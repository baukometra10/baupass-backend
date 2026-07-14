/**
 * SUPPIX chat voice notes — WhatsApp-style mic/send toggle and inline voice bubbles.
 */
(function initSuppixChatVoice(global) {
  const MIC_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" stroke="currentColor" stroke-width="2"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;
  const SEND_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h12M13 7l5 5-5 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  const STOP_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor"/></svg>`;
  const PLAY_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 7.5v9l8-4.5-8-4.5Z" fill="currentColor"/></svg>`;
  const PAUSE_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="7" y="6" width="3.5" height="12" fill="currentColor"/><rect x="13.5" y="6" width="3.5" height="12" fill="currentColor"/></svg>`;

  function isAppleLikeDevice() {
    const ua = String(global.navigator?.userAgent || "");
    return /iPad|iPhone|iPod/i.test(ua)
      || (String(global.navigator?.platform || "") === "MacIntel" && Number(global.navigator?.maxTouchPoints || 0) > 1);
  }

  function ensureMediaDevices() {
    const nav = global.navigator;
    if (!nav) return false;
    if (!nav.mediaDevices) {
      nav.mediaDevices = {};
    }
    if (!nav.mediaDevices.getUserMedia) {
      const legacy = nav.getUserMedia || nav.webkitGetUserMedia || nav.mozGetUserMedia || nav.msGetUserMedia;
      if (legacy) {
        nav.mediaDevices.getUserMedia = (constraints) => new Promise((resolve, reject) => {
          legacy.call(nav, constraints, resolve, reject);
        });
      }
    }
    return Boolean(nav.mediaDevices?.getUserMedia);
  }

  async function requestAudioStream() {
    if (!global.isSecureContext) {
      throw new Error("voice_insecure_context");
    }
    if (!ensureMediaDevices()) {
      throw new Error("voice_not_supported");
    }
    const attempts = [
      { audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } },
      { audio: true },
      { audio: { channelCount: 1 } },
    ];
    let lastError = null;
    for (const constraints of attempts) {
      try {
        return await global.navigator.mediaDevices.getUserMedia(constraints);
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error("voice_record_failed");
  }

  function isTouchPrimaryDevice() {
    try {
      return Boolean(
        global.matchMedia?.("(pointer: coarse)")?.matches
        || Number(global.navigator?.maxTouchPoints || 0) > 0
        || "ontouchstart" in global
      );
    } catch {
      return false;
    }
  }

  function isStandalonePwa() {
    try {
      return Boolean(
        global.navigator?.standalone === true
        || global.matchMedia?.("(display-mode: standalone)")?.matches
        || global.matchMedia?.("(display-mode: fullscreen)")?.matches
      );
    } catch {
      return false;
    }
  }

  function isNativeCaptureAvailable() {
    return Boolean(global.document && isTouchPrimaryDevice());
  }

  function shouldPreferNativeVoiceCapture() {
    return false;
  }

  function micInputAvailable() {
    ensureMediaDevices();
    const nav = global.navigator;
    if (!global.isSecureContext || !nav) {
      return false;
    }
    if (nav.mediaDevices?.getUserMedia) {
      return true;
    }
    return Boolean(nav.getUserMedia || nav.webkitGetUserMedia || nav.mozGetUserMedia);
  }

  function hasMediaRecorder() {
    return Boolean(global.MediaRecorder);
  }

  function hasWebAudioRecording() {
    try {
      const Ctx = global.AudioContext || global.webkitAudioContext;
      if (!Ctx?.prototype?.createMediaStreamSource) {
        return false;
      }
      if (typeof Ctx.prototype.createScriptProcessor === "function") {
        return true;
      }
      return Boolean(Ctx.prototype.audioWorklet);
    } catch {
      return false;
    }
  }

  function canRecordVoice() {
    if (!micInputAvailable()) {
      return false;
    }
    if (hasMediaRecorder() || hasWebAudioRecording()) {
      return true;
    }
    // iOS home-screen web apps may expose capture APIs only after a user gesture.
    return isAppleLikeDevice();
  }

  function isLikelyVoiceCaptureFile(file) {
    if (!file) {
      return false;
    }
    const type = String(file.type || "").toLowerCase().split(";")[0].trim();
    if (type.startsWith("video/") || type.startsWith("image/")) {
      return false;
    }
    if (type.startsWith("audio/")) {
      return true;
    }
    const name = String(file.name || "").toLowerCase();
    return /\.(m4a|aac|mp3|wav|ogg|webm|caf)$/i.test(name);
  }

  function normalizeCaptureFile(file) {
    if (!file || !isLikelyVoiceCaptureFile(file)) {
      return null;
    }
    const rawType = String(file.type || "").toLowerCase().split(";")[0].trim();
    const inferredType = rawType.startsWith("audio/") ? rawType : "audio/mp4";
    const ext = extensionForMime(inferredType);
    const fallbackName = `voice-${Date.now()}.${ext}`;
    const currentName = String(file.name || "").trim();
    const name = /voice-|\.(m4a|mp4|webm|ogg|aac|wav|caf)$/i.test(currentName) ? currentName : fallbackName;
    try {
      const out = new File([file], name, { type: inferredType });
      return out;
    } catch {
      try {
        const out = new Blob([file], { type: inferredType });
        out.name = name;
        return out;
      } catch {
        return file;
      }
    }
  }

  function withTimeout(promise, ms, message = "voice_timeout") {
    let timer = null;
    const wrapped = Promise.resolve(promise);
    const timeoutPromise = new Promise((_, reject) => {
      timer = global.setTimeout(() => reject(new Error(message)), ms);
    });
    return Promise.race([wrapped, timeoutPromise]).finally(() => {
      if (timer) {
        global.clearTimeout(timer);
      }
    });
  }

  function isSupported() {
    return canRecordVoice();
  }

  function describeVoiceError(error) {
    const name = String(error?.name || "").trim();
    const message = String(error?.message || error || "").trim();
    if (message === "voice_insecure_context" || !global.isSecureContext) return "voice_insecure_context";
    if (message === "voice_not_supported" || message === "getUserMedia_not_supported") return "voice_not_supported";
    if (name === "NotAllowedError" || name === "PermissionDeniedError" || name === "SecurityError") return "voice_permission_denied";
    if (name === "NotFoundError" || name === "DevicesNotFoundError") return "voice_no_device";
    if (name === "NotReadableError" || name === "TrackStartError") return "voice_device_busy";
    if (message === "voice_permission_timeout" || message === "voice_timeout") return "voice_permission_timeout";
    if (name === "NotSupportedError" || message.includes("MediaRecorder")) return "voice_not_supported";
    return message || "voice_record_failed";
  }

  function pickMimeType() {
    const candidates = isAppleLikeDevice()
      ? [
        "audio/mp4",
        "audio/aac",
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
        "audio/ogg",
      ]
      : [
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

  function createMediaRecorder(stream, preferredMimeType = "") {
    const mimeCandidates = [];
    if (preferredMimeType) {
      mimeCandidates.push(preferredMimeType);
    }
    const picked = pickMimeType();
    if (picked && !mimeCandidates.includes(picked)) {
      mimeCandidates.push(picked);
    }
    const fallbackMimes = isAppleLikeDevice()
      ? ["audio/mp4", "audio/aac", "audio/webm;codecs=opus", "audio/webm", ""]
      : ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/aac", ""];
    fallbackMimes.forEach((mime) => {
      if (mime && !mimeCandidates.includes(mime)) {
        mimeCandidates.push(mime);
      }
    });
    const optionSets = mimeCandidates.map((mimeType) => ({ mimeType })).concat([{}]);
    let lastError = null;
    for (const options of optionSets) {
      try {
        const recorder = Object.keys(options).length && options.mimeType
          ? new global.MediaRecorder(stream, options)
          : new global.MediaRecorder(stream);
        return {
          recorder,
          mimeType: recorder.mimeType || options.mimeType || picked || "audio/mp4",
        };
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error("voice_not_supported");
  }

  function flushRecorderData(activeRecorder) {
    try {
      if (activeRecorder?.state === "recording" && typeof activeRecorder.requestData === "function") {
        activeRecorder.requestData();
      }
    } catch {
      /* ignore */
    }
  }

  function wait(ms) {
    return new Promise((resolve) => {
      global.setTimeout(resolve, ms);
    });
  }

  function extensionForMime(mime) {
    const clean = String(mime || "").toLowerCase();
    if (clean.includes("wav")) return "wav";
    if (clean.includes("mp4") || clean.includes("aac")) return "m4a";
    if (clean.includes("ogg")) return "ogg";
    return "webm";
  }

  function mergeFloat32Chunks(chunks) {
    const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
    const merged = new Float32Array(total);
    let offset = 0;
    chunks.forEach((chunk) => {
      merged.set(chunk, offset);
      offset += chunk.length;
    });
    return merged;
  }

  function float32ToPcm16(float32) {
    const out = new Int16Array(float32.length);
    for (let i = 0; i < float32.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, float32[i]));
      out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    return out;
  }

  function encodeWavBlob(float32Samples, sampleRate) {
    const pcm = float32ToPcm16(float32Samples);
    const dataLength = pcm.length * 2;
    const buffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(buffer);
    const writeString = (offset, text) => {
      for (let i = 0; i < text.length; i += 1) {
        view.setUint8(offset + i, text.charCodeAt(i));
      }
    };
    writeString(0, "RIFF");
    view.setUint32(4, 36 + dataLength, true);
    writeString(8, "WAVE");
    writeString(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, "data");
    view.setUint32(40, dataLength, true);
    let offset = 44;
    for (let i = 0; i < pcm.length; i += 1, offset += 2) {
      view.setInt16(offset, pcm[i], true);
    }
    return new Blob([buffer], { type: "audio/wav" });
  }

  function formatDuration(seconds) {
    const total = Math.max(0, Math.round(Number(seconds) || 0));
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    return `${mins}:${String(secs).padStart(2, "0")}`;
  }

  function parseE2eAttachmentMeta(e2eMeta) {
    const raw = String(e2eMeta || "").trim();
    if (!raw) return null;
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  function parseE2eAttachmentMime(e2eMeta) {
    return String(parseE2eAttachmentMeta(e2eMeta)?.mime || "");
  }

  function parseE2eAttachmentDuration(e2eMeta) {
    const sec = Number(parseE2eAttachmentMeta(e2eMeta)?.durationSec || 0);
    return Number.isFinite(sec) && sec > 0 ? Math.round(sec) : 0;
  }

  async function probeBlobDuration(blob) {
    if (!blob) return 0;
    try {
      const probe = new Audio(URL.createObjectURL(blob));
      const fromMeta = await new Promise((resolve) => {
        const finish = (value) => {
          URL.revokeObjectURL(probe.src);
          resolve(value);
        };
        probe.addEventListener("loadedmetadata", () => {
          const value = Number(probe.duration || 0);
          if (Number.isFinite(value) && value > 0 && value !== Infinity) {
            finish(Math.round(value));
            return;
          }
          finish(0);
        }, { once: true });
        probe.addEventListener("error", () => finish(0), { once: true });
      });
      if (fromMeta > 0) return fromMeta;
    } catch {
      /* fallback below */
    }
    try {
      if (global.AudioContext || global.webkitAudioContext) {
        const Ctx = global.AudioContext || global.webkitAudioContext;
        const ctx = new Ctx();
        const buffer = await blob.arrayBuffer();
        const audioBuffer = await ctx.decodeAudioData(buffer.slice(0));
        await ctx.close?.();
        return Math.max(1, Math.round(audioBuffer.duration || 0));
      }
    } catch {
      /* ignore */
    }
    return 0;
  }

  function parseE2eAttachmentFilename(e2eMeta) {
    return String(parseE2eAttachmentMeta(e2eMeta)?.filename || "");
  }

  function isAudioAttachment(filename, contentType, e2eMeta) {
    const metaFilename = parseE2eAttachmentFilename(e2eMeta).toLowerCase();
    const e2eMime = parseE2eAttachmentMime(e2eMeta);
    const mime = String(contentType || e2eMime || "").toLowerCase().split(";")[0].trim();
    const name = String(filename || "").toLowerCase();
    const voiceName = metaFilename || name;
    if (/^video\//i.test(mime)) return false;
    if (/^audio\//i.test(mime)) return true;
    if (/^video\/webm$/i.test(mime) && /voice[-_]/.test(voiceName)) return true;
    if (/voice[-_]/.test(voiceName) && /\.(webm|m4a|mp4|ogg|aac|wav|caf)(\.e2e)?$/i.test(voiceName)) return true;
    if ((name.endsWith(".e2e") || mime.includes("e2e")) && /^audio\//i.test(e2eMime)) return true;
    return /\.(webm|m4a|ogg|mp3|wav|aac|caf)$/i.test(name) || /\.(webm|m4a|ogg|mp3|wav|aac|caf)$/i.test(metaFilename);
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

  function asUploadFile(blob, filenamePrefix, durationSec, fallbackDuration) {
    if (!blob || !blob.size) return null;
    const ext = extensionForMime(blob.type);
    const name = `${filenamePrefix || "voice"}-${Date.now()}.${ext}`;
    const duration = Math.max(0, Math.round(Number(durationSec ?? fallbackDuration ?? 0) || 0));
    try {
      const file = new File([blob], name, { type: blob.type || "audio/webm" });
      if (duration > 0) file.durationSec = duration;
      return file;
    } catch {
      const out = new Blob([blob], { type: blob.type || "audio/webm" });
      out.name = name;
      if (duration > 0) out.durationSec = duration;
      return out;
    }
  }

  function bindWhatsAppVoiceCompose({
    root,
    input,
    sendBtn,
    micBtn,
    fileInput,
    recorder,
    labels = {},
    onSendText,
    onSendVoice,
    onRecordingTick,
    onError,
  }) {
    if (!root || !micBtn || !recorder) return () => {};
    const holdMs = 0;
    const cancelSlidePx = 72;
    let recording = false;
    let holdTimer = null;
    let pointerId = null;
    let startX = 0;
    let cancelArmed = false;

    let overlay = root.querySelector(".chat-voice-record-overlay");
    if (!overlay) {
      overlay = global.document.createElement("div");
      overlay.className = "chat-voice-record-overlay hidden";
      overlay.innerHTML = `
        <div class="chat-voice-record-panel">
          <span class="chat-voice-record-cancel">${labels.slideCancel || "← Zum Abbrechen wischen"}</span>
          <span class="chat-voice-record-timer">0:00</span>
          <div class="chat-voice-record-live-wave" aria-hidden="true"></div>
        </div>`;
      root.appendChild(overlay);
      const wave = overlay.querySelector(".chat-voice-record-live-wave");
      if (wave && !wave.childElementCount) {
        wave.innerHTML = Array.from({ length: 24 }, () => "<span></span>").join("");
      }
    }
    const timerEl = overlay.querySelector(".chat-voice-record-timer");
    const cancelEl = overlay.querySelector(".chat-voice-record-cancel");

    const syncSendBtn = () => {
      if (!sendBtn) return;
      const hasText = composeHasText(input, labels.placeholder);
      const hasFile = Boolean(fileInput?.files?.length);
      const showSend = (hasText || hasFile) && !recording;
      sendBtn.hidden = !showSend;
      sendBtn.disabled = recording;
    };

    const setRecordingUi = (active) => {
      recording = active;
      micBtn.classList.toggle("is-recording", active);
      root.classList.toggle("is-voice-recording", active);
      overlay.classList.toggle("hidden", !active);
      syncSendBtn();
    };

    const updateWave = (seconds) => {
      const wave = overlay.querySelector(".chat-voice-record-live-wave");
      if (timerEl) timerEl.textContent = formatDuration(seconds);
      if (!wave) return;
      wave.querySelectorAll("span").forEach((bar, index) => {
        const phase = (Date.now() / 110 + index * 0.42) % (Math.PI * 2);
        const height = 22 + Math.abs(Math.sin(phase)) * 58 + Math.min(18, seconds * 2);
        bar.style.height = `${Math.round(height)}%`;
      });
    };

    const finishRecording = async (sendIt) => {
      if (!recording) return;
      setRecordingUi(false);
      let blob = null;
      try {
        blob = await recorder.stop();
      } catch (error) {
        recorder.cancel?.();
        onError?.(error);
        return;
      }
      if (!sendIt || cancelArmed) {
        recorder.cancel?.();
        return;
      }
      const voiceFile = asUploadFile(blob, "voice", recorder.lastDurationSec, recorder.lastDurationSec);
      if (!voiceFile) {
        onError?.(new Error(labels.tooShort || "voice_too_short"));
        return;
      }
      try {
        await onSendVoice?.(voiceFile);
      } catch (error) {
        onError?.(error);
      }
    };

    const onMicDown = async (event) => {
      if (recording || pointerId !== null) return;
      if (event.button !== undefined && event.button !== 0) return;
      pointerId = event.pointerId ?? "mouse";
      startX = event.clientX || 0;
      cancelArmed = false;
      micBtn.setPointerCapture?.(event.pointerId);
      try {
        await recorder.start();
        setRecordingUi(true);
        updateWave(0);
        onRecordingTick?.(0);
      } catch (error) {
        pointerId = null;
        onError?.(error);
      }
    };

    const onMicMove = (event) => {
      if (!recording) return;
      const dx = (event.clientX || 0) - startX;
      cancelArmed = dx < -cancelSlidePx;
      if (cancelEl) {
        cancelEl.classList.toggle("is-armed", cancelArmed);
        cancelEl.textContent = cancelArmed
          ? (labels.releaseCancel || "Loslassen zum Abbrechen")
          : (labels.slideCancel || "← Zum Abbrechen wischen");
      }
    };

    const onMicUp = async (event) => {
      if (holdTimer) {
        global.clearTimeout(holdTimer);
        holdTimer = null;
      }
      try {
        micBtn.releasePointerCapture?.(event.pointerId);
      } catch {
        /* ignore */
      }
      if (!recording) {
        pointerId = null;
        return;
      }
      pointerId = null;
      await finishRecording(true);
    };

    micBtn.addEventListener("pointerdown", onMicDown);
    micBtn.addEventListener("pointermove", onMicMove);
    micBtn.addEventListener("pointerup", onMicUp);
    micBtn.addEventListener("pointercancel", onMicUp);
    micBtn.addEventListener("contextmenu", (event) => event.preventDefault());

    if (sendBtn) {
      sendBtn.addEventListener("click", () => {
        void onSendText?.();
      });
    }
    input?.addEventListener("input", syncSendBtn);
    fileInput?.addEventListener("change", syncSendBtn);
    syncSendBtn();

    return () => {
      micBtn.removeEventListener("pointerdown", onMicDown);
      micBtn.removeEventListener("pointermove", onMicMove);
      micBtn.removeEventListener("pointerup", onMicUp);
      micBtn.removeEventListener("pointercancel", onMicUp);
    };
  }

  function createRecorder({ onTick, onError } = {}) {
    let stream = null;
    let recorder = null;
    let chunks = [];
    let mimeType = "";
    let startedAt = 0;
    let timer = null;
    let lastDurationSec = 0;
    let recordingBackend = "";
    let audioContext = null;
    let audioProcessor = null;
    let audioSource = null;
    let silentGain = null;
    let wavChunks = [];
    let wavSampleRate = 44100;
    let wavCapturing = false;

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

    const cleanupWebAudio = async () => {
      wavCapturing = false;
      if (audioProcessor) {
        try {
          audioProcessor.onaudioprocess = null;
          audioProcessor.disconnect();
        } catch {
          /* ignore */
        }
      }
      if (audioSource) {
        try {
          audioSource.disconnect();
        } catch {
          /* ignore */
        }
      }
      if (silentGain) {
        try {
          silentGain.disconnect();
        } catch {
          /* ignore */
        }
      }
      audioProcessor = null;
      audioSource = null;
      silentGain = null;
      if (audioContext) {
        try {
          await audioContext.close?.();
        } catch {
          /* ignore */
        }
      }
      audioContext = null;
      wavChunks = [];
    };

    const stopTimer = () => {
      if (timer) {
        global.clearInterval(timer);
        timer = null;
      }
    };

    const beginRecordingTimer = () => {
      startedAt = Date.now();
      stopTimer();
      timer = global.setInterval(() => {
        const seconds = (Date.now() - startedAt) / 1000;
        onTick?.(seconds);
      }, 250);
    };

    const startWebAudioRecording = async (activeStream) => {
      const Ctx = global.AudioContext || global.webkitAudioContext;
      if (!Ctx) {
        throw new Error("voice_not_supported");
      }
      audioContext = new Ctx();
      if (audioContext.state === "suspended") {
        await audioContext.resume();
      }
      wavSampleRate = Number(audioContext.sampleRate) || 44100;
      audioSource = audioContext.createMediaStreamSource(activeStream);
      silentGain = audioContext.createGain();
      silentGain.gain.value = 0;
      audioProcessor = audioContext.createScriptProcessor(4096, 1, 1);
      wavChunks = [];
      wavCapturing = true;
      audioProcessor.onaudioprocess = (event) => {
        if (!wavCapturing) {
          return;
        }
        const channel = event.inputBuffer.getChannelData(0);
        wavChunks.push(new Float32Array(channel));
      };
      audioSource.connect(audioProcessor);
      audioProcessor.connect(silentGain);
      silentGain.connect(audioContext.destination);
      recordingBackend = "webaudio";
      mimeType = "audio/wav";
      beginRecordingTimer();
    };

    const startMediaRecorder = async (activeStream) => {
      mimeType = pickMimeType();
      const created = createMediaRecorder(activeStream, mimeType);
      recorder = created.recorder;
      mimeType = created.mimeType;
      const pushChunk = (event) => {
        if (event?.data?.size) {
          chunks.push(event.data);
        }
      };
      recorder.ondataavailable = pushChunk;
      recorder.onerror = (event) => {
        onError?.(event?.error || new Error("voice_record_failed"));
      };
      if (isAppleLikeDevice()) {
        try {
          recorder.start();
        } catch {
          recorder.start(1000);
        }
      } else {
        recorder.start(250);
      }
      await wait(isAppleLikeDevice() ? 250 : 80);
      if (!recorder || recorder.state !== "recording") {
        throw new Error("voice_record_failed");
      }
      recordingBackend = "mediarecorder";
      beginRecordingTimer();
    };

    return {
      get recording() {
        if (recordingBackend === "webaudio") {
          return wavCapturing;
        }
        return Boolean(recorder && recorder.state === "recording");
      },
      get lastDurationSec() {
        return lastDurationSec;
      },
      get elapsedMs() {
        return startedAt ? Math.max(0, Date.now() - startedAt) : 0;
      },
      async start(options = null) {
        if (!canRecordVoice()) {
          throw new Error("voice_not_supported");
        }
        const opts = options && typeof options === "object" ? options : {};
        stopTimer();
        if (recorder && recorder.state !== "inactive") {
          try {
            recorder.stop();
          } catch {
            /* ignore */
          }
        }
        await cleanupWebAudio();
        cleanupStream();
        recorder = null;
        chunks = [];
        recordingBackend = "";
        mimeType = "";
        lastDurationSec = 0;
        startedAt = 0;
        if (opts.stream instanceof global.MediaStream) {
          stream = opts.stream;
        } else if (opts.streamPromise) {
          stream = await withTimeout(Promise.resolve(opts.streamPromise), 12000, "voice_permission_timeout");
        } else {
          stream = await withTimeout(requestAudioStream(), 12000, "voice_permission_timeout");
        }
        const audioTracks = stream?.getAudioTracks?.() || [];
        if (!audioTracks.length || !audioTracks.some((track) => track.readyState === "live")) {
          cleanupStream();
          throw new Error("voice_device_busy");
        }
        audioTracks.forEach((track) => {
          track.enabled = true;
        });
        if (hasMediaRecorder()) {
          try {
            await startMediaRecorder(stream);
            return;
          } catch (error) {
            recorder = null;
            chunks = [];
            if (!hasWebAudioRecording()) {
              cleanupStream();
              throw error;
            }
          }
        }
        if (!hasWebAudioRecording()) {
          cleanupStream();
          throw new Error("voice_not_supported");
        }
        await startWebAudioRecording(stream);
      },
      async stop() {
        if (recordingBackend === "webaudio") {
          stopTimer();
          wavCapturing = false;
          const samples = mergeFloat32Chunks(wavChunks);
          const durationMs = startedAt ? Math.max(0, Date.now() - startedAt) : 0;
          lastDurationSec = durationMs ? Math.max(1, Math.round(durationMs / 1000)) : 0;
          startedAt = 0;
          await cleanupWebAudio();
          cleanupStream();
          recordingBackend = "";
          if (!samples.length || durationMs < 300) {
            lastDurationSec = 0;
            return null;
          }
          const blob = encodeWavBlob(samples, wavSampleRate);
          if (!blob.size) {
            lastDurationSec = 0;
            return null;
          }
          return blob;
        }
        if (!recorder) {
          cleanupStream();
          stopTimer();
          return null;
        }
        const activeRecorder = recorder;
        recorder = null;
        stopTimer();
        const collected = [...chunks];
        const pushChunk = (event) => {
          if (event?.data?.size) {
            collected.push(event.data);
          }
        };
        activeRecorder.ondataavailable = pushChunk;
        const result = await new Promise((resolve, reject) => {
          let settled = false;
          const finish = () => {
            if (settled) return;
            settled = true;
            const outMime = activeRecorder.mimeType || mimeType || "audio/webm";
            const blob = collected.length ? new Blob(collected, { type: outMime }) : null;
            resolve(blob);
          };
          const fail = (error) => {
            if (settled) return;
            settled = true;
            reject(error);
          };
          const settleDelay = isAppleLikeDevice() ? 320 : 80;
          const timeout = global.setTimeout(() => finish(), 5000);
          activeRecorder.onstop = () => {
            global.clearTimeout(timeout);
            global.setTimeout(finish, settleDelay);
          };
          activeRecorder.onerror = (event) => {
            global.clearTimeout(timeout);
            fail(event?.error || new Error("voice_record_failed"));
          };
          try {
            if (activeRecorder.state === "recording") {
              flushRecorderData(activeRecorder);
              activeRecorder.stop();
            } else {
              global.clearTimeout(timeout);
              finish();
            }
          } catch (error) {
            global.clearTimeout(timeout);
            fail(error);
          }
        });
        cleanupStream();
        chunks = [];
        lastDurationSec = startedAt ? Math.max(1, Math.round((Date.now() - startedAt) / 1000)) : 0;
        startedAt = 0;
        if (!result || !result.size) {
          lastDurationSec = 0;
          return null;
        }
        if (result.size < 256 && lastDurationSec < 1) {
          lastDurationSec = 0;
          return null;
        }
        return result;
      },
      cancel() {
        stopTimer();
        startedAt = 0;
        lastDurationSec = 0;
        wavCapturing = false;
        try {
          if (recorder && recorder.state !== "inactive") {
            recorder.stop();
          }
        } catch {
          /* ignore */
        }
        recorder = null;
        chunks = [];
        recordingBackend = "";
        void cleanupWebAudio();
        cleanupStream();
      },
      toFile(blob, filenamePrefix, durationSec) {
        if (!blob) return null;
        const ext = extensionForMime(blob.type);
        const name = `${filenamePrefix || "voice"}-${Date.now()}.${ext}`;
        const duration = Math.max(0, Math.round(Number(durationSec || lastDurationSec) || 0));
        try {
          const file = new File([blob], name, { type: blob.type || "audio/webm" });
          if (duration > 0) file.durationSec = duration;
          return file;
        } catch {
          const out = new Blob([blob], { type: blob.type || "audio/webm" });
          if (duration > 0) out.durationSec = duration;
          return out;
        }
      },
    };
  }

  function renderAudioPlayerHtml(attachment, labels = {}) {
    const id = escapeAttr(attachment?.id || "");
    const filename = escapeAttr(attachment?.filename || labels.voice || "voice.webm");
    const contentType = escapeAttr(attachment?.contentType || attachment?.content_type || "audio/webm");
    const voiceLabel = escapeAttr(labels.voice || "Voice message");
    const side = escapeAttr(labels.side || "mine");
    const e2eRaw = attachment?.e2eMeta || attachment?.e2e_meta || labels.e2eMeta || "";
    const knownDuration = Number(labels.durationSec || attachment?.durationSec || parseE2eAttachmentDuration(e2eRaw) || 0);
    const durationLabel = knownDuration > 0 ? formatDuration(knownDuration) : "0:00";
    return `<div class="chat-voice-note is-${side}" data-attachment-id="${id}" data-filename="${filename}" data-content-type="${contentType}"${knownDuration > 0 ? ` data-duration-sec="${knownDuration}"` : ""}>
      <button type="button" class="chat-voice-play" aria-label="${voiceLabel}">${PLAY_SVG}</button>
      ${voiceWaveformHtml(id || filename)}
      <span class="chat-voice-duration">${durationLabel}</span>
    </div>`;
  }

  const audioCache = new Map();
  let activeAudio = null;
  let activePlayer = null;

  function isEncryptedBlob(blob) {
    const mime = String(blob?.type || "").toLowerCase();
    return mime.includes("e2e") || mime === "application/octet-stream";
  }

  async function resolveAudioUrl(attachmentId, downloadFn) {
    const cacheKey = String(attachmentId || "");
    if (!cacheKey) {
      throw new Error("voice_attachment_missing");
    }
    if (audioCache.has(cacheKey)) {
      return audioCache.get(cacheKey);
    }
    const payload = await downloadFn(attachmentId);
    const mime = String(payload?.blob?.type || "").toLowerCase();
    if (!payload?.blob || (!mime.startsWith("audio/") && !mime.startsWith("video/webm") && isEncryptedBlob(payload.blob))) {
      throw new Error("voice_playback_failed");
    }
    let duration = Number(payload.duration || 0);
    if (!duration) {
      duration = await probeBlobDuration(payload.blob);
    }
    const url = global.URL.createObjectURL(payload.blob);
    audioCache.set(cacheKey, { url, duration, mime: payload.blob.type || "audio/webm" });
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
      const cached = await resolveAudioUrl(attachmentId, downloadFn);
      const audio = new Audio();
      audio.preload = "auto";
      audio.src = cached.url;
      activeAudio = audio;
      activePlayer = player;
      await new Promise((resolve, reject) => {
        const onReady = () => {
          audio.removeEventListener("loadedmetadata", onReady);
          audio.removeEventListener("error", onFail);
          resolve();
        };
        const onFail = () => {
          audio.removeEventListener("loadedmetadata", onReady);
          audio.removeEventListener("error", onFail);
          reject(new Error("voice_playback_failed"));
        };
        audio.addEventListener("loadedmetadata", onReady, { once: true });
        audio.addEventListener("error", onFail, { once: true });
        audio.load();
      });
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

  function prefetchVoiceDurations(root, { downloadFn } = {}) {
    if (!root || typeof downloadFn !== "function") return;
    root.querySelectorAll(".chat-voice-note[data-attachment-id]").forEach((player) => {
      const attachmentId = player.getAttribute("data-attachment-id") || "";
      const durationEl = player.querySelector(".chat-voice-duration");
      const preset = Number(player.getAttribute("data-duration-sec") || 0);
      if (!attachmentId || !durationEl || durationEl.dataset.durationReady === "1") return;
      if (preset > 0) {
        durationEl.textContent = formatDuration(preset);
        durationEl.dataset.durationReady = "1";
        return;
      }
      void resolveAudioUrl(attachmentId, downloadFn)
        .then((cached) => {
          if (cached?.duration) {
            durationEl.textContent = formatDuration(cached.duration);
            player.setAttribute("data-duration-sec", String(Math.round(cached.duration)));
          }
          durationEl.dataset.durationReady = "1";
        })
        .catch(() => {
          durationEl.dataset.durationReady = "1";
        });
    });
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
    prefetchVoiceDurations(root, { downloadFn });
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
.worker-chat-bubble.is-company .chat-voice-note{background:rgba(255,255,255,.06)}
.worker-chat-bubble.is-company .chat-voice-play{background:rgba(233,237,239,.12);color:#e9edef}
.worker-chat-bubble.is-mine .chat-voice-note{background:rgba(0,0,0,.12)}
.worker-chat-bubble.is-mine .chat-voice-play{background:rgba(0,0,0,.16);color:#e9edef}
.worker-chat-bubble.is-company .chat-voice-duration,.worker-chat-bubble.is-mine .chat-voice-duration{color:rgba(233,237,239,.82)}
.chat-head-actions{display:flex;gap:.35rem;flex-wrap:wrap;margin-top:.35rem}
.chat-head-actions button{font-size:.72rem;padding:.28rem .5rem;border-radius:8px;border:1px solid var(--border);background:var(--input-bg);color:var(--text);cursor:pointer}
.chat-compose{position:relative}
.chat-mic-btn{display:inline-flex;align-items:center;justify-content:center;width:42px;height:42px;border-radius:50%;border:1px solid var(--border,#334155);background:var(--input-bg,#1e293b);color:var(--text,#e2e8f0);cursor:pointer;flex-shrink:0;touch-action:none;user-select:none;-webkit-user-select:none}
.chat-mic-btn.is-recording{background:#b91c1c;border-color:#ef4444;color:#fff;animation:chatMicPulse 1s ease-in-out infinite}
@keyframes chatMicPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.06)}}
.chat-voice-record-overlay{position:absolute;left:0;right:0;bottom:100%;padding:.45rem .65rem .55rem;pointer-events:none}
.chat-voice-record-overlay.hidden{display:none}
.chat-voice-record-panel{display:flex;align-items:center;gap:.65rem;padding:.55rem .75rem;border-radius:16px;border:1px solid rgba(94,234,212,.28);background:rgba(15,23,42,.94);box-shadow:0 8px 28px rgba(0,0,0,.35)}
.chat-voice-record-cancel{flex:1;font-size:.78rem;color:rgba(226,232,240,.78);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chat-voice-record-cancel.is-armed{color:#fca5a5;font-weight:700}
.chat-voice-record-timer{font-variant-numeric:tabular-nums;font-weight:700;color:#5eead4;min-width:3rem;text-align:right}
.chat-voice-record-live-wave{display:flex;align-items:flex-end;gap:2px;height:28px;width:88px}
.chat-voice-record-live-wave span{flex:1;border-radius:999px;background:linear-gradient(180deg,#67e8f9,#14b8a6);height:20%;transition:height .08s linear}
.chat-send-btn[hidden],.worker-chat-send-btn[hidden]{display:none!important}
.worker-chat-compose{position:relative}
.worker-chat-mic-btn{display:inline-flex;align-items:center;justify-content:center;width:42px;height:42px;border-radius:50%;border:1px solid rgba(255,255,255,.12);background:#1f2c34;color:#e9edef;cursor:pointer;flex-shrink:0;touch-action:none}
.worker-chat-mic-btn.is-recording{background:#b91c1c;border-color:#ef4444}
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
    describeVoiceError,
    ensureMediaDevices,
    requestAudioStream,
    withTimeout,
    micInputAvailable,
    hasMediaRecorder,
    hasWebAudioRecording,
    canRecordVoice,
    isSupported,
    isAppleLikeDevice,
    isTouchPrimaryDevice,
    isStandalonePwa,
    isNativeCaptureAvailable,
    shouldPreferNativeVoiceCapture,
    isLikelyVoiceCaptureFile,
    normalizeCaptureFile,
    pickMimeType,
    formatDuration,
    isAudioAttachment,
    isVoiceOnlyBody,
    parseE2eAttachmentDuration,
    probeBlobDuration,
    composeHasText,
    updateComposePrimaryAction,
    bindWhatsAppVoiceCompose,
    asUploadFile,
    createRecorder,
    renderAudioPlayerHtml,
    hydrateAudioPlayers,
    resetActiveAudio,
  };
  injectVoiceStyles();
})(typeof window !== "undefined" ? window : globalThis);
