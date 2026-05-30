/**
 * Shared BauPass AI UI — ChatGPT-style voice + composer (Enterprise Hub, Command Center, Worker).
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

  const MIC_SVG = `<svg class="bp-ai-mic-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V5a3 3 0 0 1 3-3z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><path d="M12 18v4"/><path d="M8 22h8"/></svg>`;

  const WAVE_HTML = `<span class="bp-ai-mic-wave" aria-hidden="true"><span></span><span></span><span></span><span></span></span>`;

  const SEND_SVG = `<svg class="bp-ai-send-icon" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M3.4 20.6 21 12 3.4 3.4l2.8 7.2L17 12l-10.8 1.4-2.8 7.2z"/></svg>`;

  const HINTS = {
    de: "BauPass KI — Sprache oder Text. Wichtige Entscheidungen bitte prüfen.",
    en: "BauPass AI — voice or text. Verify important decisions.",
    ar: "BauPass KI — صوت أو نص. تحقق من القرارات المهمة.",
  };

  function resolveLang(lang) {
    const stored =
      lang ||
      global.localStorage?.getItem("baupass-ui-lang") ||
      global.localStorage?.getItem("baupass-admin-v2-lang") ||
      global.localStorage?.getItem("baupass-worker-lang") ||
      "de";
    return String(stored).slice(0, 2);
  }

  function resolveSpeechLang(options) {
    const uiLang = resolveLang(options?.lang);
    if (options?.multilingual === false) {
      return LANG_MAP[uiLang] || "de-DE";
    }
    const browser = String(global.navigator?.language || "").trim();
    return LANG_MAP[uiLang] || browser || "de-DE";
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
      if (u.pathname.includes("ai-command-center")) return "ai-assistant";
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
      return;
    }
    if (action.type === "worker_tab" && action.tab && typeof global.applyWorkerPageView === "function") {
      global.applyWorkerPageView(action.tab);
      const target = global.document?.getElementById(action.tab);
      target?.scrollIntoView?.({ behavior: "smooth", block: "start" });
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

  function enhanceMicButton(btnEl, labels) {
    if (!btnEl || btnEl.dataset.bpMicEnhanced === "1") return;
    btnEl.dataset.bpMicEnhanced = "1";
    btnEl.classList.add("bp-ai-mic");
    btnEl.classList.remove("ai-voice-btn", "worker-ai-voice-btn");
    btnEl.innerHTML = MIC_SVG + WAVE_HTML;
    const speak = labels?.speak || "Spracheingabe";
    btnEl.setAttribute("aria-label", speak);
    btnEl.title = speak;
  }

  function enhanceSendButton(btnEl, labels) {
    if (!btnEl || btnEl.dataset.bpSendEnhanced === "1") return;
    btnEl.dataset.bpSendEnhanced = "1";
    btnEl.classList.add("bp-ai-send");
    if (!btnEl.querySelector(".bp-ai-send-icon")) {
      btnEl.innerHTML = SEND_SVG;
    }
    const send = labels?.send || "Senden";
    btnEl.setAttribute("aria-label", send);
    btnEl.title = send;
  }

  function autoResizeTextarea(textarea) {
    if (!textarea) return;
    const resize = () => {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 144)}px`;
    };
    textarea.addEventListener("input", resize);
    resize();
  }

  function setListeningState(btnEl, listening) {
    if (!btnEl) return;
    btnEl.classList.toggle("listening", Boolean(listening));
    btnEl.setAttribute("aria-pressed", listening ? "true" : "false");
    const lang = resolveLang();
    const stopLabel = lang === "en" ? "Stop listening" : lang === "ar" ? "إيقاف الاستماع" : "Aufnahme beenden";
    const speakLabel = lang === "en" ? "Voice input" : lang === "ar" ? "إدخال صوتي" : "Spracheingabe";
    btnEl.setAttribute("aria-label", listening ? stopLabel : speakLabel);
    btnEl.title = listening ? stopLabel : speakLabel;
  }

  /**
   * Wraps textarea + mic (+ optional send) in a ChatGPT-style composer bar.
   */
  function enhanceComposer(options = {}) {
    const inputEl = document.getElementById(options.inputId || "aiQuestion");
    const btnEl = document.getElementById(options.buttonId || "aiVoiceBtn");
    const sendEl = options.sendId ? document.getElementById(options.sendId) : null;
    const formEl = options.formId ? document.getElementById(options.formId) : inputEl?.closest("form");
    if (!inputEl || !btnEl) return null;

    const lang = resolveLang(options.lang);
    const labels = {
      speak: options.speakLabel || (lang === "en" ? "Voice input" : lang === "ar" ? "إدخال صوتي" : "Spracheingabe"),
      send: options.sendLabel || (lang === "en" ? "Send" : lang === "ar" ? "إرسال" : "Senden"),
    };

    enhanceMicButton(btnEl, labels);
    if (sendEl) enhanceSendButton(sendEl, labels);

    const row = inputEl.closest(".input-row, .ai-form-row, .worker-ai-input-row");
    if (row && !row.dataset.bpComposer) {
      row.dataset.bpComposer = "1";
      row.classList.add("bp-ai-composer");

      let toolbar = row.querySelector(".bp-ai-composer-toolbar");
      if (!toolbar) {
        toolbar = document.createElement("div");
        toolbar.className = "bp-ai-composer-toolbar";
        row.appendChild(toolbar);
        toolbar.appendChild(btnEl);
        if (sendEl) toolbar.appendChild(sendEl);
      }

      if (formEl && !formEl.querySelector(".bp-ai-composer-wrap")) {
        const wrap = document.createElement("div");
        wrap.className = "bp-ai-composer-wrap";
        row.parentNode.insertBefore(wrap, row);
        wrap.appendChild(row);

        if (!formEl.querySelector(".bp-ai-composer-hint")) {
          const hint = document.createElement("p");
          hint.className = "bp-ai-composer-hint";
          hint.id = options.hintId || "bpAiComposerHint";
          hint.textContent = options.hintText || HINTS[lang] || HINTS.de;
          wrap.appendChild(hint);
        }
      }

      if (formEl) formEl.classList.add("bp-ai-form-enhanced");
    }

    autoResizeTextarea(inputEl);
    if (sendEl && formEl) {
      const syncSend = () => {
        const hasText = Boolean((inputEl.value || "").trim());
        sendEl.disabled = !hasText;
      };
      inputEl.addEventListener("input", syncSend);
      syncSend();
    }

    return { inputEl, btnEl, sendEl, formEl };
  }

  function bindVoiceInput(options) {
    const inputEl = document.getElementById(options.inputId || "aiQuestion");
    const btnEl = document.getElementById(options.buttonId || "aiVoiceBtn");
    if (!inputEl || !btnEl) return;

    enhanceComposer(options);

    const lang = resolveLang(options.lang);
    const speechLang = resolveSpeechLang(options);
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
      recognition.lang = speechLang;
      recognition.continuous = false;
      recognition.interimResults = Boolean(options.interimResults !== false);
      recognition.maxAlternatives = 1;
      recognition.onstart = () => {
        listening = true;
        setListeningState(btnEl, true);
      };
      recognition.onend = () => {
        listening = false;
        setListeningState(btnEl, false);
      };
      recognition.onerror = () => {
        listening = false;
        setListeningState(btnEl, false);
      };
      recognition.onresult = (event) => {
        let finalText = "";
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const part = event.results[i][0]?.transcript || "";
          if (event.results[i].isFinal) finalText += part;
          else interim += part;
        }
        const text = (finalText || interim).trim();
        if (!text) return;
        inputEl.value = text;
        inputEl.dispatchEvent(new Event("input", { bubbles: true }));
        inputEl.dataset.bpVoiceInput = "1";
        if (!finalText) return;
        if (typeof options.onTranscript === "function") {
          options.onTranscript(finalText);
        } else {
          inputEl.form?.requestSubmit?.();
        }
      };
      recognition.start();
    });
  }

  global.BaupassAiUi = {
    bindVoiceInput,
    enhanceComposer,
    enhanceMicButton,
    enhanceSendButton,
    setListeningState,
    renderActionButtons,
    executeBaupassAction,
    actionLabel,
    resolveLang,
    resolveSpeechLang,
  };
})(window);
