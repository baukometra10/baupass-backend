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

    let setupMode = false;
    let unlocked = false;
    const waiters = [];

    function $(id) {
      return document.getElementById(id);
    }

    function setMsg(text, kind) {
      const el = $(ids.msg);
      if (!el) return;
      el.textContent = text || "";
      el.classList.toggle("is-error", kind === "err");
      el.classList.toggle("is-ok", kind === "ok");
      el.classList.toggle("is-warn", kind === "warn");
    }

    function show({ setup = false } = {}) {
      setupMode = !!setup;
      $(ids.overlay)?.classList.remove("hidden");
      $(ids.mainRoot)?.classList.add("hidden");
      $(ids.setupBlock)?.classList.toggle("hidden", !setup);
      $(ids.codeBlock)?.classList.add("hidden");
      $(ids.verifyBtn)?.classList.add("hidden");
      $(ids.sendBtn)?.classList.remove("hidden");
      $(ids.skipBtn)?.classList.toggle("hidden", !setup);
      if ($(ids.title)) {
        $(ids.title).textContent = setup
          ? t("lockSetupTitle", "Owner-Zugang einrichten")
          : t("lockTitle", "Owner-Freigabe");
      }
      if ($(ids.desc)) {
        $(ids.desc).textContent = setup
          ? t(
              "lockSetupDesc",
              "Bitte Owner-Handynummer einrichten, bevor Dokumente und Freigabe-Links nutzbar sind.",
            )
          : t(
              "lockDesc",
              "Nur mit Freigabe des Firmeninhabers. Code per SMS/E-Mail bestätigen.",
            );
      }
      setMsg("");
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
          body: JSON.stringify(body),
        });
        $(ids.codeBlock)?.classList.remove("hidden");
        $(ids.verifyBtn)?.classList.remove("hidden");
        const via = (res.channels || []).join(" + ") || "SMS/E-Mail";
        setMsg(
          res.debugCode
            ? t("lockCodeSentDebug", "Code gesendet ({via}). Debug: {code}", {
                via,
                code: res.debugCode,
              }).replace("{via}", via).replace("{code}", res.debugCode)
            : t("lockCodeSent", "Code gesendet ({via}).").replace("{via}", via),
          "ok",
        );
        if ($(ids.code)) $(ids.code).value = "";
        $(ids.code)?.focus();
        const wait = Math.max(15, Number(res.otpRequestMinSeconds || 45));
        setTimeout(() => {
          if (sendBtn) sendBtn.disabled = false;
        }, wait * 1000);
      } catch (e) {
        setMsg(e.body?.message || e.message || t("lockSendFail", "Code senden fehlgeschlagen"), "err");
        const retry = Number(e?.body?.retryInSeconds || 45);
        setTimeout(() => {
          if (sendBtn) sendBtn.disabled = false;
        }, Math.max(5, retry) * 1000);
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
        await api("/api/contracts/lock/verify", {
          method: "POST",
          body: JSON.stringify(body),
        });
        unlocked = true;
        hide();
        onStatus(t("lockUnlockedToast", "Dokumente freigeschaltet."), "ok");
        resolveWaiters(true);
      } catch (e) {
        setMsg(e.body?.message || e.message || t("lockVerifyFail", "Code ungültig"), "err");
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
        resolveWaiters(false);
      });
      $(ids.code)?.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") verifyOtp().catch(() => {});
      });
    }

    async function handleApiError(err) {
      const data = err?.body || {};
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
          show({ setup: true });
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
      ensureUnlocked,
      handleApiError,
      markUnlocked,
      isUnlocked,
      sendOtp,
      verifyOtp,
    };
  }

  global.BaupassOwnerUnlock = { create: createOwnerUnlock };
})(typeof window !== "undefined" ? window : globalThis);
