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

  const SPEAKER_SVG = `<svg class="bp-ai-speaker-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>`;

  const VOICE_REPLY_KEY = "baupass-ai-voice-reply";
  const voiceCaptureByInputId = new Map();

  const DEFAULT_MAX_RECORD_MS = 300000;
  const DEFAULT_MIN_RECORD_MS = 600;
  const MIN_AUDIO_BYTES = 800;
  const RECORD_TIMESLICE_MS = 500;

  const HINTS = {
    de: "Mikrofon: tippen → sprechen (Text erscheint live) → erneut tippen → Senden.",
    en: "Mic: tap → speak (text appears live) → tap again → Send.",
    ar: "الميكروفون: اضغط → تحدّث (النص يظهر مباشرة) → اضغط للإيقاف → أرسل.",
  };

  const LABELS = {
    de: {
      speak: "Spracheingabe",
      stop: "Aufnahme beenden",
      send: "Senden",
      voiceReplyOn: "Sprachausgabe an — KI antwortet mit Stimme",
      voiceReplyOff: "Sprachausgabe aus — nur Text",
      voiceReplyStop: "Vorlesen stoppen",
      voiceSpeakingHint: "KI spricht — 🔊 tippen zum Stoppen",
      voicePreparingHint: "Sprachausgabe wird vorbereitet…",
      unsupported: "Spracheingabe benötigt HTTPS",
      open: "Öffnen",
    },
    en: {
      speak: "Voice input",
      stop: "Stop listening",
      send: "Send",
      voiceReplyOn: "Voice reply on — AI speaks answers",
      voiceReplyOff: "Voice reply off — text only",
      voiceReplyStop: "Stop speaking",
      voiceSpeakingHint: "AI is speaking — tap 🔊 to stop",
      voicePreparingHint: "Preparing voice reply…",
      unsupported: "Voice needs HTTPS",
      open: "Open",
    },
    ar: {
      speak: "إدخال صوتي",
      stop: "إيقاف الاستماع",
      send: "إرسال",
      voiceReplyOn: "رد صوتي مفعّل — الذكاء الاصطناعي يرد بصوت",
      voiceReplyOff: "رد صوتي متوقف — نص فقط",
      voiceReplyStop: "إيقاف القراءة",
      voiceSpeakingHint: "الذكاء الاصطناعي يتحدّث — اضغط 🔊 للإيقاف",
      voicePreparingHint: "جاري تجهيز الرد الصوتي…",
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

  function resolveLiveSpeechLang(options) {
    const uiLang = resolveLang(options?.lang);
    return LANG_MAP[uiLang] || resolveSpeechLang(options);
  }

  function preferWhisperTranscription(options) {
    if (options?.useWhisper === true) return true;
    if (options?.useWhisper === false) return false;
    const uiLang = resolveLang(options?.lang);
    if (uiLang === "ar") return true;
    if (options?.multilingual !== false) return true;
    return !browserSpeechAvailable();
  }

  function resolveWhisperLang(options) {
    const uiLang = resolveLang(options?.lang);
    if (uiLang === "ar") return "ar";
    if (options?.multilingual === false) return uiLang;
    return "auto";
  }

  function isWeakTranscript(text) {
    const cleaned = String(text || "").trim();
    if (!cleaned || cleaned.length < 2) return true;
    if (/[\u0600-\u06FF]/.test(cleaned)) return false;
    return /^[.\s,;:!?…\-–—'"`]+$/.test(cleaned);
  }

  function isVoiceReplyEnabled() {
    try {
      const stored = global.localStorage?.getItem(VOICE_REPLY_KEY);
      if (stored === "0" || stored === "false") return false;
      return true;
    } catch {
      return true;
    }
  }

  function setVoiceReplyEnabled(on) {
    try {
      global.localStorage?.setItem(VOICE_REPLY_KEY, on ? "1" : "0");
    } catch {
      // ignore
    }
    global.dispatchEvent(new CustomEvent("baupass-ai-voice-reply-toggle", { detail: { enabled: Boolean(on) } }));
  }

  function ttsAvailable() {
    return Boolean(global.speechSynthesis && typeof global.SpeechSynthesisUtterance === "function");
  }

  function voiceReplySupported() {
    return typeof global.fetch === "function" || ttsAvailable();
  }

  function stripMarkdown(text) {
    let s = String(text || "");
    s = s.replace(/```[\s\S]*?```/g, " ");
    s = s.replace(/`([^`]+)`/g, "$1");
    s = s.replace(/!\[[^\]]*\]\([^)]*\)/g, " ");
    s = s.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1");
    s = s.replace(/^#{1,6}\s+/gm, "");
    s = s.replace(/^\s*[-*+•]\s+/gm, "");
    s = s.replace(/^\s*\d+[.)]\s+/gm, "");
    s = s.replace(/\*\*([^*]+)\*\*/g, "$1");
    s = s.replace(/\*([^*]+)\*/g, "$1");
    s = s.replace(/_{1,2}([^_]+)_{1,2}/g, "$1");
    s = s.replace(/https?:\/\/\S+/gi, " ");
    return s;
  }

  function dropMetaSections(text) {
    const lines = String(text || "").split("\n");
    const metaRe = /^(quelle|sources?|tools?|werkzeuge|referenz|hinweis|metadata|kontext)\s*[:：]/i;
    const out = [];
    let inMeta = false;
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        if (!inMeta) out.push("");
        continue;
      }
      if (metaRe.test(trimmed)) {
        inMeta = true;
        continue;
      }
      if (inMeta && /^[-*•\d]/.test(trimmed)) continue;
      inMeta = false;
      out.push(line);
    }
    return out.join("\n");
  }

  function truncateSentences(text, maxSentences) {
    const cleaned = String(text || "").replace(/\s+/g, " ").trim();
    if (!maxSentences || maxSentences <= 0) return cleaned;
    const parts = cleaned.split(/(?<=[.!?؟…])\s+/);
    if (parts.length <= maxSentences) return cleaned;
    return parts.slice(0, maxSentences).join(" ").trim();
  }

  function cleanTextForSpeech(text, options = {}) {
    let s = dropMetaSections(stripMarkdown(text));
    s = s.replace(/\s+/g, " ").trim();
    if (!s || isWeakTranscript(s)) return "";
    const uiLang = resolveLang(options.lang);
    const isAr = uiLang === "ar";
    const maxSentences = options.maxSentences ?? (options.spoken ? (isAr ? 8 : 6) : 8);
    s = truncateSentences(s, maxSentences);
    const maxChars = options.maxChars ?? (options.spoken && isAr ? 1200 : (options.spoken ? 900 : 0));
    if (maxChars > 0 && s.length > maxChars) {
      const cut = s.slice(0, maxChars);
      const breakAt = Math.max(
        cut.lastIndexOf("؟"),
        cut.lastIndexOf("."),
        cut.lastIndexOf("!"),
        cut.lastIndexOf("?"),
        cut.lastIndexOf("،"),
      );
      s = breakAt > 40 ? cut.slice(0, breakAt + 1).trim() : `${cut.trim()}…`;
    }
    if (s.length <= 2800) return s;
    const cut = s.slice(0, 2600);
    const breakAt = Math.max(cut.lastIndexOf("."), cut.lastIndexOf("!"), cut.lastIndexOf("?"), cut.lastIndexOf("؟"));
    return `${breakAt > 400 ? cut.slice(0, breakAt + 1) : cut}…`;
  }

  function cleanTextForDisplay(text, options = {}) {
    return cleanTextForSpeech(text, { spoken: true, maxSentences: options.maxSentences || 12, ...options });
  }

  function cleanQuestionText(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
  }

  function resolveInputId(inputEl, options) {
    return String(options?.inputId || inputEl?.id || "").trim() || null;
  }

  function stopVoiceCapture(inputIdOrOptions) {
    const id = typeof inputIdOrOptions === "string"
      ? inputIdOrOptions
      : resolveInputId(null, inputIdOrOptions || {});
    if (!id) return false;
    const ctrl = voiceCaptureByInputId.get(id);
    if (!ctrl) return false;
    ctrl.stopCapture();
    return true;
  }

  function isVoiceCaptureActive(inputIdOrOptions) {
    const id = typeof inputIdOrOptions === "string"
      ? inputIdOrOptions
      : resolveInputId(null, inputIdOrOptions || {});
    if (!id) return false;
    const ctrl = voiceCaptureByInputId.get(id);
    return Boolean(ctrl?.isActive?.());
  }

  function consumeVoiceInputFlag(inputEl) {
    if (!inputEl) return false;
    const flagged = inputEl.dataset?.bpVoiceInput === "1";
    if (flagged) delete inputEl.dataset.bpVoiceInput;
    return flagged;
  }

  function voiceScore(voice, ttsLang, prefix) {
    const name = String(voice.name || "");
    const lang = String(voice.lang || "").toLowerCase();
    let score = 0;
    if (lang === ttsLang.toLowerCase()) score += 50;
    else if (lang.startsWith(prefix)) score += 30;
    if (/neural|natural|online|premium|enhanced|wavenet|google.*network|microsoft.*online|azure/i.test(name)) {
      score += 40;
    }
    if (!voice.localService) score += 20;
    if (/female|zira|sabina|anna|nova|alloy|shimmer|samantha|moira/i.test(name)) score += 5;
    return score;
  }

  function pickVoiceForLang(lang) {
    if (!ttsAvailable()) return null;
    const voices = global.speechSynthesis.getVoices();
    if (!voices.length) return null;
    const uiLang = resolveLang(lang);
    const ttsLang = LANG_MAP[uiLang] || resolveSpeechLang({ lang });
    const prefix = ttsLang.split("-")[0].toLowerCase();
    const matching = voices.filter((v) => String(v.lang || "").toLowerCase().startsWith(prefix));
    const pool = matching.length ? matching : voices;
    if (uiLang === "ar" && !matching.length) {
      const arVoices = voices.filter((v) => String(v.lang || "").toLowerCase().startsWith("ar"));
      if (arVoices.length) {
        return arVoices.reduce((best, voice) => {
          if (!best) return voice;
          return voiceScore(voice, "ar-SA", "ar") > voiceScore(best, "ar-SA", "ar") ? voice : best;
        }, null);
      }
    }
    return pool.reduce((best, voice) => {
      if (!best) return voice;
      return voiceScore(voice, ttsLang, prefix) > voiceScore(best, ttsLang, prefix) ? voice : best;
    }, null);
  }

  function prepareSpeechText(text, options = {}) {
    return cleanTextForSpeech(text, options);
  }

  let currentSpeechUtterance = null;
  let currentAudio = null;
  let currentAudioUrl = null;

  function stopSpeaking() {
    try {
      global.speechSynthesis?.cancel();
    } catch {
      // ignore
    }
    currentSpeechUtterance = null;
    if (currentAudio) {
      try {
        currentAudio.pause();
      } catch {
        // ignore
      }
      currentAudio = null;
    }
    if (currentAudioUrl) {
      try {
        URL.revokeObjectURL(currentAudioUrl);
      } catch {
        // ignore
      }
      currentAudioUrl = null;
    }
    global.dispatchEvent(new CustomEvent("baupass-ai-speaking", { detail: { speaking: false } }));
  }

  function isSpeaking() {
    try {
      if (currentAudio && !currentAudio.paused) return true;
      return Boolean(global.speechSynthesis?.speaking || global.speechSynthesis?.pending);
    } catch {
      return false;
    }
  }

  function ensureVoicesLoaded(callback) {
    if (!ttsAvailable()) return;
    const voices = global.speechSynthesis.getVoices();
    if (voices.length) {
      callback();
      return;
    }
    const onVoices = () => {
      global.speechSynthesis.removeEventListener("voiceschanged", onVoices);
      callback();
    };
    global.speechSynthesis.addEventListener("voiceschanged", onVoices);
    global.setTimeout(() => {
      global.speechSynthesis.removeEventListener("voiceschanged", onVoices);
      callback();
    }, 1200);
  }

  function playAudioBlob(blob, mimeType, options = {}) {
    return new Promise((resolve) => {
      const type = mimeType || blob.type || "audio/mpeg";
      const url = URL.createObjectURL(new Blob([blob], { type }));
      currentAudioUrl = url;
      const audio = new Audio(url);
      currentAudio = audio;
      if (!options.keepAlive) {
        dispatchSpeakingState(true, { preparing: false });
      }
      const finish = (ok) => {
        if (currentAudioUrl === url) {
          try {
            URL.revokeObjectURL(url);
          } catch {
            // ignore
          }
          currentAudioUrl = null;
        }
        if (currentAudio === audio) currentAudio = null;
        if (!options.keepAlive) {
          dispatchSpeakingState(false);
        }
        resolve(ok);
      };
      audio.onended = () => finish(true);
      audio.onerror = () => finish(false);
      audio.play().then(() => {}).catch(() => finish(false));
    });
  }

  function buildSpeakBody(text, lang, options = {}) {
    const ui = resolveLang(lang);
    const fast = options.fast !== false && (ui === "ar" || Boolean(options.spoken));
    return {
      text,
      lang: ui,
      fast,
      stream: false,
    };
  }

  const ttsTurn = {
    locked: false,
    segmentsDone: 0,
    prefetch: null,
    playPromise: null,
  };

  function resetTtsTurn() {
    ttsTurn.locked = false;
    ttsTurn.segmentsDone = 0;
    ttsTurn.prefetch = null;
    ttsTurn.playPromise = null;
  }

  function splitSpeechSegments(text, lang, options = {}) {
    const ui = resolveLang(lang);
    const full = cleanTextForSpeech(text, {
      spoken: true,
      lang,
      maxSentences: options.maxSentences ?? (ui === "ar" ? 8 : 6),
      maxChars: options.maxChars ?? (ui === "ar" ? 1200 : 900),
    });
    if (!full) return [];
    const sentences = full.split(/(?<=[.!?؟…])\s+/).filter(Boolean);
    const maxChunk = ui === "ar" ? 240 : 300;
    const segments = [];
    let buf = "";
    for (const sentence of sentences) {
      const next = buf ? `${buf} ${sentence}` : sentence;
      if (next.length <= maxChunk) {
        buf = next;
        continue;
      }
      if (buf) segments.push(buf.trim());
      buf = sentence.length <= maxChunk ? sentence : `${sentence.slice(0, maxChunk).trim()}…`;
    }
    if (buf.trim()) segments.push(buf.trim());
    return segments;
  }

  function isOpenAiTtsBillingError(result) {
    const code = String(result?.error || "").trim();
    if (["openai_quota_exceeded", "openai_auth_error", "openai_not_configured", "openai_rate_limit"].includes(code)) {
      return true;
    }
    const hint = String(result?.hint || "");
    return /insufficient_quota|exceeded your current quota|invalid_api_key|authentication_error/i.test(hint);
  }

  function fetchTtsBlob(text, lang, options = {}) {
    const url = options.speakUrl || "/api/ai/speak";
    return fetch(url, {
      method: "POST",
      credentials: "include",
      headers: buildSpeakHeaders(options),
      body: JSON.stringify(buildSpeakBody(text, lang, { ...options, spoken: true })),
    })
      .then(async (res) => {
        if (!res.ok) {
          let payload = null;
          try {
            payload = await res.json();
          } catch {
            payload = null;
          }
          const detail = {
            error: payload?.error || "tts_failed",
            hint: payload?.hint || "",
            status: res.status,
          };
          if (!options.suppressTtsErrorEvent) {
            global.dispatchEvent(new CustomEvent("baupass-ai-tts-error", { detail }));
          }
          return detail;
        }
        const mime = res.headers.get("Content-Type") || "audio/mpeg";
        const blob = await res.blob();
        if (!blob?.size) {
          const detail = { error: "tts_empty", hint: "", status: res.status };
          if (!options.suppressTtsErrorEvent) {
            global.dispatchEvent(new CustomEvent("baupass-ai-tts-error", { detail }));
          }
          return detail;
        }
        return { blob, mime };
      })
      .catch((err) => {
        const detail = { error: "tts_failed", hint: String(err?.message || err), status: 0 };
        if (!options.suppressTtsErrorEvent) {
          global.dispatchEvent(new CustomEvent("baupass-ai-tts-error", { detail }));
        }
        return detail;
      });
  }

  function scheduleTtsAutoplay(prefetch) {
    if (!prefetch?.fetchPromise || ttsTurn.playPromise) return;
    ttsTurn.playPromise = prefetch.fetchPromise.then(async (result) => {
      if (!result?.blob?.size) return false;
      ttsTurn.segmentsDone = 1;
      dispatchSpeakingState(true, { preparing: false });
      return playAudioBlob(result.blob, result.mime, { keepAlive: true });
    }).catch(() => false);
  }

  function tryLockTtsPrefetch(text, lang, options = {}) {
    if (ttsTurn.locked) return ttsTurn.prefetch;
    const raw = String(text || "").trim();
    const segments = splitSpeechSegments(raw, lang, options);
    if (!segments.length || segments[0].length < 10) return null;
    const hasBoundary = /[.!?؟…](?:\s|$)/.test(raw);
    if (!hasBoundary && raw.length < 44) return null;

    ttsTurn.locked = true;
    const prepared = segments[0];
    const fetchPromise = fetchTtsBlob(prepared, lang, options);
    ttsTurn.prefetch = { prepared, fetchPromise, mime: "audio/mpeg" };
    dispatchSpeakingState(true, { preparing: true });
    scheduleTtsAutoplay(ttsTurn.prefetch);
    return ttsTurn.prefetch;
  }

  async function speakRemainingSegments(segments, lang, options, startIdx) {
    let playedAny = false;
    let billingError = false;
    const segOpts = { ...options, suppressTtsErrorEvent: true };
    for (let i = startIdx; i < segments.length; i++) {
      dispatchSpeakingState(true, { preparing: true });
      const part = await fetchTtsBlob(segments[i], lang, segOpts);
      if (!part?.blob?.size) {
        if (isOpenAiTtsBillingError(part)) billingError = true;
        continue;
      }
      dispatchSpeakingState(true, { preparing: false });
      ttsTurn.segmentsDone = i + 1;
      const ok = await playAudioBlob(part.blob, part.mime, { keepAlive: i < segments.length - 1 });
      if (ok) playedAny = true;
    }
    return { playedAny, billingError };
  }

  async function speakWithOpenAi(text, lang, options = {}) {
    try {
      dispatchSpeakingState(true, { preparing: true });
      const result = await fetchTtsBlob(text, lang, options);
      if (!result?.blob?.size) {
        dispatchSpeakingState(false);
        return false;
      }
      dispatchSpeakingState(true, { preparing: false });
      return playAudioBlob(result.blob, result.mime, { keepAlive: Boolean(options.keepAlive) });
    } catch {
      dispatchSpeakingState(false);
      return false;
    }
  }

  function speakWithBrowser(text, lang, options = {}) {
    if (!ttsAvailable()) return false;
    const utter = new global.SpeechSynthesisUtterance(text);
    const ttsLang = LANG_MAP[resolveLang(lang)] || resolveSpeechLang({ lang });
    utter.lang = ttsLang;
    utter.rate = Number(options.rate) || 0.94;
    utter.pitch = Number(options.pitch) || 1;
    utter.volume = Number(options.volume) || 1;
    const voice = pickVoiceForLang(lang);
    if (voice) utter.voice = voice;
    utter.onend = () => {
      currentSpeechUtterance = null;
      dispatchSpeakingState(false);
    };
    utter.onerror = () => stopSpeaking();
    currentSpeechUtterance = utter;
    dispatchSpeakingState(true);
    global.speechSynthesis.speak(utter);
    return true;
  }

  function speakWithBrowserAsync(text, lang, options = {}) {
    return new Promise((resolve) => {
      if (!ttsAvailable()) {
        resolve(false);
        return;
      }
      const utter = new global.SpeechSynthesisUtterance(text);
      const ttsLang = LANG_MAP[resolveLang(lang)] || resolveSpeechLang({ lang });
      utter.lang = ttsLang;
      utter.rate = Number(options.rate) || 0.94;
      utter.pitch = Number(options.pitch) || 1;
      utter.volume = Number(options.volume) || 1;
      const voice = pickVoiceForLang(lang);
      if (voice) utter.voice = voice;
      utter.onend = () => {
        currentSpeechUtterance = null;
        dispatchSpeakingState(false);
        resolve(true);
      };
      utter.onerror = () => {
        stopSpeaking();
        resolve(false);
      };
      currentSpeechUtterance = utter;
      dispatchSpeakingState(true);
      global.speechSynthesis.speak(utter);
    });
  }

  async function tryBrowserTtsFallback(text, lang, options, billingError) {
    if (!billingError && !options.forceBrowserFallback) return false;
    if (!ttsAvailable()) return false;
    const full = splitSpeechSegments(text, lang, options).join(" ");
    if (!full) return false;
    const ok = await speakWithBrowserAsync(full, lang, options);
    if (ok) {
      global.dispatchEvent(new CustomEvent("baupass-ai-tts-fallback", {
        detail: { reason: billingError ? "openai_billing" : "tts_failed", lang: resolveLang(lang) },
      }));
    }
    return ok;
  }

  async function speakReply(text, lang, options = {}) {
    const spoken = Boolean(options.spoken);
    if (!options.force && !spoken && !isVoiceReplyEnabled()) return false;

    const segments = splitSpeechSegments(text, lang, options);
    if (!segments.length) return false;

    if (ttsTurn.playPromise) {
      await ttsTurn.playPromise;
      const rest = splitSpeechSegments(text, lang, options);
      const start = Math.max(ttsTurn.segmentsDone, 1);
      if (start < rest.length) {
        const { playedAny, billingError } = await speakRemainingSegments(rest, lang, options, start);
        if (!playedAny) {
          return tryBrowserTtsFallback(text, lang, options, billingError);
        }
      }
      dispatchSpeakingState(false);
      return true;
    }

    stopSpeaking();
    dispatchSpeakingState(true, { preparing: true });
    const { playedAny, billingError } = await speakRemainingSegments(segments, lang, options, 0);
    if (playedAny) {
      dispatchSpeakingState(false);
      return true;
    }
    const browserOk = await tryBrowserTtsFallback(text, lang, options, billingError);
    if (!browserOk && billingError) {
      global.dispatchEvent(new CustomEvent("baupass-ai-tts-error", {
        detail: { error: "openai_quota_exceeded" },
      }));
    }
    dispatchSpeakingState(false);
    return browserOk;
  }

  async function speakText(text, lang, options = {}) {
    return speakReply(text, lang, options);
  }

  function dispatchSpeakingState(speaking, extra = {}) {
    global.dispatchEvent(new CustomEvent("baupass-ai-speaking", { detail: { speaking, ...extra } }));
  }

  function buildSpeakHeaders(options = {}) {
    const headers = { "Content-Type": "application/json" };
    if (typeof options.authHeaders === "function") {
      Object.assign(headers, options.authHeaders());
    } else if (options.authHeaders && typeof options.authHeaders === "object") {
      Object.assign(headers, options.authHeaders);
    }
    return headers;
  }

  function markTtsPreparing() {
    dispatchSpeakingState(true, { preparing: true });
  }

  function beginTtsPrefetch(text, lang, options = {}) {
    return tryLockTtsPrefetch(text, lang, options);
  }

  async function playPrefetchedSpeech(prefetch, finalPrepared) {
    if (!prefetch?.fetchPromise || !finalPrepared) return false;
    const result = await prefetch.fetchPromise;
    if (!result?.blob?.size) return false;
    dispatchSpeakingState(true, { preparing: false });
    return playAudioBlob(result.blob, result.mime || prefetch.mime);
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
    const whisperLang = resolveWhisperLang(options);
    const res = await fetch(url, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({
        audio: audioB64,
        mime: blob.type || "audio/webm",
        multilingual: whisperLang === "auto" ? multilingual : false,
        lang: whisperLang,
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
    const code = String(err?.payload?.error || err?.error || err?.message || "").trim();
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
    if (code === "elevenlabs_not_configured") {
      return ui === "ar"
        ? "الصوت يحتاج ELEVENLABS_API_KEY على Railway ثم إعادة نشر (Redeploy) السيرفر."
        : ui === "en"
          ? "Voice needs ELEVENLABS_API_KEY on Railway, then redeploy the server."
          : "Sprache braucht ELEVENLABS_API_KEY auf Railway und anschließend Redeploy.";
    }
    if (code === "elevenlabs_http_error") {
      return ui === "ar"
        ? "خطأ ElevenLabs — تحقق من المفتاح والرصيد في elevenlabs.io."
        : ui === "en"
          ? "ElevenLabs error — check API key and credits at elevenlabs.io."
          : "ElevenLabs-Fehler — API-Key und Guthaben auf elevenlabs.io prüfen.";
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
    let liveRecognition = null;
    let liveRecognitionActive = false;
    let liveDraftFinal = "";
    let transcribeAborted = false;

    const abortTranscribe = () => {
      transcribeAborted = true;
      btnEl.classList.remove("bp-ai-transcribing");
      if (typeof options.onTranscribing === "function") options.onTranscribing(false);
    };

    const stopCapture = () => {
      transcribeAborted = true;
      if (browserListening) {
        stopBrowser();
      }
      if (recording) {
        recording = false;
        liveRecognitionActive = false;
        try {
          liveRecognition?.stop?.();
        } catch {
          // ignore
        }
        liveRecognition = null;
        if (maxRecordTimer) {
          global.clearTimeout(maxRecordTimer);
          maxRecordTimer = null;
        }
        if (recorder && recorder.state !== "inactive") {
          recorder.onstop = () => {
            chunks = [];
            recorder = null;
            cleanupRecording();
          };
          try {
            if (typeof recorder.requestData === "function") recorder.requestData();
          } catch {
            // ignore
          }
          try {
            recorder.stop();
          } catch {
            cleanupRecording();
          }
        } else {
          cleanupRecording();
        }
      } else {
        abortTranscribe();
      }
      setListeningState(btnEl, false, lang);
    };

    const inputId = resolveInputId(inputEl, options);
    if (inputId) {
      voiceCaptureByInputId.set(inputId, {
        stopCapture,
        isActive: () => Boolean(
          recording
          || browserListening
          || btnEl.classList.contains("bp-ai-transcribing")
          || btnEl.classList.contains("listening"),
        ),
      });
    }

    const startLiveSpeechPreview = () => {
      if (options.liveSpeechDuringRecord === false) return;
      const SpeechRecognition = global.SpeechRecognition || global.webkitSpeechRecognition;
      if (!SpeechRecognition || !global.isSecureContext) return;
      liveDraftFinal = inputEl.value.trim();
      liveRecognition = new SpeechRecognition();
      liveRecognition.lang = resolveLiveSpeechLang(options);
      liveRecognition.continuous = true;
      liveRecognition.interimResults = true;
      liveRecognition.maxAlternatives = 1;
      liveRecognition.onresult = (event) => {
        let interim = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const part = event.results[i][0]?.transcript || "";
          if (event.results[i].isFinal) {
            liveDraftFinal = `${liveDraftFinal} ${part}`.trim();
          } else {
            interim += part;
          }
        }
        const display = `${liveDraftFinal}${interim ? ` ${interim}` : ""}`.trim();
        if (display) applyTranscript(display, false);
      };
      liveRecognition.onend = () => {
        if (recording && liveRecognitionActive) {
          try {
            liveRecognition.start();
          } catch {
            // ignore restart races
          }
        }
      };
      liveRecognition.onerror = () => {
        // Whisper + saved draft remain the fallback; stay quiet during live preview.
      };
      try {
        liveRecognition.start();
        liveRecognitionActive = true;
      } catch {
        liveRecognition = null;
        liveRecognitionActive = false;
      }
    };

    const stopLiveSpeechPreview = () => {
      liveRecognitionActive = false;
      try {
        liveRecognition?.stop?.();
      } catch {
        // ignore
      }
      liveRecognition = null;
      const fromInput = inputEl.value.trim();
      if (fromInput.length >= liveDraftFinal.length) {
        liveDraftFinal = fromInput;
      }
      return liveDraftFinal.trim();
    };

    const applyDraftIfUsable = (draft) => {
      const cleaned = String(draft || "").trim();
      if (!cleaned || isWeakTranscript(cleaned)) return false;
      applyTranscript(cleaned, true);
      return true;
    };

    const applyTranscript = (text, isFinal) => {
      const cleaned = cleanQuestionText(text);
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
      stopSpeaking();
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
      liveRecognitionActive = false;
      try {
        liveRecognition?.stop?.();
      } catch {
        // ignore
      }
      liveRecognition = null;
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
      if (transcribeAborted) {
        chunks = [];
        recorder = null;
        cleanupRecording();
        return;
      }
      const savedLive = stopLiveSpeechPreview();
      const mimeType = recordMimeType || recorder?.mimeType || pickRecorderMimeType() || "audio/webm";
      const blob = new Blob(chunks, { type: mimeType });
      chunks = [];
      recorder = null;
      cleanupRecording();
      if (!blob.size || blob.size < MIN_AUDIO_BYTES) {
        if (applyDraftIfUsable(savedLive)) return;
        notifyError(new Error("audio_too_short"), "transcribe");
        return;
      }
      if (Date.now() - recordStartedAt < minRecordMs) {
        if (applyDraftIfUsable(savedLive)) return;
        notifyError(new Error("audio_too_short"), "transcribe");
        return;
      }
      const liveDraft = String(savedLive || inputEl.value || "").trim();
      if (options.preferLiveDraft !== false && applyDraftIfUsable(liveDraft)) {
        return;
      }
      try {
        btnEl.classList.add("bp-ai-transcribing");
        if (typeof options.onTranscribing === "function") options.onTranscribing(true);
        const text = await transcribeWithWhisper(blob, options);
        applyTranscript(text, true);
      } catch (err) {
        if (applyDraftIfUsable(savedLive || inputEl.value)) return;
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
      stopSpeaking();
      transcribeAborted = false;
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
        recorder.start(RECORD_TIMESLICE_MS);
        recording = true;
        startLiveSpeechPreview();
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
      if (isSpeaking()) {
        stopSpeaking();
        return;
      }
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

  function enhanceVoiceReplyButton(btnEl, lang) {
    if (!btnEl || btnEl.dataset.bpSpeakerEnhanced === "1") return btnEl;
    if (!voiceReplySupported()) {
      btnEl.disabled = true;
      btnEl.hidden = true;
      return btnEl;
    }
    btnEl.dataset.bpSpeakerEnhanced = "1";
    btnEl.type = "button";
    btnEl.classList.add("bp-ai-speaker");
    btnEl.innerHTML = SPEAKER_SVG;
    const syncState = () => {
      const ui = labelsForLang(lang);
      const on = isVoiceReplyEnabled();
      const speaking = isSpeaking();
      btnEl.classList.toggle("voice-reply-on", on);
      btnEl.classList.toggle("speaking", speaking);
      btnEl.setAttribute("aria-pressed", on ? "true" : "false");
      if (speaking) {
        btnEl.title = ui.voiceReplyStop;
        btnEl.setAttribute("aria-label", ui.voiceReplyStop);
      } else if (on) {
        btnEl.title = ui.voiceReplyOn;
        btnEl.setAttribute("aria-label", ui.voiceReplyOn);
      } else {
        btnEl.title = ui.voiceReplyOff;
        btnEl.setAttribute("aria-label", ui.voiceReplyOff);
      }
    };
    btnEl.addEventListener("click", () => {
      if (isSpeaking()) {
        stopSpeaking();
        syncState();
        return;
      }
      setVoiceReplyEnabled(!isVoiceReplyEnabled());
      syncState();
    });
    global.addEventListener("baupass-ai-speaking", syncState);
    global.addEventListener("baupass-ai-voice-reply-toggle", syncState);
    ensureVoicesLoaded(syncState);
    syncState();
    return btnEl;
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
        if (options.voiceReply !== false && voiceReplySupported()) {
          const replyId = options.replyButtonId || "aiVoiceReplyBtn";
          let replyBtn = document.getElementById(replyId);
          if (!replyBtn) {
            replyBtn = document.createElement("button");
            replyBtn.id = replyId;
          }
          enhanceVoiceReplyButton(replyBtn, lang);
          toolbar.appendChild(replyBtn);
        }
        if (sendEl) toolbar.appendChild(sendEl);
      } else if (options.voiceReply !== false && voiceReplySupported()) {
        const replyId = options.replyButtonId || "aiVoiceReplyBtn";
        if (!document.getElementById(replyId)) {
          const replyBtn = document.createElement("button");
          replyBtn.id = replyId;
          enhanceVoiceReplyButton(replyBtn, lang);
          if (sendEl && sendEl.parentElement === toolbar) {
            toolbar.insertBefore(replyBtn, sendEl);
          } else {
            toolbar.appendChild(replyBtn);
          }
        }
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
    } else if (row) {
      row.classList.add("bp-ai-composer");
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

    const hookSendStop = () => {
      stopVoiceCapture(resolveInputId(inputEl, options));
    };
    if (formEl && formEl.dataset.bpVoiceSendHook !== "1") {
      formEl.dataset.bpVoiceSendHook = "1";
      formEl.addEventListener("submit", hookSendStop, true);
    }
    if (sendEl && sendEl.dataset.bpVoiceSendHook !== "1") {
      sendEl.dataset.bpVoiceSendHook = "1";
      sendEl.addEventListener("click", hookSendStop, true);
    }

    const hintEl = document.getElementById(options.hintId || "bpAiComposerHint");
    if (hintEl && hintEl.dataset.bpSpeakingHint !== "1") {
      hintEl.dataset.bpSpeakingHint = "1";
      const defaultHint = hintEl.textContent;
      global.addEventListener("baupass-ai-speaking", (ev) => {
        if (ev.detail?.speaking) {
          const ui = labelsForLang(lang);
          hintEl.textContent = ev.detail?.preparing
            ? (options.preparingHintText || ui.voicePreparingHint)
            : (options.speakingHintText || ui.voiceSpeakingHint);
          hintEl.classList.add("bp-ai-hint-speaking");
        } else {
          hintEl.textContent = options.hintText || HINTS[lang] || HINTS.de || defaultHint;
          hintEl.classList.remove("bp-ai-hint-speaking");
        }
      });
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
    const replyBtn = document.getElementById(options.replyButtonId || "aiVoiceReplyBtn");
    if (replyBtn) {
      enhanceVoiceReplyButton(replyBtn, lang);
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
    ttsAvailable,
    voiceReplySupported,
    isVoiceReplyEnabled,
    setVoiceReplyEnabled,
    cleanQuestionText,
    cleanTextForSpeech,
    cleanTextForDisplay,
    consumeVoiceInputFlag,
    stopVoiceCapture,
    isVoiceCaptureActive,
    speakReply,
    speakText,
    beginTtsPrefetch,
    tryLockTtsPrefetch,
    resetTtsTurn,
    markTtsPreparing,
    stopSpeaking,
    isSpeaking,
  };
})(window);
