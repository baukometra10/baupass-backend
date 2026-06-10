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

  const DEFAULT_MAX_RECORD_MS = 300000;
  const DEFAULT_MIN_RECORD_MS = 600;
  const MIN_AUDIO_BYTES = 1200;

  const HINTS = {
    de: "Mikrofon: Aufnahme starten → sprechen → erneut klicken zum Stoppen → Text prüfen → Senden.",
    en: "Mic: tap to record → speak → tap to stop → review text → Send.",
    ar: "الميكروفون: اضغط للتسجيل → تحدّث → اضغط للإيقاف → راجع النص → أرسل.",
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

  function browserSpeechAvailable() {
    const SpeechRecognition = global.SpeechRecognition || global.webkitSpeechRecognition;
    return Boolean(SpeechRecognition && global.isSecureContext);
  }

  function preferWhisperTranscription(options) {
    if (options?.useWhisper === true) return true;
    if (options?.useWhisper === false) return false;
    if (options?.multilingual !== false) return true;
    return !browserSpeechAvailable();
  }

  function isWeakTranscript(text) {
    const cleaned = String(text || "").trim();
    if (!cleaned || cleaned.length < 2) return true;
    return /^[.\s,;:!?…\-–—'"`]+$/.test(cleaned);
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
    const text = String(data.text || "").trim();
    if (isWeakTranscript(text)) {
      const err = new Error("no_speech_detected");
      err.payload = { error: "no_speech_detected" };
      throw err;
    }
    return text;
  }

  function inferOpenAiVoiceError(err) {
    const code = String(err?.payload?.error || err?.message || "").trim();
    const hint = String(err?.payload?.hint || "").trim();
    if (code === "openai_quota_exceeded" || code === "openai_auth_error" || code === "openai_rate_limit") {
      return code;
    }
    const blob = `${code} ${hint}`;
    if (blob.includes("insufficient_quota") || blob.includes("exceeded your current quota")) {
      return "openai_quota_exceeded";
    }
    if (hint.startsWith("{")) {
      try {
        const parsed = JSON.parse(hint);
        const oai = parsed?.error?.code || parsed?.error?.type || "";
        if (oai === "insufficient_quota") return "openai_quota_exceeded";
        if (oai === "invalid_api_key" || oai === "authentication_error") return "openai_auth_error";
        if (oai === "rate_limit_exceeded") return "openai_rate_limit";
      } catch {
        // ignore invalid JSON hint
      }
    }
    return code;
  }

  function isWhisperServerError(err) {
    const code = inferOpenAiVoiceError(err);
    return [
      "openai_quota_exceeded",
      "openai_not_configured",
      "openai_auth_error",
      "openai_rate_limit",
      "whisper_http_error",
      "whisper_failed",
    ].includes(code);
  }

  function voiceErrorMessage(err, lang) {
    const code = inferOpenAiVoiceError(err);
    const hint = String(err?.payload?.hint || "").trim();
    const ui = resolveLang(lang);
    if (code === "not-allowed" || code === "service-not-allowed") {
      return ui === "ar"
        ? "تم حظر الميكروفون — اسمح بالوصول في المتصفح."
        : ui === "en"
          ? "Microphone blocked — allow access in the browser."
          : "Mikrofon blockiert — Browser-Berechtigung erlauben.";
    }
    if (code === "no-speech" || code === "no_speech_detected" || code === "audio_too_short") {
      return ui === "ar"
        ? "لم يُسمع صوت — حاول مرة أخرى."
        : ui === "en"
          ? "No speech detected — try again."
          : "Keine Sprache erkannt — bitte erneut versuchen.";
    }
    if (code === "openai_quota_exceeded") {
      return ui === "ar"
        ? "رصيد OpenAI API منتهٍ. اشتراك ChatGPT Plus ≠ API — أضف رصيداً في platform.openai.com/settings/billing."
        : ui === "en"
          ? "OpenAI API quota exceeded. ChatGPT Plus ≠ API billing — add credits at platform.openai.com/settings/billing."
          : "OpenAI-API-Guthaben leer. ChatGPT Plus ≠ API — Billing unter platform.openai.com/settings/billing.";
    }
    if (code === "openai_auth_error") {
      return ui === "ar"
        ? "مفتاح OPENAI_API_KEY على السيرفر غير صالح."
        : ui === "en"
          ? "Invalid OPENAI_API_KEY on the server."
          : "Ungültiger OPENAI_API_KEY auf dem Server.";
    }
    if (code === "openai_rate_limit") {
      return ui === "ar"
        ? "حد طلبات OpenAI — انتظر قليلاً ثم أعد المحاولة."
        : ui === "en"
          ? "OpenAI rate limit — wait briefly and try again."
          : "OpenAI-Ratenlimit — kurz warten und erneut versuchen.";
    }
    if (code === "openai_not_configured") {
      return ui === "ar"
        ? "الصوت يحتاج OPENAI_API_KEY أو Azure (AZURE_OPENAI_WHISPER_DEPLOYMENT) على السيرفر."
        : ui === "en"
          ? "Voice needs OPENAI_API_KEY or Azure Whisper (AZURE_OPENAI_WHISPER_DEPLOYMENT) on the server."
          : "Spracheingabe braucht OPENAI_API_KEY oder Azure Whisper auf dem Server.";
    }
    if (code === "feature_not_available") {
      return ui === "ar"
        ? "المساعد الذكي يتطلب باقة Enterprise."
        : ui === "en"
          ? "AI assistant requires Enterprise plan."
          : "KI-Assistent braucht Enterprise-Tarif.";
    }
    if (hint && !hint.startsWith("{")) return hint;
    return ui === "ar" ? "فشل الإدخال الصوتي." : ui === "en" ? "Voice input failed." : "Spracheingabe fehlgeschlagen.";
  }

  function bindVoiceController(options, btnEl, inputEl) {
    const lang = resolveLang(options.lang);
    const speechLang = resolveSpeechLang(options);
    const ui = labelsForLang(lang);
    const maxRecordMs = Math.max(10000, Number(options.maxRecordMs) || DEFAULT_MAX_RECORD_MS);
    const minRecordMs = Math.max(300, Number(options.minRecordMs) || DEFAULT_MIN_RECORD_MS);
    let useWhisperMode = preferWhisperTranscription(options);

    let browserRecognition = null;
    let browserListening = false;
    let stream = null;
    let recorder = null;
    let recording = false;
    let recordStartedAt = 0;
    let maxRecordTimer = null;
    let chunks = [];
    let recordMimeType = "";

    const applyTranscript = (text, isFinal) => {
      const cleaned = String(text || "").trim();
      if (!cleaned) return;
      if (isFinal && isWeakTranscript(cleaned)) return;
      inputEl.value = cleaned;
      inputEl.dispatchEvent(new Event("input", { bubbles: true }));
      if (!isFinal) return;
      inputEl.dataset.bpVoiceInput = "1";
      inputEl.focus?.();
      if (typeof options.onTranscript === "function") {
        options.onTranscript(cleaned);
      } else if (options.autoSubmit === true) {
        inputEl.form?.requestSubmit?.();
      }
    };

    const notifyError = (err, kind) => {
      const wrapped = err instanceof Error ? err : new Error(String(err || "voice_error"));
      if (kind === "mic" && typeof options.onMicError === "function") {
        options.onMicError(wrapped);
        return;
      }
      if (typeof options.onTranscribeError === "function") {
        options.onTranscribeError(wrapped);
        return;
      }
      if (typeof options.onError === "function") {
        options.onError(wrapped);
        return;
      }
      global.console?.warn?.("BaupassAiUi voice", kind, wrapped);
    };

    const stopBrowser = () => {
      try {
        browserRecognition?.stop?.();
      } catch {
        // ignore
      }
      browserListening = false;
      setListeningState(btnEl, false, lang);
    };

    const startBrowser = () => {
      const SpeechRecognition = global.SpeechRecognition || global.webkitSpeechRecognition;
      if (!SpeechRecognition || !global.isSecureContext) return false;

      browserRecognition = new SpeechRecognition();
      browserRecognition.lang = options.multilingual !== false
        ? (String(global.navigator?.language || "").trim() || speechLang)
        : speechLang;
      browserRecognition.continuous = false;
      browserRecognition.interimResults = options.interimResults !== false;
      browserRecognition.maxAlternatives = 1;

      browserRecognition.onstart = () => {
        browserListening = true;
        setListeningState(btnEl, true, lang);
        if (typeof options.onListening === "function") options.onListening(true);
      };
      browserRecognition.onend = () => {
        browserListening = false;
        setListeningState(btnEl, false, lang);
        if (typeof options.onListening === "function") options.onListening(false);
      };
      browserRecognition.onerror = (event) => {
        browserListening = false;
        setListeningState(btnEl, false, lang);
        const code = String(event?.error || "");
        if (code && code !== "aborted") {
          notifyError(new Error(code), "speech");
        }
      };
      browserRecognition.onresult = (event) => {
        let finalText = "";
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const part = event.results[i][0]?.transcript || "";
          if (event.results[i].isFinal) finalText += part;
          else interim += part;
        }
        const display = (finalText || interim).trim();
        if (display) applyTranscript(display, false);
        if (finalText.trim()) applyTranscript(finalText.trim(), true);
      };

      try {
        browserRecognition.start();
        return true;
      } catch (err) {
        notifyError(err, "speech");
        return false;
      }
    };

    const cleanupRecording = () => {
      if (maxRecordTimer) {
        global.clearTimeout(maxRecordTimer);
        maxRecordTimer = null;
      }
      stream?.getTracks?.().forEach((track) => track.stop());
      stream = null;
      recording = false;
      setListeningState(btnEl, false, lang);
      if (typeof options.onListening === "function") options.onListening(false);
      if (typeof options.onTranscribing === "function") options.onTranscribing(false);
    };

    const stopWhisperRecording = () => {
      if (!recorder || recorder.state === "inactive") return;
      try {
        if (typeof recorder.requestData === "function") recorder.requestData();
      } catch {
        // ignore
      }
      recorder.stop();
    };

    const transcribeRecording = async () => {
      const mimeType = recordMimeType || recorder?.mimeType || pickRecorderMimeType() || "audio/webm";
      const blob = new Blob(chunks, { type: mimeType });
      chunks = [];
      recorder = null;
      cleanupRecording();
      if (!blob.size || blob.size < MIN_AUDIO_BYTES) {
        notifyError(new Error("audio_too_short"), "transcribe");
        return;
      }
      if (Date.now() - recordStartedAt < minRecordMs) {
        notifyError(new Error("audio_too_short"), "transcribe");
        return;
      }
      try {
        btnEl.classList.add("bp-ai-transcribing");
        if (typeof options.onTranscribing === "function") options.onTranscribing(true);
        const text = await transcribeWithWhisper(blob, options);
        applyTranscript(text, true);
      } catch (err) {
        if (options.fallbackToBrowser !== false && isWhisperServerError(err) && browserSpeechAvailable()) {
          useWhisperMode = false;
          const fallbackMsg = resolveLang(lang) === "ar"
            ? "تعذّر التفريغ على السيرفر — تحدّث مرة أخرى (صوت المتصفح، لغات محدودة)."
            : resolveLang(lang) === "en"
              ? "Server transcription unavailable — speak again (browser voice, limited languages)."
              : "Server-Transkription nicht verfügbar — erneut sprechen (Browser-Sprache, begrenzte Sprachen).";
          notifyError(Object.assign(new Error("whisper_fallback"), { payload: { error: "whisper_fallback", hint: fallbackMsg } }), "transcribe");
          if (startBrowser()) return;
        }
        notifyError(err, "transcribe");
      } finally {
        btnEl.classList.remove("bp-ai-transcribing");
        if (typeof options.onTranscribing === "function") options.onTranscribing(false);
      }
    };

    const startWhisperRecording = async () => {
      if (!global.navigator?.mediaDevices?.getUserMedia || !global.MediaRecorder) {
        return false;
      }
      try {
        chunks = [];
        stream = await global.navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });
        recordMimeType = pickRecorderMimeType();
        recorder = recordMimeType
          ? new global.MediaRecorder(stream, { mimeType: recordMimeType })
          : new global.MediaRecorder(stream);
        recordStartedAt = Date.now();
        recorder.ondataavailable = (event) => {
          if (event.data && event.data.size > 0) chunks.push(event.data);
        };
        recorder.onstop = () => {
          void transcribeRecording();
        };
        recorder.start();
        recording = true;
        setListeningState(btnEl, true, lang);
        if (typeof options.onListening === "function") options.onListening(true);
        maxRecordTimer = global.setTimeout(() => {
          if (recording) stopWhisperRecording();
        }, maxRecordMs);
        return true;
      } catch (err) {
        cleanupRecording();
        notifyError(err, "mic");
        return false;
      }
    };

    btnEl.addEventListener("click", async () => {
      if (browserListening) {
        stopBrowser();
        return;
      }
      if (recording) {
        stopWhisperRecording();
        return;
      }

      if (useWhisperMode) {
        const started = await startWhisperRecording();
        if (!started) {
          btnEl.disabled = true;
          btnEl.title = options.unsupportedHint || ui.unsupported;
        }
        return;
      }
      if (!startBrowser()) {
        const started = await startWhisperRecording();
        if (!started) {
          btnEl.disabled = true;
          btnEl.title = options.unsupportedHint || ui.unsupported;
        }
      }
    });
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

    if (btnEl.dataset.bpVoiceBound === "1") {
      refreshComposerLabels(options);
      return;
    }
    btnEl.dataset.bpVoiceBound = "1";

    if (!browserSpeechAvailable() && !global.navigator?.mediaDevices?.getUserMedia) {
      btnEl.disabled = true;
      btnEl.title = options.unsupportedHint || labelsForLang(options.lang).unsupported;
      return;
    }

    bindVoiceController(options, btnEl, inputEl);
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
    voiceErrorMessage,
    browserSpeechAvailable,
    transcribeWithWhisper,
  };
})(window);
