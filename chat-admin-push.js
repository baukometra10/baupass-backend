/**
 * SUPPIX admin chat push — VAPID web push for employer PWA/mobile browser.
 */
(function initSuppixAdminPush(global) {
  const DISMISS_KEY = "suppix-admin-push-banner-dismissed";
  const LOCAL_OK_PREFIX = "suppix-admin-push-local-ok:";

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = global.atob(base64);
    const output = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; ++i) output[i] = raw.charCodeAt(i);
    return output;
  }

  function arrayBufferToBase64(buffer) {
    if (!buffer) return "";
    const bytes = new Uint8Array(buffer);
    let binary = "";
    bytes.forEach((b) => { binary += String.fromCharCode(b); });
    return global.btoa(binary);
  }

  function resolveCompanyId(opts = {}) {
    if (typeof opts.getCompanyId === "function") {
      const live = String(opts.getCompanyId() || "").trim();
      if (live) return live;
    }
    return String(opts.companyId || "").trim();
  }

  function markLocalPushOk(companyId, endpoint) {
    try {
      if (companyId && endpoint) {
        global.sessionStorage?.setItem(`${LOCAL_OK_PREFIX}${companyId}`, endpoint);
      }
    } catch {
      /* ignore */
    }
  }

  function clearLocalPushOk(companyId) {
    try {
      if (companyId) global.sessionStorage?.removeItem(`${LOCAL_OK_PREFIX}${companyId}`);
    } catch {
      /* ignore */
    }
  }

  function hasLocalPushOk(companyId, endpoint) {
    try {
      const saved = global.sessionStorage?.getItem(`${LOCAL_OK_PREFIX}${companyId}`) || "";
      return Boolean(saved && (!endpoint || saved === endpoint));
    } catch {
      return false;
    }
  }

  async function ensureAdminSw() {
    if (!("serviceWorker" in global.navigator)) return null;
    try {
      let registration = await global.navigator.serviceWorker.getRegistration("/");
      if (!registration) {
        registration = await global.navigator.serviceWorker.getRegistration();
      }
      if (!registration) {
        registration = await global.navigator.serviceWorker.register("/admin-sw.js", { scope: "/" });
      }
      await global.navigator.serviceWorker.ready;
      return registration;
    } catch (err) {
      console.warn("[admin-push] SW register failed", err);
      return null;
    }
  }

  function pushSupportState() {
    if (!("Notification" in global) || !("PushManager" in global) || !("serviceWorker" in global.navigator)) {
      return "unsupported";
    }
    if (Notification.permission === "denied") return "denied";
    return "ok";
  }

  async function fetchVapidPublicKey(api) {
    const paths = ["/api/chat/push-vapid-key", "/api/worker-app/push-vapid-key"];
    let lastErr = null;
    for (const path of paths) {
      try {
        const vapidRes = await api(path);
        const vapidKey = String(vapidRes?.vapidPublicKey || vapidRes?.publicKey || "").trim();
        if (vapidKey) {
          return {
            ok: true,
            key: vapidKey,
            configured: vapidRes?.configured !== false,
          };
        }
        if (vapidRes && vapidRes.configured === false) {
          return { ok: false, error: "vapid_missing", configured: false };
        }
      } catch (err) {
        lastErr = err;
      }
    }
    return {
      ok: false,
      error: "vapid_missing",
      detail: String(lastErr?.message || lastErr || ""),
    };
  }

  async function subscribeAdminPush(opts = {}) {
    const { api } = opts;
    const companyId = resolveCompanyId(opts);
    if (!api) return { ok: false, error: "api_required" };
    if (!companyId) return { ok: false, error: "company_required" };
    if (!("Notification" in global) || !("PushManager" in global)) {
      return { ok: false, error: "unsupported" };
    }
    if (Notification.permission === "denied") return { ok: false, error: "denied" };
    try {
      if (Notification.permission === "default") {
        const perm = await Notification.requestPermission();
        if (perm !== "granted") return { ok: false, error: perm === "denied" ? "denied" : "permission_dismissed" };
      }
      const registration = await ensureAdminSw();
      if (!registration?.pushManager) return { ok: false, error: "sw_failed" };

      let subscription = await registration.pushManager.getSubscription();
      if (!subscription) {
        const vapid = await fetchVapidPublicKey(api);
        if (!vapid.ok || !vapid.key) {
          return { ok: false, error: vapid.error || "vapid_missing" };
        }
        try {
          subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(vapid.key),
          });
        } catch (subErr) {
          console.warn("[admin-push] pushManager.subscribe failed", subErr);
          return { ok: false, error: "subscribe_failed", detail: String(subErr?.message || subErr) };
        }
      }

      const p256dh = arrayBufferToBase64(subscription.getKey("p256dh"));
      const auth = arrayBufferToBase64(subscription.getKey("auth"));
      if (!subscription.endpoint || !p256dh || !auth) {
        return { ok: false, error: "subscribe_failed", detail: "missing_subscription_keys" };
      }

      await api("/api/chat/push-subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          endpoint: subscription.endpoint,
          p256dh,
          auth,
          company_id: companyId,
        }),
      });
      markLocalPushOk(companyId, subscription.endpoint);
      return { ok: true, endpoint: subscription.endpoint };
    } catch (err) {
      console.warn("[admin-push] subscribe failed", err);
      const msg = String(err?.message || err || "subscribe_failed");
      if (/vapid/i.test(msg)) return { ok: false, error: "vapid_missing", detail: msg };
      if (/missing_user|missing_fields/i.test(msg)) return { ok: false, error: "subscribe_failed", detail: msg };
      return { ok: false, error: "subscribe_failed", detail: msg };
    }
  }

  async function fetchAdminPushStatus(opts = {}) {
    const { api } = opts;
    const companyId = resolveCompanyId(opts);
    if (!api || !companyId) return { subscribed: false, subscriptionCount: 0 };
    try {
      let endpoint = "";
      try {
        const registration = await ensureAdminSw();
        const subscription = await registration?.pushManager?.getSubscription?.();
        endpoint = subscription?.endpoint || "";
      } catch {
        /* ignore */
      }
      const q = new URLSearchParams({ company_id: companyId });
      if (endpoint) q.set("endpoint", endpoint);
      const status = await api(`/api/chat/push-status?${q.toString()}`);
      if (status?.subscribed) {
        if (endpoint) markLocalPushOk(companyId, endpoint);
        return status;
      }
      if (hasLocalPushOk(companyId, endpoint) && endpoint) {
        return { ...status, subscribed: true, endpointMatched: true, localOptimistic: true };
      }
      return status;
    } catch (err) {
      console.warn("[admin-push] status failed", err);
      let endpoint = "";
      try {
        const registration = await ensureAdminSw();
        endpoint = (await registration?.pushManager?.getSubscription?.())?.endpoint || "";
      } catch {
        /* ignore */
      }
      if (hasLocalPushOk(companyId, endpoint)) {
        return { subscribed: true, subscriptionCount: 1, localOptimistic: true };
      }
      return { subscribed: false, subscriptionCount: 0, error: String(err?.message || err || "") };
    }
  }

  async function unsubscribeAdminPush(opts = {}) {
    const { api } = opts;
    const companyId = resolveCompanyId(opts);
    if (!api || !companyId) return false;
    try {
      const registration = await ensureAdminSw();
      const subscription = await registration?.pushManager?.getSubscription?.();
      const endpoint = subscription?.endpoint || "";
      if (subscription) {
        try { await subscription.unsubscribe(); } catch { /* ignore */ }
      }
      await api("/api/chat/push-unsubscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ company_id: companyId, ...(endpoint ? { endpoint } : {}) }),
      });
      clearLocalPushOk(companyId);
      return true;
    } catch {
      return false;
    }
  }

  function shouldShowPushBanner() {
    if (!("Notification" in global)) return false;
    if (Notification.permission === "granted") return false;
    try {
      if (global.sessionStorage?.getItem(DISMISS_KEY) === "1") return false;
    } catch {
      /* ignore */
    }
    return true;
  }

  function pushErrorLabel(code, labels = {}, detail = "") {
    if (code === "denied") return labels.denied || "Push blockiert — in den Browser-Einstellungen erlauben.";
    if (code === "unsupported") return labels.unsupported || "Push wird in diesem Browser nicht unterstützt.";
    if (code === "company_required") return labels.companyRequired || "Bitte Chat mit Firma öffnen, dann Push aktivieren.";
    if (code === "vapid_missing") {
      return labels.vapidMissing
        || "Push-Server-Schlüssel fehlen (VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_EMAIL auf dem Server setzen).";
    }
    if (code === "sw_failed") return labels.swFailed || "Service Worker konnte nicht geladen werden.";
    if (code === "permission_dismissed") return labels.permissionDismissed || "Benachrichtigung nicht erlaubt.";
    if (detail && /missing_user|session/i.test(detail)) {
      return labels.sessionRequired || "Bitte erneut anmelden, dann Push aktivieren.";
    }
    return labels.subscribeFailed || "Push konnte nicht aktiviert werden. Bitte erneut versuchen.";
  }

  function mountPushBanner({ bannerEl, textEl, enableBtn, dismissBtn, labels = {}, onSubscribed } = {}) {
    if (!bannerEl) return;
    const sync = () => {
      if (!shouldShowPushBanner()) {
        bannerEl.classList.add("hidden");
        return;
      }
      if (textEl) {
        textEl.textContent = Notification.permission === "denied"
          ? (labels.denied || "Push blockiert — in den Browser-Einstellungen erlauben.")
          : (labels.prompt || "Push aktivieren, um Mitarbeiter-Nachrichten auch bei geschlossenem Tab zu erhalten.");
      }
      if (enableBtn) {
        enableBtn.disabled = Notification.permission === "denied";
        enableBtn.textContent = labels.enable || "Aktivieren";
      }
      bannerEl.classList.remove("hidden");
    };
    sync();
    if (enableBtn && !enableBtn.dataset.pushBound) {
      enableBtn.dataset.pushBound = "1";
      enableBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        enableBtn.disabled = true;
        const prev = enableBtn.textContent;
        enableBtn.textContent = "…";
        void (async () => {
          const result = await onSubscribed?.();
          const ok = result === true || result?.ok === true;
          if (ok) {
            bannerEl.classList.add("hidden");
            return;
          }
          enableBtn.disabled = false;
          enableBtn.textContent = prev || labels.enable || "Aktivieren";
          if (textEl) {
            textEl.textContent = pushErrorLabel(result?.error, labels, result?.detail);
          }
        })();
      });
    }
    dismissBtn?.addEventListener("click", () => {
      try { global.sessionStorage?.setItem(DISMISS_KEY, "1"); } catch { /* ignore */ }
      bannerEl.classList.add("hidden");
    });
    return sync;
  }

  function mountPushStatus({
    statusEl,
    textEl,
    actionBtn,
    api,
    companyId,
    getCompanyId,
    labels = {},
  } = {}) {
    if (!statusEl || !api) return () => {};
    let lastError = "";
    const opts = { api, companyId, getCompanyId };

    const render = async ({ keepError = false } = {}) => {
      const cid = resolveCompanyId(opts);
      if (!cid) {
        statusEl.classList.remove("hidden");
        if (textEl) textEl.textContent = pushErrorLabel("company_required", labels);
        if (actionBtn) actionBtn.classList.add("hidden");
        return;
      }
      const support = pushSupportState();
      if (support === "unsupported") {
        statusEl.classList.remove("hidden");
        if (textEl) textEl.textContent = labels.unsupported || "Push wird in diesem Browser nicht unterstützt.";
        if (actionBtn) actionBtn.classList.add("hidden");
        return;
      }
      if (support === "denied") {
        statusEl.classList.remove("hidden");
        if (textEl) textEl.textContent = labels.denied || "Push blockiert — in den Browser-Einstellungen erlauben.";
        if (actionBtn) actionBtn.classList.add("hidden");
        return;
      }
      const status = await fetchAdminPushStatus({ ...opts, companyId: cid });
      const subscribed = Boolean(status?.subscribed);
      statusEl.classList.remove("hidden");
      statusEl.classList.toggle("is-ok", subscribed);
      statusEl.classList.toggle("is-error", Boolean(!subscribed && keepError && lastError));
      if (textEl) {
        if (!subscribed && keepError && lastError) {
          textEl.textContent = lastError;
        } else {
          textEl.textContent = subscribed
            ? (labels.enabled || "Push aktiv — Mitarbeiter-Nachrichten erreichen dieses Gerät.")
            : (labels.disabled || "Push nicht aktiv auf diesem Gerät.");
        }
      }
      if (actionBtn) {
        actionBtn.classList.remove("hidden");
        actionBtn.disabled = false;
        actionBtn.textContent = subscribed
          ? (labels.unsubscribe || "Deaktivieren")
          : (labels.enable || "Aktivieren");
        actionBtn.dataset.mode = subscribed ? "unsubscribe" : "subscribe";
      }
    };

    if (actionBtn && !actionBtn.dataset.pushBound) {
      actionBtn.dataset.pushBound = "1";
      actionBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        void (async () => {
          const mode = actionBtn.dataset.mode || "subscribe";
          actionBtn.disabled = true;
          actionBtn.textContent = "…";
          lastError = "";
          try {
            if (mode === "unsubscribe") {
              await unsubscribeAdminPush(opts);
              lastError = "";
              await render();
              return;
            }
            const result = await subscribeAdminPush(opts);
            if (result.ok) {
              lastError = "";
              if (textEl) {
                textEl.textContent = labels.enabled || "Push aktiv — Mitarbeiter-Nachrichten erreichen dieses Gerät.";
              }
              actionBtn.dataset.mode = "unsubscribe";
              actionBtn.textContent = labels.unsubscribe || "Deaktivieren";
              actionBtn.disabled = false;
              await render();
              return;
            }
            lastError = pushErrorLabel(result.error, labels, result.detail);
            if (textEl) textEl.textContent = lastError;
            actionBtn.dataset.mode = "subscribe";
            actionBtn.textContent = labels.enable || "Aktivieren";
            actionBtn.disabled = false;
            // Keep the real error visible — do not wipe with "not active"
            await render({ keepError: true });
          } catch (err) {
            lastError = pushErrorLabel("subscribe_failed", labels, String(err?.message || err || ""));
            if (textEl) textEl.textContent = lastError;
            actionBtn.dataset.mode = "subscribe";
            actionBtn.textContent = labels.enable || "Aktivieren";
            actionBtn.disabled = false;
          }
        })();
      });
    }
    void render();
    return render;
  }

  function initAdminChatPush({ api, companyId, getCompanyId, prompt = true, banner, status } = {}) {
    if (!api) return;
    const liveOpts = { api, companyId, getCompanyId };
    if (banner) {
      mountPushBanner({
        ...banner,
        onSubscribed: async () => {
          const result = await subscribeAdminPush(liveOpts);
          if (result.ok && status?.refresh) await status.refresh();
          return result;
        },
      });
    }
    let refresh = null;
    if (status) {
      refresh = mountPushStatus({ ...status, ...liveOpts });
      status.refresh = refresh;
    }
    if (!prompt) return;
    if (!("Notification" in global)) return;
    const cid = resolveCompanyId(liveOpts);
    if (Notification.permission === "granted" && cid) {
      void subscribeAdminPush(liveOpts).then((result) => {
        if (result.ok) refresh?.();
      });
    }
  }

  global.SUPPIXAdminChatPush = {
    ensureAdminSw,
    subscribeAdminPush,
    unsubscribeAdminPush,
    fetchAdminPushStatus,
    shouldShowPushBanner,
    mountPushBanner,
    mountPushStatus,
    initAdminChatPush,
  };
})(typeof window !== "undefined" ? window : globalThis);
