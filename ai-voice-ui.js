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
    de: "BauPass KI — Sprache oder Text (Deutsch, Englisch, Arabisch). Wichtige Entscheidungen bitte prüfen.",
    en: "BauPass AI — voice or text (German, English, Arabic). Verify important decisions.",
    ar: "BauPass KI — صوت أو نص (ألماني، إنجليزي، عربي). تحقق من القرارات المهمة.",
  };

  const LABELS = {
    de: {
      speak: "Spracheingabe",
      stop: "Aufnahme beenden",
      send: "Senden",
      unsupported: "Spracheingabe benötigt HTTPS",
      open: "Öffnen",
    },
    en: {
      speak: "Voice input",
      stop: "Stop listening",
      send: "Send",
      unsupported: "Voice needs HTTPS",
      open: "Open",
    },
    ar: {
      speak: "إدخال صوتي",
      stop: "إيقاف الاستماع",
      send: "إرسال",
      unsupported: "الصوت يتطلب HTTPS",
      open: "فتح",
    },
  };

  function labelsForLang(lang) {
    const key = resolveLang(lang);
    return LABELS[key] || LABELS.de;
  }

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

  function preferWhisperTranscription(options) {
    if (options?.useWhisper === false) return false;
    if (options?.multilingual === false) return Boolean(options?.useWhisper);
    return options?.useWhisper !== false;
  }

  function pickRecorderMimeType() {
    const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
    for (const mime of candidates) {
      if (global.MediaRecorder?.isTypeSupported?.(mime)) return mime;
    }
    return "";
  }

  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onloadend = () => {
        const raw = String(reader.result || "");
        const idx = raw.indexOf(",");
        resolve(idx >= 0 ? raw.slice(idx + 1) : raw);
      };
      reader.onerror = () => reject(reader.error || new Error("read_failed"));
      reader.readAsDataURL(blob);
    });
  }

  async function transcribeWithWhisper(blob, options) {
    const audioB64 = await blobToBase64(blob);
    const headers = { "Content-Type": "application/json" };
    if (typeof options.authHeaders === "function") {
      Object.assign(headers, options.authHeaders());
    } else if (options.authHeaders && typeof options.authHeaders === "object") {
      Object.assign(headers, options.authHeaders);
    }
    const url = options.transcribeUrl || "/api/ai/transcribe";
    const multilingual = options.multilingual !== false;
    const res = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({
        audio: audioB64,
        mime: blob.type || "audio/webm",
        multilingual,
        lang: multilingual ? "auto" : resolveLang(options.lang),
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.hint || data.error || res.statusText);
      err.payload = data;
      throw err;
    }
    return String(data.text || "").trim();
  }

  function startBrowserSpeechRecognition(options, btnEl, inputEl, lang, speechLang) {
    const SpeechRecognition = global.SpeechRecognition || global.webkitSpeechRecognition;
    if (!SpeechRecognition || !global.isSecureContext) {
      btnEl.disabled = true;
      btnEl.title = options.unsupportedHint || labelsForLang(lang).unsupported;
      return null;
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
        setListeningState(btnEl, true, lang);
      };
      recognition.onend = () => {
        listening = false;
        setListeningState(btnEl, false, lang);
      };
      recognition.onerror = () => {
        listening = false;
        setListeningState(btnEl, false, lang);
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
    return recognition;
  }

  async function startWhisperCapture(options, btnEl, inputEl, lang) {
    if (!global.navigator?.mediaDevices?.getUserMedia || !global.MediaRecorder) {
      return false;
    }

    let stream = null;
    let recorder = null;
    let listening = false;
    const ui = labelsForLang(lang);

    const finish = (text) => {
      const cleaned = String(text || "").trim();
      if (!cleaned) return;
      inputEl.value = cleaned;
      inputEl.dispatchEvent(new Event("input", { bubbles: true }));
      inputEl.dataset.bpVoiceInput = "1";
      if (typeof options.onTranscript === "function") {
        options.onTranscript(cleaned);
      } else {
        inputEl.form?.requestSubmit?.();
      }
    };

    btnEl.addEventListener("click", async () => {
      if (listening && recorder && recorder.state !== "inactive") {
        recorder.stop();
        return;
      }
      try {
        stream = await global.navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = pickRecorderMimeType();
        const chunks = [];
        recorder = mimeType ? new global.MediaRecorder(stream, { mimeType }) : new global.MediaRecorder(stream);
        recorder.ondataavailable = (event) => {
          if (event.data && event.data.size > 0) chunks.push(event.data);
        };
        recorder.onstop = async () => {
          listening = false;
          setListeningState(btnEl, false, lang);
          stream?.getTracks?.().forEach((track) => track.stop());
          stream = null;
          btnEl.classList.remove("bp-ai-transcribing");
          const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
          try {
            btnEl.classList.add("bp-ai-transcribing");
            btnEl.title = ui.speak;
            const text = await transcribeWithWhisper(blob, options);
            finish(text);
          } catch (err) {
            if (typeof options.onTranscribeError === "function") {
              options.onTranscribeError(err);
            } else {
              global.console?.warn?.("Whisper transcription failed", err);
            }
          } finally {
            btnEl.classList.remove("bp-ai-transcribing");
            btnEl.title = ui.speak;
          }
        };
        recorder.start();
        listening = true;
        setListeningState(btnEl, true, lang);
      } catch (err) {
        listening = false;
        setListeningState(btnEl, false, lang);
        stream?.getTracks?.().forEach((track) => track.stop());
        if (typeof options.onMicError === "function") {
          options.onMicError(err);
        }
      }
    });
    return true;
  }

  function actionLabel(action, lang) {
    const key = `label${lang.charAt(0).toUpperCase()}${lang.slice(1)}`;
    const ui = labelsForLang(lang);
    return action[key] || action.labelDe || action.labelEn || action.labelAr || action.label || action.id || ui.open;
  }

  function parseViewFromUrl(url) {
    if (global.BaupassEmbed?.viewFromHref) {
      return global.BaupassEmbed.viewFromHref(url);
    }
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
      const focusEinsatzplan =
        action.focusEinsatzplan === true ||
        url.includes("einsatzplan=1") ||
        url.includes("view=deployment-plan") ||
        url.includes("#einsatzplan");
      if (global.parent && global.parent !== global) {
        if (global.BaupassEmbed?.navigateFromEmbed && view) {
          global.BaupassEmbed.navigateFromEmbed(url);
          return;
        }
        global.parent.postMessage(
          { type: "baupass-navigate", view, url, focusEinsatzplan },
          global.location.origin,
        );
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

  function setListeningState(btnEl, listening, lang) {
    if (!btnEl) return;
    btnEl.classList.toggle("listening", Boolean(listening));
    btnEl.setAttribute("aria-pressed", listening ? "true" : "false");
    const ui = labelsForLang(lang);
    btnEl.setAttribute("aria-label", listening ? ui.stop : ui.speak);
    btnEl.title = listening ? ui.stop : ui.speak;
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
    const ui = labelsForLang(lang);
    const labels = {
      speak: options.speakLabel || ui.speak,
      send: options.sendLabel || ui.send,
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
    const useWhisper = preferWhisperTranscription(options);

    if (useWhisper) {
      startWhisperCapture(options, btnEl, inputEl, lang).then((started) => {
        if (!started) {
          startBrowserSpeechRecognition(options, btnEl, inputEl, lang, speechLang);
        }
      });
      return;
    }

    startBrowserSpeechRecognition(options, btnEl, inputEl, lang, speechLang);
  }

  function refreshComposerLabels(options = {}) {
    const lang = resolveLang(options.lang);
    const ui = labelsForLang(lang);
    const btnEl = document.getElementById(options.buttonId || "aiVoiceBtn");
    const sendEl = options.sendId ? document.getElementById(options.sendId) : null;
    const hintEl = document.getElementById(options.hintId || "bpAiComposerHint");
    if (btnEl) {
      const listening = btnEl.classList.contains("listening");
      btnEl.setAttribute("aria-label", listening ? ui.stop : ui.speak);
      btnEl.title = listening ? ui.stop : ui.speak;
    }
    if (sendEl) {
      sendEl.setAttribute("aria-label", ui.send);
      sendEl.title = ui.send;
    }
    if (hintEl) {
      hintEl.textContent = options.hintText || HINTS[lang] || HINTS.de;
    }
  }

  global.BaupassAiUi = {
    bindVoiceInput,
    enhanceComposer,
    enhanceMicButton,
    enhanceSendButton,
    setListeningState,
    refreshComposerLabels,
    renderActionButtons,
    executeBaupassAction,
    actionLabel,
    resolveLang,
    resolveSpeechLang,
    labelsForLang,
    transcribeWithWhisper,
  };
})(window);
