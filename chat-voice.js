/**
 * SUPPIX chat voice notes — WhatsApp-style mic/send toggle and audio bubbles.
 */
(function initSuppixChatVoice(global) {
  const MIC_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" stroke="currentColor" stroke-width="2"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;
  const SEND_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h12M13 7l5 5-5 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  const STOP_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor"/></svg>`;
  const PLAY_SVG = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 7.5v9l8-4.5-8-4.5Z" fill="currentColor"/></svg>`;
  const PAUSE_SVG = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="7" y="6" width="3.5" height="12" fill="currentColor"/><rect x="13.5" y="6" width="3.5" height="12" fill="currentColor"/></svg>`;

  function isSupported() {
    return Boolean(global.navigator?.mediaDevices?.getUserMedia && global.MediaRecorder);
  }

  function pickMimeType() {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/aac",
      "audio/ogg;codecs=opus",
      "audio/ogg",
    ];
    for (const mime of candidates) {
      try {
        if (global.MediaRecorder.isTypeSupported(mime)) return mime;
      } catch {
        /* ignore */
      }
    }
    return "";
  }

  function extensionForMime(mime) {
    const clean = String(mime || "").toLowerCase();
    if (clean.includes("mp4") || clean.includes("aac")) return "m4a";
    if (clean.includes("ogg")) return "ogg";
    return "webm";
  }

  function formatDuration(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    return `${mins}:${String(secs).padStart(2, "0")}`;
  }

  function isAudioAttachment(filename, contentType) {
    const mime = String(contentType || "").toLowerCase();
    if (/^audio\//i.test(mime)) return true;
    return /\.(webm|m4a|mp4|ogg|mp3|wav|aac)$/i.test(String(filename || ""));
  }

  function escapeAttr(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function setButtonIcon(button, svg, label) {
    if (!button) return;
    button.innerHTML = svg;
    if (label) {
      button.setAttribute("aria-label", label);
      button.title = label;
    }
  }

  function composeHasText(input, placeholder) {
    const raw = String(input?.value || "").trim();
    const ph = String(placeholder || "").trim();
    if (!raw) return false;
    if (ph && raw === ph) return false;
    return true;
  }

  function updateComposePrimaryAction({ input, button, fileInput, recording, labels = {} }) {
    if (!button) return "mic";
    const sendLabel = labels.send || "Send";
    const micLabel = labels.mic || "Voice message";
    const stopLabel = labels.stop || "Stop recording";
    button.classList.remove("is-recording");
    if (recording) {
      button.dataset.mode = "stop";
      setButtonIcon(button, STOP_SVG, stopLabel);
      button.classList.add("is-recording");
      return "stop";
    }
    const hasText = composeHasText(input, labels.placeholder);
    const hasFile = Boolean(fileInput?.files?.length);
    if (hasText || hasFile) {
      button.dataset.mode = "send";
      setButtonIcon(button, SEND_SVG, sendLabel);
      return "send";
    }
    button.disabled = false;
    button.dataset.mode = "mic";
    setButtonIcon(button, MIC_SVG, micLabel);
    return "mic";
  }

  function createRecorder({ onTick, onError } = {}) {
    let stream = null;
    let recorder = null;
    let chunks = [];
    let mimeType = "";
    let startedAt = 0;
    let timer = null;

    const cleanupStream = () => {
      if (stream) {
        stream.getTracks().forEach((track) => {
          try {
            track.stop();
          } catch {
            /* ignore */
          }
        });
      }
      stream = null;
    };

    const stopTimer = () => {
      if (timer) {
        global.clearInterval(timer);
        timer = null;
      }
    };

    return {
      get recording() {
        return Boolean(recorder && recorder.state === "recording");
      },
      async start() {
        if (!isSupported()) {
          throw new Error("voice_not_supported");
        }
        chunks = [];
        mimeType = pickMimeType();
        stream = await global.navigator.mediaDevices.getUserMedia({ audio: true });
        try {
          recorder = mimeType ? new global.MediaRecorder(stream, { mimeType }) : new global.MediaRecorder(stream);
        } catch (error) {
          cleanupStream();
          throw error;
        }
        recorder.ondataavailable = (event) => {
          if (event?.data?.size) chunks.push(event.data);
        };
        recorder.onerror = (event) => {
          onError?.(event?.error || new Error("voice_record_failed"));
        };
        recorder.start(250);
        startedAt = Date.now();
        stopTimer();
        timer = global.setInterval(() => {
          const seconds = (Date.now() - startedAt) / 1000;
          onTick?.(seconds);
        }, 250);
      },
      async stop() {
        if (!recorder) {
          cleanupStream();
          stopTimer();
          return null;
        }
        const activeRecorder = recorder;
        const result = await new Promise((resolve, reject) => {
          activeRecorder.onstop = () => {
            const outMime = activeRecorder.mimeType || mimeType || "audio/webm";
            const blob = chunks.length ? new Blob(chunks, { type: outMime }) : null;
            resolve(blob);
          };
          activeRecorder.onerror = (event) => reject(event?.error || new Error("voice_record_failed"));
          try {
            if (activeRecorder.state !== "inactive") activeRecorder.stop();
          } catch (error) {
            reject(error);
          }
        });
        stopTimer();
        cleanupStream();
        recorder = null;
        chunks = [];
        if (!result || !result.size) {
          return null;
        }
        if (result.size < 900) {
          return null;
        }
        return result;
      },
      cancel() {
        stopTimer();
        try {
          if (recorder && recorder.state !== "inactive") recorder.stop();
        } catch {
          /* ignore */
        }
        recorder = null;
        chunks = [];
        cleanupStream();
      },
      toFile(blob, filenamePrefix) {
        if (!blob) return null;
        const ext = extensionForMime(blob.type);
        const name = `${filenamePrefix || "voice"}-${Date.now()}.${ext}`;
        try {
          return new File([blob], name, { type: blob.type || "audio/webm" });
        } catch {
          return new Blob([blob], { type: blob.type || "audio/webm" });
        }
      },
    };
  }

  function renderAudioPlayerHtml(attachment, labels = {}) {
    const id = escapeAttr(attachment?.id || "");
    const filename = escapeAttr(attachment?.filename || labels.voice || "voice.webm");
    const contentType = escapeAttr(attachment?.contentType || attachment?.content_type || "audio/webm");
    const e2eMeta = escapeAttr(attachment?.e2eMeta || attachment?.e2e_meta || "");
    const voiceLabel = escapeAttr(labels.voice || "Voice message");
    return `<div class="chat-audio-player" data-attachment-id="${id}" data-filename="${filename}" data-content-type="${contentType}" data-e2e-meta="${e2eMeta}">
      <button type="button" class="chat-audio-play" aria-label="${voiceLabel}">${PLAY_SVG}</button>
      <div class="chat-audio-track" aria-hidden="true"><span class="chat-audio-progress"></span></div>
      <span class="chat-audio-duration">0:00</span>
    </div>`;
  }

  const audioCache = new Map();
  let activeAudio = null;
  let activePlayBtn = null;

  async function resolveAudioUrl(attachmentId, meta, downloadFn) {
    const cacheKey = `${attachmentId}:${meta || ""}`;
    if (audioCache.has(cacheKey)) {
      return audioCache.get(cacheKey);
    }
    const payload = await downloadFn(attachmentId, meta);
    const url = global.URL.createObjectURL(payload.blob);
    audioCache.set(cacheKey, { url, duration: payload.duration || 0 });
    return audioCache.get(cacheKey);
  }

  function resetActiveAudio() {
    if (activeAudio) {
      try {
        activeAudio.pause();
      } catch {
        /* ignore */
      }
    }
    if (activePlayBtn) {
      activePlayBtn.classList.remove("is-playing");
      activePlayBtn.innerHTML = PLAY_SVG;
    }
    activeAudio = null;
    activePlayBtn = null;
  }

  function hydrateAudioPlayers(root, { downloadFn, onError } = {}) {
    if (!root || typeof downloadFn !== "function") return;
    root.querySelectorAll(".chat-audio-player:not([data-audio-bound])").forEach((player) => {
      player.dataset.audioBound = "1";
      const playBtn = player.querySelector(".chat-audio-play");
      const progress = player.querySelector(".chat-audio-progress");
      const durationEl = player.querySelector(".chat-audio-duration");
      const attachmentId = player.getAttribute("data-attachment-id") || "";
      const meta = player.getAttribute("data-e2e-meta") || "";
      if (!playBtn || !attachmentId) return;
      playBtn.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        try {
          if (activePlayBtn === playBtn && activeAudio && !activeAudio.paused) {
            activeAudio.pause();
            playBtn.classList.remove("is-playing");
            playBtn.innerHTML = PLAY_SVG;
            activeAudio = null;
            activePlayBtn = null;
            return;
          }
          resetActiveAudio();
          const cached = await resolveAudioUrl(attachmentId, meta, downloadFn);
          const audio = new Audio(cached.url);
          activeAudio = audio;
          activePlayBtn = playBtn;
          playBtn.classList.add("is-playing");
          playBtn.innerHTML = PAUSE_SVG;
          if (durationEl && cached.duration) {
            durationEl.textContent = formatDuration(cached.duration);
          }
          audio.addEventListener("timeupdate", () => {
            if (!progress || !audio.duration) return;
            progress.style.width = `${Math.min(100, (audio.currentTime / audio.duration) * 100)}%`;
            if (durationEl) durationEl.textContent = formatDuration(audio.currentTime);
          });
          audio.addEventListener("ended", () => {
            playBtn.classList.remove("is-playing");
            playBtn.innerHTML = PLAY_SVG;
            if (progress) progress.style.width = "0%";
            if (durationEl && cached.duration) durationEl.textContent = formatDuration(cached.duration);
            activeAudio = null;
            activePlayBtn = null;
          });
          await audio.play();
        } catch (error) {
          resetActiveAudio();
          onError?.(error);
        }
      });
    });
  }

  global.SUPPIXChatVoice = {
    MIC_SVG,
    SEND_SVG,
    STOP_SVG,
    isSupported,
    pickMimeType,
    formatDuration,
    isAudioAttachment,
    composeHasText,
    updateComposePrimaryAction,
    createRecorder,
    renderAudioPlayerHtml,
    hydrateAudioPlayers,
    resetActiveAudio,
  };
})(typeof window !== "undefined" ? window : globalThis);
