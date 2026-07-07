/**
 * SUPPIX chat voice notes — WhatsApp-style mic/send toggle and inline voice bubbles.
 */
(function initSuppixChatVoice(global) {
  const MIC_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" stroke="currentColor" stroke-width="2"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;
  const SEND_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h12M13 7l5 5-5 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  const STOP_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor"/></svg>`;
  const PLAY_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 7.5v9l8-4.5-8-4.5Z" fill="currentColor"/></svg>`;
  const PAUSE_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="7" y="6" width="3.5" height="12" fill="currentColor"/><rect x="13.5" y="6" width="3.5" height="12" fill="currentColor"/></svg>`;

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

  function parseE2eAttachmentMime(e2eMeta) {
    const raw = String(e2eMeta || "").trim();
    if (!raw) return "";
    try {
      const meta = JSON.parse(raw);
      return String(meta?.mime || "");
    } catch {
      return "";
    }
  }

  function isAudioAttachment(filename, contentType, e2eMeta) {
    const e2eMime = parseE2eAttachmentMime(e2eMeta);
    const mime = String(contentType || e2eMime || "").toLowerCase().split(";")[0].trim();
    const name = String(filename || "").toLowerCase();
    if (/^audio\//i.test(mime)) return true;
    if (/^video\/webm$/i.test(mime) && /voice-/.test(name)) return true;
    if (/voice-/.test(name) && /\.(webm|m4a|mp4|ogg|aac|wav)(\.e2e)?$/i.test(name)) return true;
    if ((name.endsWith(".e2e") || mime.includes("e2e")) && /^audio\//i.test(e2eMime)) return true;
    return /\.(webm|m4a|mp4|ogg|mp3|wav|aac)$/i.test(name);
  }

  function isVoiceOnlyBody(body, voiceLabel) {
    const text = String(body || "").trim().toLowerCase();
    if (!text) return true;
    const label = String(voiceLabel || "sprachnachricht").trim().toLowerCase();
    return (
      text === label
      || text.includes("sprachnachricht")
      || text.includes("voice message")
      || text.includes("sesli mesaj")
      || text.includes("رسالة صوتية")
      || text.startsWith("🎤")
    );
  }

  function escapeAttr(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function voiceWaveformHtml(seed) {
    let hash = 0;
    const text = String(seed || "voice");
    for (let i = 0; i < text.length; i += 1) {
      hash = (hash + text.charCodeAt(i) * (i + 3)) % 9973;
    }
    const bars = [];
    for (let i = 0; i < 28; i += 1) {
      hash = (hash * 33 + i * 17) % 100;
      const height = 28 + (hash % 72);
      bars.push(`<span style="height:${height}%"></span>`);
    }
    return `<div class="chat-voice-wave" aria-hidden="true">${bars.join("")}</div>`;
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
        if (!result || !result.size || result.size < 900) {
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
    const side = escapeAttr(labels.side || "mine");
    return `<div class="chat-voice-note is-${side}" data-attachment-id="${id}" data-filename="${filename}" data-content-type="${contentType}" data-e2e-meta="${e2eMeta}">
      <button type="button" class="chat-voice-play" aria-label="${voiceLabel}">${PLAY_SVG}</button>
      ${voiceWaveformHtml(id || filename)}
      <span class="chat-voice-duration">0:00</span>
    </div>`;
  }

  const audioCache = new Map();
  let activeAudio = null;
  let activePlayer = null;

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
    if (activePlayer) {
      activePlayer.classList.remove("is-playing", "is-loading");
      const playBtn = activePlayer.querySelector(".chat-voice-play");
      if (playBtn) playBtn.innerHTML = PLAY_SVG;
    }
    activeAudio = null;
    activePlayer = null;
  }

  async function toggleVoicePlayback(player, { downloadFn, onError } = {}) {
    const playBtn = player.querySelector(".chat-voice-play");
    const progressWave = player.querySelector(".chat-voice-wave");
    const durationEl = player.querySelector(".chat-voice-duration");
    const attachmentId = player.getAttribute("data-attachment-id") || "";
    const meta = player.getAttribute("data-e2e-meta") || "";
    if (!playBtn || !attachmentId) return;

    if (activePlayer === player && activeAudio && !activeAudio.paused) {
      activeAudio.pause();
      player.classList.remove("is-playing");
      playBtn.innerHTML = PLAY_SVG;
      activeAudio = null;
      activePlayer = null;
      return;
    }

    resetActiveAudio();
    player.classList.add("is-loading");
    try {
      const cached = await resolveAudioUrl(attachmentId, meta, downloadFn);
      const audio = new Audio(cached.url);
      activeAudio = audio;
      activePlayer = player;
      player.classList.remove("is-loading");
      player.classList.add("is-playing");
      playBtn.innerHTML = PAUSE_SVG;
      if (durationEl && cached.duration) {
        durationEl.textContent = formatDuration(cached.duration);
      }
      audio.addEventListener("timeupdate", () => {
        if (!audio.duration) return;
        const ratio = Math.min(1, audio.currentTime / audio.duration);
        if (progressWave) {
          progressWave.style.setProperty("--voice-progress", String(ratio));
        }
        if (durationEl) {
          durationEl.textContent = formatDuration(audio.currentTime);
        }
      });
      audio.addEventListener("ended", () => {
        player.classList.remove("is-playing");
        playBtn.innerHTML = PLAY_SVG;
        if (progressWave) progressWave.style.setProperty("--voice-progress", "0");
        if (durationEl && cached.duration) {
          durationEl.textContent = formatDuration(cached.duration);
        }
        activeAudio = null;
        activePlayer = null;
      });
      await audio.play();
    } catch (error) {
      player.classList.remove("is-loading", "is-playing");
      playBtn.innerHTML = PLAY_SVG;
      resetActiveAudio();
      onError?.(error);
    }
  }

  function hydrateAudioPlayers(root, { downloadFn, onError } = {}) {
    if (!root || typeof downloadFn !== "function") return;
    root.querySelectorAll(".chat-voice-note:not([data-audio-bound])").forEach((player) => {
      player.dataset.audioBound = "1";
      const playBtn = player.querySelector(".chat-voice-play");
      if (!playBtn) return;
      const handler = (event) => {
        event.preventDefault();
        event.stopPropagation();
        void toggleVoicePlayback(player, { downloadFn, onError });
      };
      playBtn.addEventListener("click", handler);
      player.addEventListener("click", (event) => {
        if (event.target instanceof Element && event.target.closest(".chat-voice-play")) return;
        handler(event);
      });
    });
    root.querySelectorAll(".chat-audio-player:not([data-audio-bound])").forEach((player) => {
      player.dataset.audioBound = "1";
      player.classList.add("chat-voice-note");
      const playBtn = player.querySelector(".chat-audio-play");
      if (playBtn) {
        playBtn.classList.add("chat-voice-play");
        playBtn.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          void toggleVoicePlayback(player, { downloadFn, onError });
        });
      }
    });
  }

  function injectVoiceStyles() {
    const css = `
.chat-voice-note{display:flex;align-items:center;gap:10px;min-width:min(240px,78vw);max-width:100%;padding:6px 8px 6px 4px;border-radius:999px;cursor:pointer;user-select:none}
.chat-voice-note.is-mine,.bubble.admin .chat-voice-note{background:rgba(255,255,255,.14)}
.chat-voice-note.is-them,.bubble.worker .chat-voice-note{background:rgba(15,23,42,.08)}
.chat-voice-play{width:36px;height:36px;border-radius:50%;border:none;display:grid;place-items:center;flex-shrink:0;cursor:pointer;color:inherit;background:rgba(255,255,255,.22)}
.chat-voice-note.is-them .chat-voice-play,.bubble.worker .chat-voice-play{background:rgba(15,23,42,.08);color:#0f766e}
.chat-voice-note.is-mine .chat-voice-play,.bubble.admin .chat-voice-play{background:rgba(255,255,255,.24);color:#ecfeff}
.chat-voice-note.is-playing .chat-voice-play{transform:scale(1.03)}
.chat-voice-note.is-loading .chat-voice-play{opacity:.55}
.chat-voice-wave{--voice-progress:0;position:relative;display:flex;align-items:center;gap:2px;flex:1;min-width:84px;height:28px;overflow:hidden}
.chat-voice-wave::after{content:"";position:absolute;inset:0;width:calc(var(--voice-progress,0) * 100%);background:linear-gradient(90deg,rgba(94,234,212,.18),rgba(94,234,212,.34));pointer-events:none;border-radius:999px}
.chat-voice-wave span{display:block;width:3px;border-radius:999px;background:currentColor;opacity:.42;align-self:center}
.chat-voice-note.is-playing .chat-voice-wave span{opacity:.72}
.chat-voice-duration{font-size:.72rem;opacity:.82;min-width:2.3rem;text-align:end;font-variant-numeric:tabular-nums}
.bubble.is-voice-only .bubble-body{display:none}
.bubble.is-voice-only{padding:.35rem .55rem .35rem .35rem}
.worker-chat-bubble.is-voice-only .worker-chat-body{display:none}
.worker-chat-bubble.is-voice-only{padding:.4rem .55rem .35rem .45rem}
.chat-delete-btn,.worker-chat-delete-btn{border:none;background:transparent;cursor:pointer;opacity:.5;font-size:.85rem;padding:0 .15rem}
.chat-delete-btn:hover,.worker-chat-delete-btn:hover{opacity:1}
.worker-chat-bubble.is-company .chat-voice-note{background:rgba(15,23,42,.06)}
.worker-chat-bubble.is-company .chat-voice-play{background:rgba(194,65,12,.1);color:#c2410c}
.worker-chat-bubble.is-mine .chat-voice-note{background:rgba(37,99,235,.08)}
.worker-chat-bubble.is-mine .chat-voice-play{background:rgba(37,99,235,.14);color:#1d4ed8}
.chat-head-actions{display:flex;gap:.35rem;flex-wrap:wrap;margin-top:.35rem}
.chat-head-actions button{font-size:.72rem;padding:.28rem .5rem;border-radius:8px;border:1px solid var(--border);background:var(--input-bg);color:var(--text);cursor:pointer}
`;
    let style = global.document?.getElementById("suppixChatVoiceStyles");
    if (!style && global.document) {
      style = global.document.createElement("style");
      style.id = "suppixChatVoiceStyles";
      style.textContent = css;
      global.document.head.appendChild(style);
    } else if (style) {
      style.textContent = css;
    }
  }

  global.SUPPIXChatVoice = {
    MIC_SVG,
    SEND_SVG,
    STOP_SVG,
    isSupported,
    pickMimeType,
    formatDuration,
    isAudioAttachment,
    isVoiceOnlyBody,
    composeHasText,
    updateComposePrimaryAction,
    createRecorder,
    renderAudioPlayerHtml,
    hydrateAudioPlayers,
    resetActiveAudio,
  };
  injectVoiceStyles();
})(typeof window !== "undefined" ? window : globalThis);
