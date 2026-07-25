/**
 * Shared Owner step-up unlock (contracts + docs).
 * Uses /api/contracts/lock/* OTP session (shared unlock flag).
 */
(function (global) {
  function createOwnerUnlock(opts) {
    const cfg = opts || {};
    const ids = Object.assign(
      {
        overlay: "docsLockOverlay",
        title: "docsLockTitle",
        desc: "docsLockDesc",
        setupBlock: "docsLockSetupBlock",
        emailLabel: "docsLockEmailLabel",
        deliveryHint: "docsLockDeliveryHint",
        rateHint: "docsLockRateHint",
        phone: "docsLockOwnerPhone",
        email: "docsLockOwnerEmail",
        codeBlock: "docsLockCodeBlock",
        code: "docsLockOtpCode",
        msg: "docsLockMsg",
        sendBtn: "docsLockSendBtn",
        verifyBtn: "docsLockVerifyBtn",
        skipBtn: "docsLockSkipBtn",
        mainRoot: "docsMainRoot",
      },
      cfg.ids || {},
    );

    const t = typeof cfg.t === "function" ? cfg.t : (k, fallback) => fallback || k;
    const api = cfg.api;
    const getCompanyId = cfg.getCompanyId || (() => "");
    const onStatus = typeof cfg.onStatus === "function" ? cfg.onStatus : () => {};
    const onVerified = typeof cfg.onVerified === "function" ? cfg.onVerified : null;
    const mapError = typeof cfg.mapError === "function" ? cfg.mapError : (e) => e?.body?.message || e?.data?.message || e?.message || String(e);
    const skipResolvesTrue = cfg.skipResolvesTrue === true;

    let setupMode = false;
    let unlocked = false;
    let cooldownUntil = 0;
    const waiters = [];

    function $(id) {
      return id ? document.getElementById(id) : null;
    }

    function setMsg(text, kind) {
      const el = $(ids.msg);
      if (!el) return;
      el.textContent = text || "";
      el.classList.toggle("is-error", kind === "err" || kind === "error");
      el.classList.toggle("is-ok", kind === "ok");
      el.classList.toggle("is-warn", kind === "warn");
    }

    function setRateHint(seconds) {
      const el = $(ids.rateHint);
      if (!el) return;
      const n = Math.max(0, Number(seconds) || 0);
      if (n <= 0) {
        el.textContent = "";
        el.classList.add("hidden");
        return;
      }
      el.classList.remove("hidden");
      el.textContent = t(
        "lockRateLimitHint",
        "Bitte {n}s warten, bevor Sie erneut einen Code anfordern.",
      ).replace("{n}", String(n));
    }

    function startCooldown(seconds) {
      const wait = Math.max(5, Number(seconds) || 45);
      cooldownUntil = Date.now() + wait * 1000;
      const sendBtn = $(ids.sendBtn);
      if (sendBtn) sendBtn.disabled = true;
      setRateHint(wait);
      const tick = () => {
        const left = Math.ceil((cooldownUntil - Date.now()) / 1000);
        if (left <= 0) {
          if (sendBtn) sendBtn.disabled = false;
          setRateHint(0);
          return;
        }
        setRateHint(left);
        setTimeout(tick, 1000);
      };
      setTimeout(tick, 1000);
    }

    function show({ setup = false, enforced = false, smsConfigured = true } = {}) {
      setupMode = !!setup;
      $(ids.overlay)?.classList.remove("hidden");
      $(ids.mainRoot)?.classList.add("hidden");
      $(ids.setupBlock)?.classList.toggle("hidden", !setup);
      $(ids.codeBlock)?.classList.add("hidden");
      $(ids.verifyBtn)?.classList.add("hidden");
      $(ids.sendBtn)?.classList.remove("hidden");
      // Skip only when setup is optional (not enforced).
      $(ids.skipBtn)?.classList.toggle("hidden", !setup || enforced);
      if ($(ids.title)) {
        $(ids.title).textContent = setup
          ? t("lockSetupTitle", "Owner-Zugang einrichten")
          : t("lockTitle", "Owner-Freigabe");
      }
      if ($(ids.desc)) {
        if (setup && enforced) {
          $(ids.desc).textContent = t(
            "lockSetupRequiredDesc",
            "Pflicht: Owner-Handynummer einrichten, sonst bleiben Verträge/Dokumente gesperrt.",
          );
        } else if (setup) {
          $(ids.desc).textContent = t(
            "lockSetupDesc",
            "Bitte Owner-Handynummer einrichten. Der Code kommt per SMS (E-Mail als Backup).",
          );
        } else {
          $(ids.desc).textContent = t(
            "lockDesc",
            "Nur mit Freigabe des Firmeninhabers. Code per SMS/E-Mail bestätigen.",
          );
        }
      }
      const emailLabel = $(ids.emailLabel);
      const hint = $(ids.deliveryHint);
      if (!smsConfigured) {
        if (emailLabel) {
          emailLabel.textContent = t("lockEmailRequired", "E-Mail (erforderlich — SMS nicht konfiguriert)");
        }
        if (hint) {
          hint.textContent = t(
            "lockNoSmsHint",
            "Twilio-SMS fehlt. Code geht per E-Mail oder als Debug-Code in der Entwicklung.",
          );
        }
      } else {
        if (emailLabel) {
          emailLabel.textContent = t("lockEmailLabel", "Backup-E-Mail (optional)");
        }
        if (hint) {
          hint.textContent = t("lockSmsOkHint", "SMS aktiv. E-Mail als Backup empfohlen.");
        }
      }
      setMsg("");
      if (Date.now() < cooldownUntil) {
        setRateHint(Math.ceil((cooldownUntil - Date.now()) / 1000));
      } else {
        setRateHint(0);
      }
    }

    function hide() {
      $(ids.overlay)?.classList.add("hidden");
      $(ids.mainRoot)?.classList.remove("hidden");
    }

    function resolveWaiters(ok) {
      const list = waiters.splice(0, waiters.length);
      list.forEach((fn) => {
        try {
          fn(!!ok);
        } catch {
          /* ignore */
        }
      });
    }

    function ensureUnlocked() {
      if (unlocked) return Promise.resolve(true);
      show({ setup: false });
      return new Promise((resolve) => waiters.push(resolve));
    }

    async function sendOtp() {
      const sendBtn = $(ids.sendBtn);
      if (sendBtn?.disabled) return;
      if (Date.now() < cooldownUntil) {
        const left = Math.ceil((cooldownUntil - Date.now()) / 1000);
        setMsg(t("lockRateLimitHint", "Bitte {n}s warten.").replace("{n}", String(left)), "warn");
        setRateHint(left);
        return;
      }
      setMsg("");
      const phone = $(ids.phone)?.value.trim() || "";
      const email = $(ids.email)?.value.trim() || "";
      const body = { company_id: getCompanyId(), setup: setupMode };
      if (setupMode) body.phone = phone;
      if (email) body.email = email;
      if (sendBtn) sendBtn.disabled = true;
      try {
        const res = await api("/api/contracts/lock/request-otp", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        $(ids.codeBlock)?.classList.remove("hidden");
        $(ids.verifyBtn)?.classList.remove("hidden");
        const via = (res.channels || []).join(" + ") || "SMS/E-Mail";
        const phoneBit = res.phoneMasked ? ` · ${res.phoneMasked}` : "";
        const emailBit = res.emailMasked ? ` · ${res.emailMasked}` : "";
        if (res.debugFallback || res.debugCode) {
          const debugHint = res.debugCode ? ` Debug-Code: ${res.debugCode}` : "";
          setMsg(
            (res.message || t("lockDebugFallback", "Debug-Code (kein SMS/E-Mail-Versand).")) + debugHint,
            "ok",
          );
        } else {
          setMsg(
            res.message ||
              t("lockCodeSent", "Code gesendet ({via}).")
                .replace("{via}", via) + phoneBit + emailBit,
            "ok",
          );
        }
        if ($(ids.code)) $(ids.code).value = "";
        $(ids.code)?.focus();
        startCooldown(res.otpRequestMinSeconds || 45);
      } catch (e) {
        const retry = Number(e?.body?.retryInSeconds || e?.data?.retryInSeconds || 45);
        setMsg(mapError(e) || t("lockSendFail", "Code senden fehlgeschlagen"), "err");
        startCooldown(retry);
      }
    }

    async function verifyOtp() {
      const code = $(ids.code)?.value.trim() || "";
      if (!code) {
        setMsg(t("lockCodeRequired", "Bitte Code eingeben."), "err");
        return;
      }
      const phone = $(ids.phone)?.value.trim() || "";
      const email = $(ids.email)?.value.trim() || "";
      const body = { company_id: getCompanyId(), code, setup: setupMode };
      if (setupMode) {
        body.phone = phone;
        if (email) body.email = email;
      }
      try {
        const res = await api("/api/contracts/lock/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        unlocked = true;
        hide();
        onStatus(t("lockUnlockedToast", "Bereich freigeschaltet."), "ok");
        if (onVerified) {
          await onVerified(res);
        }
        resolveWaiters(true);
      } catch (e) {
        setMsg(mapError(e) || t("lockVerifyFail", "Code ungültig"), "err");
      }
    }

    function bind() {
      $(ids.sendBtn)?.addEventListener("click", () => {
        sendOtp().catch(() => {});
      });
      $(ids.verifyBtn)?.addEventListener("click", () => {
        verifyOtp().catch(() => {});
      });
      $(ids.skipBtn)?.addEventListener("click", () => {
        hide();
        resolveWaiters(skipResolvesTrue);
      });
      $(ids.code)?.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") verifyOtp().catch(() => {});
      });
    }

    async function handleApiError(err) {
      const data = err?.body || err?.data || {};
      if (data.roleBlocked || data.error === "sensitive_forbidden") {
        const msg =
          data.message ||
          t(
            "lockRoleBlocked",
            "Nur mit Freigabe des Firmeninhabers — Inhaber wurde informiert.",
          );
        onStatus(msg, "err");
        setMsg(msg, "warn");
        return true;
      }
      if (
        data.stepUpRequired ||
        data.error === "contracts_locked" ||
        data.error === "owner_setup_required"
      ) {
        unlocked = false;
        if (data.ownerSetupRequired || data.error === "owner_setup_required") {
          show({ setup: true, enforced: true });
        } else {
          const ok = await ensureUnlocked();
          return !ok;
        }
        return true;
      }
      return false;
    }

    function markUnlocked(v) {
      unlocked = !!v;
    }

    function isUnlocked() {
      return unlocked;
    }

    return {
      bind,
      show,
      hide,
      setMsg,
      setRateHint,
      ensureUnlocked,
      handleApiError,
      markUnlocked,
      isUnlocked,
      sendOtp,
      verifyOtp,
      resolveWaiters,
    };
  }

  global.BaupassOwnerUnlock = { create: createOwnerUnlock };
})(typeof window !== "undefined" ? window : globalThis);
