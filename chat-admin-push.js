/**
 * SUPPIX admin chat push — VAPID web push for employer PWA/mobile browser.
 */
(function initSuppixAdminPush(global) {
  const DISMISS_KEY = "suppix-admin-push-banner-dismissed";

  function urlBase64ToUint8Array(base64String) {
    const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
    const raw = global.atob(base64);
    const output = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; ++i) output[i] = raw.charCodeAt(i);
    return output;
  }

  function arrayBufferToBase64(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = "";
    bytes.forEach((b) => { binary += String.fromCharCode(b); });
    return global.btoa(binary);
  }

  async function ensureAdminSw() {
    if (!("serviceWorker" in global.navigator)) return null;
    try {
      let registration = await global.navigator.serviceWorker.getRegistration();
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

  async function subscribeAdminPush({ api, companyId } = {}) {
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
      if (!registration) return { ok: false, error: "sw_failed" };

      let subscription = await registration.pushManager.getSubscription();
      if (!subscription) {
        const vapidRes = await api("/api/worker-app/push-vapid-key");
        const vapidKey = String(vapidRes?.vapidPublicKey || vapidRes?.publicKey || "").trim();
        if (!vapidKey) return { ok: false, error: "vapid_missing" };
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(vapidKey),
        });
      }

      await api("/api/chat/push-subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          endpoint: subscription.endpoint,
          p256dh: arrayBufferToBase64(subscription.getKey("p256dh")),
          auth: arrayBufferToBase64(subscription.getKey("auth")),
          company_id: companyId,
        }),
      });
      return { ok: true };
    } catch (err) {
      console.warn("[admin-push] subscribe failed", err);
      return { ok: false, error: String(err?.message || err || "subscribe_failed") };
    }
  }

  async function fetchAdminPushStatus({ api, companyId } = {}) {
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
      return await api(`/api/chat/push-status?${q.toString()}`);
    } catch {
      return { subscribed: false, subscriptionCount: 0 };
    }
  }

  async function unsubscribeAdminPush({ api, companyId } = {}) {
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

  function pushErrorLabel(code, labels = {}) {
    if (code === "denied") return labels.denied || "Push blockiert — in den Browser-Einstellungen erlauben.";
    if (code === "unsupported") return labels.unsupported || "Push wird in diesem Browser nicht unterstützt.";
    if (code === "company_required") return labels.companyRequired || "Bitte Chat mit Firma öffnen, dann Push aktivieren.";
    if (code === "vapid_missing") return labels.vapidMissing || "Push-Server-Schlüssel fehlen (VAPID).";
    if (code === "sw_failed") return labels.swFailed || "Service Worker konnte nicht geladen werden.";
    if (code === "permission_dismissed") return labels.permissionDismissed || "Benachrichtigung nicht erlaubt.";
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
          if (textEl && result?.error) {
            textEl.textContent = pushErrorLabel(result.error, labels);
          }
          sync();
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
    labels = {},
  } = {}) {
    if (!statusEl || !api) return () => {};
    const render = async () => {
      if (!companyId) {
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
      const status = await fetchAdminPushStatus({ api, companyId });
      const subscribed = Boolean(status?.subscribed);
      statusEl.classList.remove("hidden");
      if (textEl) {
        textEl.textContent = subscribed
          ? (labels.enabled || "Push aktiv — Mitarbeiter-Nachrichten erreichen dieses Gerät.")
          : (labels.disabled || "Push nicht aktiv auf diesem Gerät.");
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
          const prev = actionBtn.textContent;
          actionBtn.textContent = "…";
          try {
            if (mode === "unsubscribe") {
              await unsubscribeAdminPush({ api, companyId });
            } else {
              const result = await subscribeAdminPush({ api, companyId });
              if (result.ok) {
                if (textEl) textEl.textContent = labels.enabled || "Push aktiv — Mitarbeiter-Nachrichten erreichen dieses Gerät.";
                actionBtn.dataset.mode = "unsubscribe";
                actionBtn.textContent = labels.unsubscribe || "Deaktivieren";
              } else if (textEl) {
                textEl.textContent = pushErrorLabel(result.error, labels);
              }
            }
          } finally {
            actionBtn.disabled = false;
            actionBtn.textContent = prev;
            await render();
          }
        })();
      });
    }
    void render();
    return render;
  }

  function initAdminChatPush({ api, companyId, prompt = true, banner, status } = {}) {
    if (!api) return;
    if (banner) {
      mountPushBanner({
        ...banner,
        onSubscribed: async () => {
          const result = await subscribeAdminPush({ api, companyId });
          if (result.ok && status?.refresh) await status.refresh();
          return result;
        },
      });
    }
    let refresh = null;
    if (status) {
      refresh = mountPushStatus({ ...status, api, companyId });
      status.refresh = refresh;
    }
    if (!prompt) return;
    if (!("Notification" in global)) return;
    if (Notification.permission === "granted" && companyId) {
      void subscribeAdminPush({ api, companyId }).then((result) => {
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
