/**
 * SUPPIX chat voice notes — WhatsApp-style mic/send toggle and inline voice bubbles.
 */
(function initSuppixChatVoice(global) {
  const MIC_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z" stroke="currentColor" stroke-width="2"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>`;
  const SEND_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h12M13 7l5 5-5 5" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  const STOP_SVG = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor"/></svg>`;
  const PLAY_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 7.5v9l8-4.5-8-4.5Z" fill="currentColor"/></svg>`;
  const PAUSE_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="7" y="6" width="3.5" height="12" fill="currentColor"/><rect x="13.5" y="6" width="3.5" height="12" fill="currentColor"/></svg>`;
  const LOCK_SVG = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7 11V8a5 5 0 0 1 10 0v3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><rect x="5" y="11" width="14" height="10" rx="2" stroke="currentColor" stroke-width="2"/></svg>`;
  const VOICE_AUDIO_CONSTRAINTS = {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    channelCount: 1,
    sampleRate: 48000,
  };
  const VOICE_RECORD_BITRATE = 128000;

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
      { audio: VOICE_AUDIO_CONSTRAINTS },
      { audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 } },
      { audio: true },
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
        const recorderOptions = { ...options };
        if (recorderOptions.mimeType) {
          recorderOptions.audioBitsPerSecond = VOICE_RECORD_BITRATE;
        }
        const recorder = Object.keys(recorderOptions).length && recorderOptions.mimeType
          ? new global.MediaRecorder(stream, recorderOptions)
          : new global.MediaRecorder(stream, { audioBitsPerSecond: VOICE_RECORD_BITRATE });
        return {
          recorder,
          mimeType: recorder.mimeType || options.mimeType || picked || "audio/webm",
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

  function voiceWaveformHtml(seed, barCount = 36) {
    let hash = 0;
    const text = String(seed || "voice");
    for (let i = 0; i < text.length; i += 1) {
      hash = (hash + text.charCodeAt(i) * (i + 3)) % 9973;
    }
    const bars = [];
    for (let i = 0; i < barCount; i += 1) {
      hash = (hash * 33 + i * 17) % 100;
      const height = 24 + (hash % 68);
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
    onRecordingEnd,
    onError,
    canRecord,
  }) {
    if (!root || !micBtn || !recorder) return () => {};
    const cancelSlidePx = 72;
    const lockSlidePx = 72;
    const useToggleMode = !isTouchPrimaryDevice();
    let recording = false;
    let locked = false;
    let tickTimer = null;
    let pointerId = null;
    let startX = 0;
    let startY = 0;
    let cancelArmed = false;
    let pendingStart = null;
    let cancelPending = false;

    let sheet = root.querySelector(".wa-voice-record-sheet");
    if (!sheet) {
      sheet = global.document.createElement("div");
      sheet.className = "wa-voice-record-sheet hidden";
      sheet.innerHTML = `
        <div class="wa-voice-record-inner">
          <div class="wa-voice-record-hint">
            <span class="wa-voice-record-cancel">${labels.slideCancel || "← Wischen zum Abbrechen"}</span>
            <span class="wa-voice-record-lock-hint">${labels.slideLock || "↑ Hochziehen zum Sperren"}</span>
          </div>
          <div class="wa-voice-record-main">
            <button type="button" class="wa-voice-record-lock-btn hidden" aria-label="${labels.locked || "Aufnahme gesperrt"}">${LOCK_SVG}</button>
            <div class="wa-voice-record-live-wave" aria-hidden="true"></div>
            <span class="wa-voice-record-timer">0:00</span>
          </div>
          <div class="wa-voice-record-actions">
            <button type="button" class="wa-voice-record-cancel-btn hidden">${labels.cancel || "Abbrechen"}</button>
            <button type="button" class="wa-voice-record-send hidden">${labels.sendVoice || "Senden"}</button>
          </div>
        </div>`;
      root.appendChild(sheet);
      const wave = sheet.querySelector(".wa-voice-record-live-wave");
      if (wave && !wave.childElementCount) {
        wave.innerHTML = Array.from({ length: 32 }, () => "<span></span>").join("");
      }
    }
    const timerEl = sheet.querySelector(".wa-voice-record-timer");
    const cancelEl = sheet.querySelector(".wa-voice-record-cancel");
    const lockHintEl = sheet.querySelector(".wa-voice-record-lock-hint");
    const lockBtnEl = sheet.querySelector(".wa-voice-record-lock-btn");
    const sendLockedBtn = sheet.querySelector(".wa-voice-record-send");
    const cancelLockedBtn = sheet.querySelector(".wa-voice-record-cancel-btn");

    const stopTickTimer = () => {
      if (tickTimer) {
        global.clearInterval(tickTimer);
        tickTimer = null;
      }
    };

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
      if (!active) locked = false;
      micBtn.classList.toggle("is-recording", active);
      root.classList.toggle("is-voice-recording", active);
      sheet.classList.toggle("hidden", !active);
      sheet.classList.toggle("is-locked", locked);
      lockBtnEl?.classList.toggle("hidden", !locked);
      const showDesktopActions = active && useToggleMode;
      const showLockedSend = active && locked;
      sendLockedBtn?.classList.toggle("hidden", !(showLockedSend || showDesktopActions));
      cancelLockedBtn?.classList.toggle("hidden", !(showLockedSend || showDesktopActions));
      lockHintEl?.classList.toggle("hidden", locked || useToggleMode);
      if (active && useToggleMode && cancelEl) {
        cancelEl.textContent = labels.desktopRecording || labels.recording || "Aufnahme läuft…";
      }
      if (!active) {
        cancelArmed = false;
        if (cancelEl) {
          cancelEl.classList.remove("is-armed");
          cancelEl.textContent = labels.slideCancel || "← Wischen zum Abbrechen";
        }
        stopTickTimer();
        onRecordingEnd?.();
      }
      syncSendBtn();
    };

    const updateWave = (seconds) => {
      const wave = sheet.querySelector(".wa-voice-record-live-wave");
      if (timerEl) timerEl.textContent = formatDuration(seconds);
      const level = Number(recorder.lastLevel || 0);
      if (!wave) return;
      wave.querySelectorAll("span").forEach((bar, index) => {
        const phase = (Date.now() / 100 + index * 0.38) % (Math.PI * 2);
        const base = 18 + Math.abs(Math.sin(phase)) * 24;
        const height = base + level * 52 + Math.min(12, seconds * 1.5);
        bar.style.height = `${Math.round(Math.min(100, height))}%`;
      });
    };

    const startTickTimer = () => {
      stopTickTimer();
      tickTimer = global.setInterval(() => {
        const seconds = recorder.elapsedMs ? Math.max(0, recorder.elapsedMs / 1000) : 0;
        updateWave(seconds);
        onRecordingTick?.(seconds);
      }, 250);
    };

    const finishRecording = async (sendIt) => {
      if (!recording) return;
      stopTickTimer();
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

    const beginRecording = async () => {
      if (recording || pendingStart) return;
      if (typeof canRecord === "function" && !canRecord()) {
        onError?.(new Error(labels.noThread || "no_thread_selected"));
        return;
      }
      cancelPending = false;
      cancelArmed = false;
      pendingStart = recorder.start()
        .then(() => {
          pendingStart = null;
          if (cancelPending) {
            recorder.cancel?.();
            return;
          }
          setRecordingUi(true);
          updateWave(0);
          onRecordingTick?.(0);
          startTickTimer();
        })
        .catch((error) => {
          pendingStart = null;
          cancelPending = false;
          onError?.(error);
        });
      await pendingStart;
    };

    const onMicDown = (event) => {
      if (useToggleMode || recording || pointerId !== null || pendingStart) return;
      if (event.button !== undefined && event.button !== 0) return;
      pointerId = event.pointerId ?? "mouse";
      startX = event.clientX || 0;
      startY = event.clientY || 0;
      cancelArmed = false;
      locked = false;
      cancelPending = false;
      micBtn.setPointerCapture?.(event.pointerId);
      void beginRecording();
    };

    const onMicMove = (event) => {
      if (!recording || locked) return;
      const dx = (event.clientX || 0) - startX;
      const dy = startY - (event.clientY || 0);
      cancelArmed = dx < -cancelSlidePx;
      if (cancelEl) {
        cancelEl.classList.toggle("is-armed", cancelArmed);
        cancelEl.textContent = cancelArmed
          ? (labels.releaseCancel || "Loslassen zum Abbrechen")
          : (labels.slideCancel || "← Wischen zum Abbrechen");
      }
      if (!useToggleMode && dy > lockSlidePx && lockHintEl) {
        locked = true;
        sheet.classList.add("is-locked");
        lockBtnEl?.classList.remove("hidden");
        sendLockedBtn?.classList.remove("hidden");
        lockHintEl.classList.add("hidden");
        if (cancelEl) cancelEl.textContent = labels.lockedRecording || "🔒 Aufnahme gesperrt";
      }
    };

    const onMicUp = async (event) => {
      try {
        micBtn.releasePointerCapture?.(event.pointerId);
      } catch {
        /* ignore */
      }
      if (pendingStart) {
        cancelPending = true;
        pointerId = null;
        return;
      }
      if (!recording || locked) {
        pointerId = null;
        return;
      }
      pointerId = null;
      await finishRecording(true);
    };

    sendLockedBtn?.addEventListener("click", () => {
      if (recording) void finishRecording(true);
    });

    cancelLockedBtn?.addEventListener("click", () => {
      if (!recording) return;
      cancelArmed = true;
      void finishRecording(false);
    });

    cancelEl?.addEventListener("click", () => {
      if (!recording || useToggleMode) return;
      cancelArmed = true;
      void finishRecording(false);
    });

    const onMicToggleClick = (event) => {
      if (!useToggleMode) return;
      event.preventDefault();
      if (typeof canRecord === "function" && !canRecord() && !recording) {
        onError?.(new Error(labels.noThread || "no_thread_selected"));
        return;
      }
      if (recording) {
        void finishRecording(true);
        return;
      }
      void beginRecording();
    };

    micBtn.addEventListener("click", onMicToggleClick);
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
      micBtn.removeEventListener("click", onMicToggleClick);
      micBtn.removeEventListener("pointerdown", onMicDown);
      micBtn.removeEventListener("pointermove", onMicMove);
      micBtn.removeEventListener("pointerup", onMicUp);
      micBtn.removeEventListener("pointercancel", onMicUp);
      stopTickTimer();
    };
  }

  function createRecorder({ onTick, onError, onLevel } = {}) {
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
    let levelContext = null;
    let levelAnalyser = null;
    let levelTimer = null;
    let lastLevel = 0;

    const cleanupStream = () => {
      if (levelTimer) {
        global.clearInterval(levelTimer);
        levelTimer = null;
      }
      if (levelContext) {
        levelContext.close?.().catch(() => {});
        levelContext = null;
      }
      levelAnalyser = null;
      lastLevel = 0;
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

    const attachInputLevel = (activeStream) => {
      try {
        const Ctx = global.AudioContext || global.webkitAudioContext;
        if (!Ctx) return;
        levelContext = new Ctx();
        levelAnalyser = levelContext.createAnalyser();
        levelAnalyser.fftSize = 256;
        const src = levelContext.createMediaStreamSource(activeStream);
        src.connect(levelAnalyser);
        const buffer = new Uint8Array(levelAnalyser.frequencyBinCount);
        levelTimer = global.setInterval(() => {
          if (!levelAnalyser) return;
          levelAnalyser.getByteFrequencyData(buffer);
          let sum = 0;
          for (let i = 0; i < buffer.length; i += 1) sum += buffer[i];
          lastLevel = Math.min(1, (sum / buffer.length / 255) * 2.2);
          onLevel?.(lastLevel);
        }, 80);
      } catch {
        /* ignore level meter */
      }
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
      get lastLevel() {
        return lastLevel;
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
        attachInputLevel(stream);
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
    return `<div class="chat-voice-note wa-voice-bubble is-${side}" data-attachment-id="${id}" data-filename="${filename}" data-content-type="${contentType}"${knownDuration > 0 ? ` data-duration-sec="${knownDuration}"` : ""}>
      <button type="button" class="chat-voice-play" aria-label="${voiceLabel}">${PLAY_SVG}</button>
      <div class="chat-voice-body">
        ${voiceWaveformHtml(id || filename, 40)}
        <span class="chat-voice-duration">${durationLabel}</span>
      </div>
      <span class="chat-voice-dot" aria-hidden="true"></span>
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

  function bindWaveformSeek(player, audio) {
    const wave = player.querySelector(".chat-voice-wave");
    if (!wave || wave.dataset.seekBound === "1") return;
    wave.dataset.seekBound = "1";
    wave.style.cursor = "pointer";
    wave.addEventListener("click", (event) => {
      if (!audio.duration || Number.isNaN(audio.duration)) return;
      const rect = wave.getBoundingClientRect();
      if (!rect.width) return;
      const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
      audio.currentTime = ratio * audio.duration;
      const progressWave = player.querySelector(".chat-voice-wave");
      if (progressWave) {
        progressWave.style.setProperty("--voice-progress", String(ratio));
      }
      event.stopPropagation();
    });
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
      bindWaveformSeek(player, audio);
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
          const remaining = Math.max(0, audio.duration - audio.currentTime);
          durationEl.textContent = formatDuration(remaining);
          durationEl.classList.toggle("is-countdown", true);
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
      playBtn.addEventListener("dblclick", (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (activePlayer !== player || !activeAudio) return;
        const rates = [1, 1.5, 2];
        const current = Number(activeAudio.playbackRate || 1);
        const idx = rates.indexOf(current);
        activeAudio.playbackRate = rates[(idx + 1) % rates.length];
        player.setAttribute("data-playback-rate", String(activeAudio.playbackRate));
      });
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
.wa-voice-bubble,.chat-voice-note{display:flex;align-items:center;gap:8px;min-width:min(260px,82vw);max-width:min(320px,92vw);padding:7px 10px 7px 6px;border-radius:999px;cursor:pointer;user-select:none;position:relative}
.wa-voice-bubble .chat-voice-body{display:flex;align-items:center;gap:8px;flex:1;min-width:0}
.wa-voice-bubble .chat-voice-dot{width:8px;height:8px;border-radius:50%;background:#53bdeb;flex-shrink:0;opacity:.95}
.wa-voice-bubble.is-mine,.bubble.admin .wa-voice-bubble,.bubble.admin .chat-voice-note{background:#005c4b;color:#e9edef}
.wa-voice-bubble.is-them,.bubble.worker .wa-voice-bubble,.bubble.worker .chat-voice-note{background:#202c33;color:#e9edef}
.chat-voice-play{width:34px;height:34px;border-radius:50%;border:none;display:grid;place-items:center;flex-shrink:0;cursor:pointer;color:inherit;background:rgba(0,0,0,.18)}
.wa-voice-bubble.is-mine .chat-voice-play,.bubble.admin .chat-voice-play{background:rgba(0,0,0,.16);color:#e9edef}
.wa-voice-bubble.is-them .chat-voice-play,.bubble.worker .chat-voice-play{background:rgba(255,255,255,.1);color:#e9edef}
.chat-voice-note.is-playing .chat-voice-play,.wa-voice-bubble.is-playing .chat-voice-play{transform:scale(1.04);background:rgba(0,0,0,.24)}
.chat-voice-note.is-loading .chat-voice-play,.wa-voice-bubble.is-loading .chat-voice-play{opacity:.55}
.chat-voice-wave{--voice-progress:0;position:relative;display:flex;align-items:center;gap:2px;flex:1;min-width:96px;height:26px;overflow:hidden}
.chat-voice-wave::after{content:"";position:absolute;inset:0;width:calc(var(--voice-progress,0) * 100%);background:linear-gradient(90deg,rgba(255,255,255,.08),rgba(255,255,255,.18));pointer-events:none;border-radius:999px}
.chat-voice-wave span{display:block;width:2px;border-radius:999px;background:currentColor;opacity:.55;align-self:center;min-height:4px}
.chat-voice-note.is-playing .chat-voice-wave span,.wa-voice-bubble.is-playing .chat-voice-wave span{opacity:.88}
.chat-voice-wave{cursor:pointer;touch-action:manipulation}
.chat-voice-duration{font-size:.74rem;opacity:.88;min-width:2.4rem;text-align:end;font-variant-numeric:tabular-nums;flex-shrink:0}
.chat-voice-duration.is-countdown{opacity:1}
.bubble.is-voice-only .bubble-body{display:none}
.bubble.is-voice-only{padding:.35rem .55rem .35rem .35rem}
.worker-chat-bubble.is-voice-only .worker-chat-body{display:none}
.worker-chat-bubble.is-voice-only{padding:.4rem .55rem .35rem .45rem}
.chat-delete-btn,.worker-chat-delete-btn{border:none;background:transparent;cursor:pointer;opacity:.5;font-size:.85rem;padding:0 .15rem}
.chat-delete-btn:hover,.worker-chat-delete-btn:hover{opacity:1}
.worker-chat-bubble.is-company .wa-voice-bubble,.worker-chat-bubble.is-company .chat-voice-note{background:rgba(32,44,51,.92)}
.worker-chat-bubble.is-mine .wa-voice-bubble,.worker-chat-bubble.is-mine .chat-voice-note{background:#005c4b}
.worker-chat-bubble.is-company .chat-voice-duration,.worker-chat-bubble.is-mine .chat-voice-duration{color:rgba(233,237,239,.88)}
.chat-head-actions{display:flex;gap:.35rem;flex-wrap:wrap;margin-top:.35rem}
.chat-head-actions button{font-size:.72rem;padding:.28rem .5rem;border-radius:8px;border:1px solid var(--border);background:var(--input-bg);color:var(--text);cursor:pointer}
.chat-compose,.worker-chat-compose{position:relative}
.chat-mic-btn,.worker-chat-mic-btn{display:inline-flex;align-items:center;justify-content:center;width:42px;height:42px;border-radius:50%;border:none;background:#00a884;color:#fff;cursor:pointer;flex-shrink:0;touch-action:none;user-select:none;-webkit-user-select:none;box-shadow:0 2px 8px rgba(0,168,132,.35)}
.chat-mic-btn.is-recording,.worker-chat-mic-btn.is-recording{background:#e53935;box-shadow:0 2px 12px rgba(229,57,53,.45);animation:chatMicPulse 1s ease-in-out infinite}
@keyframes chatMicPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.05)}}
.wa-voice-record-sheet{position:fixed;left:0;right:0;bottom:0;z-index:1500;padding:.75rem .85rem calc(.85rem + env(safe-area-inset-bottom,0px));background:linear-gradient(180deg,rgba(11,20,26,.02),rgba(11,20,26,.96) 28%,#0b141a 100%);pointer-events:auto}
.wa-voice-record-sheet.hidden{display:none}
.wa-voice-record-inner{display:flex;flex-direction:column;gap:.65rem;max-width:520px;margin:0 auto}
.wa-voice-record-hint{display:flex;justify-content:space-between;gap:.75rem;font-size:.78rem;color:rgba(233,237,239,.72)}
.wa-voice-record-cancel.is-armed{color:#ff8a80;font-weight:700}
.wa-voice-record-lock-hint{color:#53bdeb}
.wa-voice-record-main{display:flex;align-items:center;gap:.75rem;padding:.65rem .85rem;border-radius:18px;background:#202c33;border:1px solid rgba(255,255,255,.06)}
.wa-voice-record-live-wave{display:flex;align-items:flex-end;gap:2px;flex:1;height:34px}
.wa-voice-record-live-wave span{flex:1;border-radius:999px;background:linear-gradient(180deg,#00a884,#128c7e);height:20%;transition:height .07s linear}
.wa-voice-record-timer{font-variant-numeric:tabular-nums;font-weight:700;color:#e9edef;min-width:3rem;text-align:right;font-size:.95rem}
.wa-voice-record-lock-btn{width:38px;height:38px;border-radius:50%;border:1px solid rgba(255,255,255,.12);background:rgba(0,168,132,.2);color:#00a884;display:grid;place-items:center;flex-shrink:0}
.wa-voice-record-send{align-self:flex-end;border:none;border-radius:999px;padding:.55rem 1.1rem;background:#00a884;color:#fff;font-weight:700;cursor:pointer}
.wa-voice-record-actions{display:flex;justify-content:flex-end;gap:.55rem}
.wa-voice-record-cancel-btn{border:1px solid rgba(255,255,255,.16);border-radius:999px;padding:.55rem 1.1rem;background:rgba(255,255,255,.06);color:#ff8a80;font-weight:700;cursor:pointer}
.wa-voice-record-cancel-btn.hidden,.wa-voice-record-send.hidden{display:none}
.wa-voice-record-sheet.is-locked .wa-voice-record-main{border-color:rgba(0,168,132,.35)}
.chat-send-btn[hidden],.worker-chat-send-btn[hidden]{display:none!important}
.is-voice-recording textarea{opacity:.45}
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
