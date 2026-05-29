/**
 * Shared BauPass AI UI — voice input + action buttons (Enterprise Hub, Command Center).
 */
(function initBaupassAiUi(global) {
  const LANG_MAP = {
    de: "de-DE",
    en: "en-GB",
    tr: "tr-TR",
    ar: "ar-SA",
    fr: "fr-FR",
    es: "es-ES",
    it: "it-IT",
    pl: "pl-PL",
  };

  function resolveLang(lang) {
    const stored =
      lang ||
      global.localStorage?.getItem("baupass-ui-lang") ||
      global.localStorage?.getItem("baupass-admin-v2-lang") ||
      "de";
    return String(stored).slice(0, 2);
  }

  function actionLabel(action, lang) {
    const key = `label${lang.charAt(0).toUpperCase()}${lang.slice(1)}`;
    return action[key] || action.labelDe || action.labelEn || action.labelAr || action.label || action.id || "Open";
  }

  function parseViewFromUrl(url) {
    try {
      const u = new URL(url, global.location.origin);
      const view = u.searchParams.get("view");
      if (view) return view;
      if (u.pathname.includes("enterprise-hub")) return "enterprise-hub";
      if (u.pathname.includes("ops-command-center")) return "ops-center";
      if (u.pathname.includes("admin-v2")) return "admin-v2";
      if (u.pathname.includes("ai-command-center")) return "enterprise-hub";
    } catch {
      // no-op
    }
    return "";
  }

  function executeBaupassAction(action, lang) {
    if (!action) return;
    if (action.type === "navigate" && action.url) {
      const url = action.url;
      if (url.startsWith("mailto:") || url.startsWith("tel:")) {
        global.open(url, "_blank", "noopener,noreferrer");
        return;
      }
      const view = parseViewFromUrl(url);
      if (global.parent && global.parent !== global) {
        global.parent.postMessage({ type: "baupass-navigate", view, url }, global.location.origin);
        return;
      }
      if (view && typeof global.parent?.setView === "function") {
        global.parent.setView(view);
        return;
      }
      if (url.startsWith("/") && !url.includes("view=")) {
        global.location.href = url;
        return;
      }
      if (view) {
        const target = new URL(global.location.href);
        target.searchParams.set("view", view);
        global.location.href = target.toString();
        return;
      }
      global.location.href = url;
      return;
    }
    if (action.type === "execute" && typeof global.runExecuteAction === "function") {
      global.runExecuteAction(action, "");
    }
  }

  function renderActionButtons(container, actions, lang) {
    if (!container || !actions?.length) return;
    const row = document.createElement("div");
    row.className = "ai-action-row";
    actions.forEach((action) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "ai-action-btn";
      btn.textContent = actionLabel(action, lang);
      btn.addEventListener("click", () => executeBaupassAction(action, lang));
      row.appendChild(btn);
    });
    container.appendChild(row);
  }

  function bindVoiceInput(options) {
    const inputEl = document.getElementById(options.inputId || "aiQuestion");
    const btnEl = document.getElementById(options.buttonId || "aiVoiceBtn");
    if (!inputEl || !btnEl) return;

    const lang = resolveLang(options.lang);
    const SpeechRecognition = global.SpeechRecognition || global.webkitSpeechRecognition;
    if (!SpeechRecognition || !global.isSecureContext) {
      btnEl.disabled = true;
      btnEl.title = options.unsupportedHint || "Voice needs HTTPS";
      return;
    }

    let recognition = null;
    let listening = false;

    btnEl.addEventListener("click", () => {
      if (listening && recognition) {
        recognition.stop();
        return;
      }
      recognition = new SpeechRecognition();
      recognition.lang = LANG_MAP[lang] || "de-DE";
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.onstart = () => {
        listening = true;
        btnEl.classList.add("listening");
        btnEl.setAttribute("aria-pressed", "true");
      };
      recognition.onend = () => {
        listening = false;
        btnEl.classList.remove("listening");
        btnEl.setAttribute("aria-pressed", "false");
      };
      recognition.onerror = () => {
        listening = false;
        btnEl.classList.remove("listening");
      };
      recognition.onresult = (event) => {
        const text = event.results?.[0]?.[0]?.transcript || "";
        if (!text.trim()) return;
        inputEl.value = text.trim();
        if (typeof options.onTranscript === "function") {
          options.onTranscript(text.trim());
        } else {
          inputEl.form?.requestSubmit?.();
        }
      };
      recognition.start();
    });
  }

  global.BaupassAiUi = {
    bindVoiceInput,
    renderActionButtons,
    executeBaupassAction,
    actionLabel,
    resolveLang,
  };
})(window);
