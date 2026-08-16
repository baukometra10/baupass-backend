/**
 * SUPPIX voice/video call — WebRTC + HTTP signaling (admin + worker web).
 * Supports optional camera, peer camera-intent notices, and in-call image share.
 */
(function (global) {
  const POLL_MS = 700;
  const RING_TIMEOUT_MS = 60000;
  const AUDIO_CONSTRAINTS = {
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
      sampleRate: 48000,
    },
    video: false,
  };
  function videoConstraints(facingMode = "user", tier = "hd") {
    const sd = String(tier || "").toLowerCase() === "sd";
    return {
      video: {
        facingMode: { ideal: facingMode },
        width: sd ? { ideal: 640, max: 854 } : { ideal: 1280, min: 640 },
        height: sd ? { ideal: 480, max: 480 } : { ideal: 720, min: 480 },
        frameRate: sd ? { ideal: 24, max: 30 } : { ideal: 30, max: 30 },
      },
      audio: false,
    };
  }

  /** Make a local PiP <video> draggable within its offsetParent. */
  function bindDraggablePip(el) {
    if (!el || el.dataset.dragBound === "1") return el;
    el.dataset.dragBound = "1";
    el.style.touchAction = "none";
    el.style.cursor = "grab";
    let dragging = false;
    let startX = 0;
    let startY = 0;
    let origLeft = 0;
    let origTop = 0;

    function clamp(n, min, max) {
      return Math.max(min, Math.min(max, n));
    }

    function onPointerDown(event) {
      if (el.classList.contains("hidden")) return;
      const pt = event.touches ? event.touches[0] : event;
      if (!pt) return;
      const parent = el.offsetParent || el.parentElement || document.body;
      const parentRect = parent.getBoundingClientRect();
      const rect = el.getBoundingClientRect();
      el.style.left = `${rect.left - parentRect.left}px`;
      el.style.top = `${rect.top - parentRect.top}px`;
      el.style.right = "auto";
      el.style.bottom = "auto";
      startX = pt.clientX;
      startY = pt.clientY;
      origLeft = parseFloat(el.style.left) || 0;
      origTop = parseFloat(el.style.top) || 0;
      dragging = true;
      el.style.cursor = "grabbing";
      try {
        el.setPointerCapture?.(event.pointerId);
      } catch (_) {
        /* ignore */
      }
      event.preventDefault?.();
      event.stopPropagation?.();
    }

    function onPointerMove(event) {
      if (!dragging) return;
      const pt = event.touches ? event.touches[0] : event;
      if (!pt) return;
      const parent = el.offsetParent || el.parentElement || document.body;
      const parentRect = parent.getBoundingClientRect();
      const w = el.offsetWidth || 120;
      const h = el.offsetHeight || 160;
      const nextLeft = clamp(origLeft + (pt.clientX - startX), 8, Math.max(8, parentRect.width - w - 8));
      const nextTop = clamp(origTop + (pt.clientY - startY), 8, Math.max(8, parentRect.height - h - 8));
      el.style.left = `${nextLeft}px`;
      el.style.top = `${nextTop}px`;
      event.preventDefault?.();
      event.stopPropagation?.();
    }

    function snapToCorner() {
      const parent = el.offsetParent || el.parentElement || document.body;
      const parentRect = parent.getBoundingClientRect();
      const w = el.offsetWidth || 120;
      const h = el.offsetHeight || 160;
      const left = parseFloat(el.style.left) || 0;
      const top = parseFloat(el.style.top) || 0;
      const midX = left + w / 2;
      const midY = top + h / 2;
      const toLeft = midX < parentRect.width / 2;
      const toTop = midY < parentRect.height / 2;
      const nextLeft = toLeft ? 8 : Math.max(8, parentRect.width - w - 8);
      const nextTop = toTop ? 8 : Math.max(8, parentRect.height - h - 8);
      el.style.transition = "left 0.18s ease, top 0.18s ease";
      el.style.left = `${nextLeft}px`;
      el.style.top = `${nextTop}px`;
      global.setTimeout(() => {
        el.style.transition = "";
      }, 220);
    }

    function onPointerUp(event) {
      if (!dragging) return;
      dragging = false;
      el.style.cursor = "grab";
      try {
        el.releasePointerCapture?.(event.pointerId);
      } catch (_) {
        /* ignore */
      }
      snapToCorner();
      event.stopPropagation?.();
    }

    el.addEventListener("pointerdown", onPointerDown);
    el.addEventListener("pointermove", onPointerMove);
    el.addEventListener("pointerup", onPointerUp);
    el.addEventListener("pointercancel", onPointerUp);
    return el;
  }

  function resetDraggablePip(el) {
    if (!el) return;
    el.style.left = "";
    el.style.top = "";
    el.style.right = "";
    el.style.bottom = "";
    el.style.transition = "";
  }

  function mapCameraError(error) {
    const name = String(error?.name || "");
    const msg = String(error?.message || error || "");
    if (name === "NotAllowedError" || /permission|denied|NotAllowed/i.test(msg)) {
      return Object.assign(new Error("camera_permission_denied"), { code: "camera_permission_denied" });
    }
    if (name === "NotFoundError" || /NotFound|device not found/i.test(msg)) {
      return Object.assign(new Error("camera_not_found"), { code: "camera_not_found" });
    }
    if (name === "NotReadableError" || /NotReadable|track.*progress|Could not start/i.test(msg)) {
      return Object.assign(new Error("camera_in_use"), { code: "camera_in_use" });
    }
    if (name === "OverconstrainedError" || /Overconstrained/i.test(msg)) {
      return Object.assign(new Error("camera_constraints"), { code: "camera_constraints" });
    }
    if (name === "AbortError" || /timeout/i.test(msg)) {
      return Object.assign(new Error("camera_timeout"), { code: "camera_timeout" });
    }
    return Object.assign(error instanceof Error ? error : new Error(msg || "camera_failed"), {
      code: "camera_failed",
    });
  }
  const OFFER_OPTS = { offerToReceiveAudio: true, offerToReceiveVideo: true };

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * WhatsApp-like call tones (distinct directions):
   * - incoming: short melodic messenger motif + pause (device ringtone feel)
   * - outgoing: classic dual-tone ringback 440+480 (caller hears "it is ringing")
   * mode: "incoming" | "outgoing"
   */
  function createRingtone(options = {}) {
    const mode = options.mode === "incoming" ? "incoming" : "outgoing";
    // Never mix styles: incoming ≠ outgoing.
    const whatsappStyle = mode === "incoming" ? (options.whatsappStyle !== false) : false;
    const defaultSrc =
      mode === "incoming"
        ? "/sounds/phone-call-ring.mp3"
        : "/sounds/phone-call-ringback.mp3";
    const src =
      String(options.src || global.SUPPIX_CALL_RINGTONE_URL || defaultSrc).trim() || defaultSrc;
    // Silence is baked into the MP3; tiny gap only between loops.
    const pauseMs = Math.max(
      60,
      Number(options.pauseMs) || (mode === "incoming" ? 120 : 80),
    );
    let audio = null;
    let stopped = false;
    let outputEnabled = true;
    let pauseTimer = null;
    let fallbackTimer = null;
    let fallbackCtx = null;
    let fallbackMaster = null;

    function targetVolume() {
      if (!outputEnabled) return 0;
      return mode === "outgoing" ? 0.82 : 1;
    }

    function applyOutput() {
      if (!audio) return;
      audio.muted = !outputEnabled;
      audio.volume = targetVolume();
      if (fallbackMaster) {
        try {
          fallbackMaster.gain.value = outputEnabled ? 0.7 : 0.0001;
        } catch (_) {
          /* ignore */
        }
      }
    }

    function clearPauseTimer() {
      if (pauseTimer) {
        global.clearTimeout(pauseTimer);
        pauseTimer = null;
      }
    }

    function stopFallback() {
      if (fallbackTimer) {
        global.clearTimeout(fallbackTimer);
        global.clearInterval(fallbackTimer);
        fallbackTimer = null;
      }
      if (fallbackCtx) {
        fallbackCtx.close().catch(() => {});
        fallbackCtx = null;
      }
      fallbackMaster = null;
    }

    function scheduleNextCycle() {
      clearPauseTimer();
      if (stopped) return;
      pauseTimer = global.setTimeout(() => {
        pauseTimer = null;
        if (stopped || !audio) return;
        try {
          audio.currentTime = 0;
          const p = audio.play();
          if (p && typeof p.catch === "function") p.catch(() => {});
        } catch (_) {
          /* ignore */
        }
      }, pauseMs);
    }

    function startFallbackSynth() {
      if (stopped || fallbackCtx) return;
      try {
        const ctx = new (global.AudioContext || global.webkitAudioContext)();
        fallbackCtx = ctx;
        // Incoming: melodic motif. Outgoing: classic dual-tone ringback.
        const master = ctx.createGain();
        fallbackMaster = master;
        master.gain.value = outputEnabled ? 0.78 : 0.0001;
        master.connect(ctx.destination);

        function playNote(hz, start, dur, peak = 0.18) {
          const osc = ctx.createOscillator();
          const g = ctx.createGain();
          osc.type = "sine";
          osc.frequency.value = hz;
          const o2 = ctx.createOscillator();
          const g2 = ctx.createGain();
          o2.type = "sine";
          o2.frequency.value = hz * 2;
          g.gain.setValueAtTime(0.0001, start);
          g.gain.exponentialRampToValueAtTime(peak, start + 0.015);
          g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
          g2.gain.setValueAtTime(0.0001, start);
          g2.gain.exponentialRampToValueAtTime(peak * 0.28, start + 0.015);
          g2.gain.exponentialRampToValueAtTime(0.0001, start + dur);
          osc.connect(g);
          o2.connect(g2);
          g.connect(master);
          g2.connect(master);
          osc.start(start);
          o2.start(start);
          osc.stop(start + dur + 0.02);
          o2.stop(start + dur + 0.02);
        }

        function playDualPulse(start, dur = 0.4, peak = 0.16) {
          [440, 480].forEach((hz) => {
            const osc = ctx.createOscillator();
            const g = ctx.createGain();
            osc.type = "sine";
            osc.frequency.value = hz;
            g.gain.setValueAtTime(0.0001, start);
            g.gain.exponentialRampToValueAtTime(peak, start + 0.02);
            g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
            osc.connect(g);
            g.connect(master);
            osc.start(start);
            osc.stop(start + dur + 0.02);
          });
        }

        const ringBurst = () => {
          if (stopped || !fallbackCtx) return;
          const t0 = ctx.currentTime + 0.02;
          if (whatsappStyle) {
            const motif = [
              [523.25, 0.11],
              [783.99, 0.11],
              [1046.5, 0.16],
              [0, 0.07],
              [659.25, 0.1],
              [783.99, 0.1],
              [1046.5, 0.2],
            ];
            let cursor = t0;
            motif.forEach(([hz, dur]) => {
              if (hz > 0) playNote(hz, cursor, dur, 0.2);
              cursor += dur;
            });
            return;
          }
          // Outgoing WhatsApp-like ringback: tring-tring … long pause
          playDualPulse(t0, 0.4, 0.17);
          playDualPulse(t0 + 0.6, 0.4, 0.17);
        };
        if (ctx.state === "suspended") void ctx.resume();
        const burst = () => {
          if (stopped || !fallbackCtx) return;
          ringBurst();
          // Match asset cadence: ~2.45s incoming, ~5s outgoing
          const nextMs = whatsappStyle ? 2450 : 5000;
          fallbackTimer = global.setTimeout(burst, nextMs);
        };
        burst();
      } catch (_) {
        /* ignore */
      }
    }

    return {
      start() {
        if (stopped) return;
        try {
          audio = new global.Audio();
          audio.preload = "auto";
          audio.loop = false; // full cycle must finish; we restart after a pause
          audio.playsInline = true;
          audio.setAttribute("playsinline", "true");
          audio.src = src.includes("?") ? src : `${src}?v=20260726wa3`;
          applyOutput();
          audio.addEventListener("ended", () => {
            if (!stopped) scheduleNextCycle();
          });
          const playPromise = audio.play();
          if (playPromise && typeof playPromise.then === "function") {
            playPromise.catch(() => {
              if (!stopped) startFallbackSynth();
            });
          }
          audio.addEventListener("error", () => {
            if (!stopped) startFallbackSynth();
          }, { once: true });
        } catch (_) {
          startFallbackSynth();
        }
      },
      setOutputEnabled(on) {
        outputEnabled = Boolean(on);
        applyOutput();
      },
      isOutputEnabled() {
        return outputEnabled;
      },
      stop() {
        stopped = true;
        clearPauseTimer();
        stopFallback();
        if (audio) {
          try {
            audio.pause();
            audio.removeAttribute("src");
            audio.load();
          } catch (_) {
            /* ignore */
          }
          audio = null;
        }
      },
    };
  }

  function buildIceServers(raw) {
    const list = Array.isArray(raw) ? raw : [];
    return list.map((item) => {
      if (typeof item === "string") return { urls: item };
      return item;
    });
  }

  class VoiceCallSession {
    constructor({
      api,
      role,
      onState,
      onError,
      onAudioLevels,
      onCameraIntent,
      onCameraState,
      onCallImage,
      onLocalVideo,
      onRemoteVideo,
      onVideoQuality,
      onCameraPreview,
      onScreenShare,
      onRecording,
      displayName,
      preferVideo,
    }) {
      this.api = api;
      this.role = role;
      this.onState = onState || (() => {});
      this.onError = onError || (() => {});
      this.onAudioLevels = onAudioLevels || (() => {});
      this.onCameraIntent = onCameraIntent || (() => {});
      this.onCameraState = onCameraState || (() => {});
      this.onCallImage = onCallImage || (() => {});
      this.onLocalVideo = onLocalVideo || (() => {});
      this.onRemoteVideo = onRemoteVideo || (() => {});
      this.onVideoQuality = onVideoQuality || (() => {});
      this.onCameraPreview = onCameraPreview || (() => {});
      this.onScreenShare = onScreenShare || (() => {});
      this.onRecording = onRecording || (() => {});
      this.displayName = String(displayName || "").trim();
      this.preferVideo = Boolean(preferVideo);
      this.callId = "";
      this.workerId = "";
      this.iceServers = [];
      this.pc = null;
      this.localStream = null;
      this.remoteStream = null;
      this.remoteAudio = null;
      this.pollTimer = null;
      this.lastSignalId = "";
      this.ringtone = null;
      this.ended = false;
      this.ringDeadline = 0;
      this.muted = false;
      this.speakerOn = true;
      this.cameraOn = false;
      this.cameraPreviewing = false;
      this.previewStream = null;
      this.facingMode = "user";
      this.remoteHasVideo = false;
      this.videoQuality = "hd";
      this.screenSharing = false;
      this.blurEnabled = false;
      this._blurRawTrack = null;
      this._blurCanvas = null;
      this._blurRaf = 0;
      this._screenTrack = null;
      this._cameraTrackBeforeShare = null;
      this._recorder = null;
      this._recordChunks = [];
      this._qualityBadStreak = 0;
      this._qualityGoodStreak = 0;
      this._qualityTimer = null;
      this.outputVolume = 1;
      this.companyId = "";
      this.ringTimeoutTimer = null;
      this.audioContext = null;
      this.localAnalyser = null;
      this.remoteAnalyser = null;
      this.localSource = null;
      this.remoteSource = null;
      this.meterTimer = null;
      this.localMeterData = null;
      this.remoteMeterData = null;
      this.deferredOffer = false;
      this.offerSent = false;
      this.pendingIce = [];
      this._makingOffer = false;
      this._ignoreOffer = false;
    }

    _callStatusPath() {
      const prefix = this.role === "worker" ? "/api/worker-app" : "/api";
      return `${prefix}/chat/calls/${encodeURIComponent(this.callId)}`;
    }

    _scheduleRingTimeout() {
      if (this.ringTimeoutTimer) global.clearTimeout(this.ringTimeoutTimer);
      this.ringTimeoutTimer = global.setTimeout(() => {
        if (this.ended || !this.callId) return;
        void this.api(this._callStatusPath())
          .then((data) => {
            const status = data.call?.status || "";
            if (!this.ended && (status === "ringing" || status === "accepted")) {
              if (status === "ringing") {
                this.onState("unreachable");
                void this.end("timeout");
              }
            }
          })
          .catch(() => {});
      }, RING_TIMEOUT_MS);
    }

    _clearRingTimeout() {
      if (this.ringTimeoutTimer) global.clearTimeout(this.ringTimeoutTimer);
      this.ringTimeoutTimer = null;
    }

    toggleMute() {
      this.muted = !this.muted;
      this._applyMuteToLocalTracks();
      return this.muted;
    }

    setMuted(muted) {
      this.muted = Boolean(muted);
      this._applyMuteToLocalTracks();
      return this.muted;
    }

    _applyMuteToLocalTracks() {
      if (!this.localStream) return;
      this.localStream.getAudioTracks().forEach((track) => {
        track.enabled = !this.muted;
      });
    }

    toggleSpeaker() {
      this.speakerOn = !this.speakerOn;
      this._applySpeakerToRemoteAudio();
      return this.speakerOn;
    }

    setSpeakerOn(on) {
      this.speakerOn = Boolean(on);
      this._applySpeakerToRemoteAudio();
      return this.speakerOn;
    }

    _applySpeakerToRemoteAudio() {
      if (!this.remoteAudio) return;
      this.remoteAudio.muted = !this.speakerOn || this.outputVolume === 0;
      this.remoteAudio.volume = this.outputVolume;
    }

    setOutputVolume(value) {
      const vol = Math.max(0, Math.min(1, Number(value)));
      this.outputVolume = vol;
      this._applySpeakerToRemoteAudio();
      return vol;
    }

    isCameraOn() {
      return Boolean(this.cameraOn);
    }

    getLocalStream() {
      return this.localStream;
    }

    getRemoteStream() {
      return this.remoteStream;
    }

    hasRemoteVideo() {
      return Boolean(this.remoteHasVideo);
    }

    getFacingMode() {
      return this.facingMode === "environment" ? "environment" : "user";
    }

    getVideoQuality() {
      return this.videoQuality || "hd";
    }

    _stopQualityMonitor() {
      if (this._qualityTimer) {
        global.clearInterval(this._qualityTimer);
        this._qualityTimer = null;
      }
      this._qualityBadStreak = 0;
      this._qualityGoodStreak = 0;
    }

    _startQualityMonitor() {
      this._stopQualityMonitor();
      if (!this.cameraOn) return;
      this._qualityTimer = global.setInterval(() => {
        void this._adaptVideoQuality();
      }, 3000);
    }

    async _applyVideoTier(tier) {
      const next = String(tier || "hd").toLowerCase() === "sd" ? "sd" : "hd";
      if (next === this.videoQuality) return;
      const track = this.localStream?.getVideoTracks?.()?.[0];
      if (!track || track.readyState === "ended") return;
      const constraints = videoConstraints(this.facingMode || "user", next).video;
      try {
        await track.applyConstraints(constraints);
      } catch (_) {
        try {
          await track.applyConstraints({
            width: next === "sd" ? 640 : 1280,
            height: next === "sd" ? 480 : 720,
            frameRate: next === "sd" ? 24 : 30,
          });
        } catch (_) {
          return;
        }
      }
      this.videoQuality = next;
      try {
        this.onVideoQuality(next);
      } catch (_) {
        /* ignore */
      }
    }

    async _adaptVideoQuality() {
      if (this.ended || !this.cameraOn || !this.pc) return;
      let rttMs = 0;
      let lossRatio = 0;
      let bitrate = 0;
      try {
        const stats = await this.pc.getStats();
        let packetsLost = 0;
        let packetsSent = 0;
        let bytesSent = 0;
        let timestamp = 0;
        stats.forEach((report) => {
          if (report.type === "candidate-pair" && (report.state === "succeeded" || report.nominated)) {
            const rtt = Number(report.currentRoundTripTime || 0);
            if (rtt > 0) rttMs = Math.max(rttMs, rtt * 1000);
          }
          if (report.type === "outbound-rtp" && (report.kind === "video" || report.mediaType === "video")) {
            packetsLost += Number(report.packetsLost || 0);
            packetsSent += Number(report.packetsSent || 0);
            bytesSent = Number(report.bytesSent || bytesSent);
            timestamp = Number(report.timestamp || timestamp);
          }
        });
        const total = packetsLost + packetsSent;
        if (total > 20) lossRatio = packetsLost / total;
        if (this._lastQualityBytes != null && this._lastQualityTs && timestamp > this._lastQualityTs) {
          const dt = (timestamp - this._lastQualityTs) / 1000;
          if (dt > 0) bitrate = ((bytesSent - this._lastQualityBytes) * 8) / dt;
        }
        this._lastQualityBytes = bytesSent;
        this._lastQualityTs = timestamp;
      } catch (_) {
        return;
      }
      const bad = rttMs > 420 || lossRatio > 0.05 || (bitrate > 0 && bitrate < 180000);
      const good = rttMs > 0 && rttMs < 220 && lossRatio < 0.015 && (bitrate === 0 || bitrate > 450000);
      if (bad) {
        this._qualityBadStreak += 1;
        this._qualityGoodStreak = 0;
      } else if (good) {
        this._qualityGoodStreak += 1;
        this._qualityBadStreak = 0;
      } else {
        this._qualityBadStreak = Math.max(0, this._qualityBadStreak - 1);
        this._qualityGoodStreak = Math.max(0, this._qualityGoodStreak - 1);
      }
      if (this.videoQuality !== "sd" && this._qualityBadStreak >= 2) {
        await this._applyVideoTier("sd");
      } else if (this.videoQuality === "sd" && this._qualityGoodStreak >= 3) {
        await this._applyVideoTier("hd");
      }
    }

    async sendCameraIntent(enabled = true) {
      if (!this.callId || this.ended) return false;
      await this._sendSignal("camera_intent", {
        enabled: Boolean(enabled),
        fromName: this.displayName || "",
      });
      return true;
    }

    async sendCallImage(dataUrl, opts = {}) {
      if (!this.callId || this.ended) return false;
      const raw = String(dataUrl || "");
      if (!raw.startsWith("data:image/")) throw new Error("invalid_image");
      if (raw.length > 300000) throw new Error("call_image_too_large");
      await this._sendSignal("call_image", {
        dataUrl: raw,
        fromName: String(opts.fromName || this.displayName || "").slice(0, 80),
        mime: String(opts.mime || "image/jpeg").slice(0, 40),
      });
      return true;
    }

    isCameraPreviewing() {
      return Boolean(this.cameraPreviewing);
    }

    async startCameraPreview() {
      if (this.ended) return false;
      if (this.cameraOn) return true;
      if (this.cameraPreviewing && this.previewStream) {
        try {
          this.onLocalVideo(this.previewStream, true, { preview: true });
          this.onCameraPreview(true);
        } catch (_) { /* ignore */ }
        return "preview";
      }
      let camStream;
      try {
        camStream = await navigator.mediaDevices.getUserMedia(
          videoConstraints(this.facingMode || "user", this.videoQuality || "hd"),
        );
      } catch (error) {
        throw mapCameraError(error);
      }
      this.previewStream = camStream;
      this.cameraPreviewing = true;
      try {
        this.onLocalVideo(camStream, true, { preview: true });
        this.onCameraPreview(true);
      } catch (_) { /* ignore */ }
      return "preview";
    }

    async cancelCameraPreview() {
      this.cameraPreviewing = false;
      if (this.previewStream) {
        this.previewStream.getTracks().forEach((t) => { try { t.stop(); } catch (_) { /* ignore */ } });
        this.previewStream = null;
      }
      try {
        this.onCameraPreview(false);
        this.onLocalVideo(this.localStream, this.cameraOn, { preview: false });
      } catch (_) { /* ignore */ }
      return false;
    }

    async confirmCameraPreview() {
      if (this.ended) return false;
      if (!this.pc || !this.callId) throw new Error("call_not_connected");
      if (this.cameraOn) return true;
      if (!this.previewStream) await this.startCameraPreview();
      const camStream = this.previewStream;
      const videoTrack = camStream?.getVideoTracks?.()?.[0];
      if (!videoTrack) throw mapCameraError(new Error("camera_failed"));
      await this.sendCameraIntent(true);
      await sleep(320);
      if (!this.localStream) this.localStream = camStream;
      else if (!this.localStream.getVideoTracks().includes(videoTrack)) this.localStream.addTrack(videoTrack);
      // Reuse the negotiated video m-line (recvonly from peer). addTrack alone
      // creates a second m-line → peer sees us but we stay invisible to them.
      await this._attachLocalVideoTrack(videoTrack);
      await this._renegotiate();
      this.cameraPreviewing = false;
      this.previewStream = null;
      this.cameraOn = true;
      this._startQualityMonitor();
      try { await this._sendSignal("camera_state", { enabled: true, fromName: this.displayName || "" }); } catch (_) { /* ignore */ }
      try {
        this.onCameraPreview(false);
        this.onLocalVideo(this.localStream, true, { preview: false });
      } catch (_) { /* ignore */ }
      return true;
    }

    /**
     * Publish camera on the existing video transceiver when possible.
     * Critical for one-way video after peer reserved a recvonly video slot.
     */
    async _attachLocalVideoTrack(videoTrack) {
      if (!this.pc || !videoTrack) return false;
      const txs = this.pc.getTransceivers?.() || [];
      for (const tx of txs) {
        const sk = tx.sender?.track?.kind || null;
        const rk = tx.receiver?.track?.kind || null;
        if (sk === "audio" || rk === "audio") continue;
        const isVideoSlot = sk === "video" || rk === "video";
        if (!isVideoSlot) continue;
        try {
          if (typeof tx.setDirection === "function") {
            const dir = String(tx.direction || "");
            if (dir === "recvonly" || dir === "inactive" || dir === "sendonly") {
              try { await tx.setDirection("sendrecv"); } catch (_) { /* ignore */ }
            }
          }
        } catch (_) { /* ignore */ }
        try {
          if (typeof tx.sender?.replaceTrack === "function") {
            await tx.sender.replaceTrack(videoTrack);
            return true;
          }
        } catch (_) { /* try next */ }
      }
      for (const sender of this.pc.getSenders?.() || []) {
        if (sender.track?.kind === "audio") continue;
        if (!sender.track || sender.track.kind === "video") {
          try {
            await sender.replaceTrack(videoTrack);
            return true;
          } catch (_) { /* try next */ }
        }
      }
      try {
        if (!this.localStream) this.localStream = new MediaStream([videoTrack]);
        else if (!this.localStream.getVideoTracks().includes(videoTrack)) {
          this.localStream.addTrack(videoTrack);
        }
        this.pc.addTrack(videoTrack, this.localStream);
        return true;
      } catch (_) {
        return false;
      }
    }

    async setCameraEnabled(enabled, opts = {}) {
      const next = Boolean(enabled);
      const skipPreview = Boolean(opts.skipPreview || opts.publish);
      if (this.ended) return false;
      if (!this.pc || !this.callId) throw new Error("call_not_connected");
      if (!next) {
        if (this.cameraPreviewing) return this.cancelCameraPreview();
        if (!this.cameraOn) return false;
        try { await this.setBlurEnabled(false); } catch (_) { /* ignore */ }
        if (this.screenSharing) { try { await this.setScreenShareEnabled(false); } catch (_) { /* ignore */ } }
        const senders = this.pc.getSenders?.() || [];
        for (const sender of senders) {
          if (sender.track?.kind === "video") {
            try { sender.track.stop(); } catch (_) { /* ignore */ }
            // Keep the video m-line for the next camera enable (avoid second-line bug).
            try {
              if (typeof sender.replaceTrack === "function") await sender.replaceTrack(null);
              else this.pc.removeTrack(sender);
            } catch (_) {
              try { this.pc.removeTrack(sender); } catch (_) { /* ignore */ }
            }
          }
        }
        (this.localStream?.getVideoTracks?.() || []).forEach((track) => {
          try { track.stop(); this.localStream.removeTrack(track); } catch (_) { /* ignore */ }
        });
        await this._renegotiate();
        this.cameraOn = false;
        this._stopQualityMonitor();
        this.videoQuality = "hd";
        this._lastQualityBytes = null;
        this._lastQualityTs = 0;
        try { await this._sendSignal("camera_state", { enabled: false, fromName: this.displayName || "" }); } catch (_) { /* ignore */ }
        try { this.onLocalVideo(this.localStream, false, { preview: false }); } catch (_) { /* ignore */ }
        return false;
      }
      if (this.cameraOn) return true;
      if (!skipPreview) return this.startCameraPreview();
      try {
        return await this.confirmCameraPreview();
      } catch (error) {
        await this.cancelCameraPreview();
        throw mapCameraError(error);
      }
    }

    async _replaceOutgoingVideoTrack(newTrack, { stopOld = true } = {}) {
      if (!this.pc || !newTrack) return;
      const sender = (this.pc.getSenders?.() || []).find((s) => s.track?.kind === "video");
      const oldTrack = sender?.track || this.localStream?.getVideoTracks?.()?.[0] || null;
      const attached = await this._attachLocalVideoTrack(newTrack);
      if (!attached) {
        if (sender && typeof sender.replaceTrack === "function") {
          await sender.replaceTrack(newTrack);
        } else if (sender) {
          try { this.pc.removeTrack(sender); } catch (_) { /* ignore */ }
          if (!this.localStream) this.localStream = new MediaStream([newTrack]);
          this.pc.addTrack(newTrack, this.localStream);
          await this._renegotiate();
        } else {
          if (!this.localStream) this.localStream = new MediaStream([newTrack]);
          else this.localStream.addTrack(newTrack);
          this.pc.addTrack(newTrack, this.localStream);
          await this._renegotiate();
        }
      }
      if (this.localStream && !this.localStream.getVideoTracks().includes(newTrack)) this.localStream.addTrack(newTrack);
      if (stopOld && oldTrack && oldTrack !== newTrack) {
        try { oldTrack.stop(); this.localStream?.removeTrack?.(oldTrack); } catch (_) { /* ignore */ }
      }
    }

    async setBlurEnabled(enabled) {
      const next = Boolean(enabled);
      if (!this.cameraOn || this.screenSharing) { this.blurEnabled = false; return false; }
      if (next === this.blurEnabled) return this.blurEnabled;
      if (!next) {
        this._stopBlurPipeline();
        if (this._blurRawTrack) {
          await this._replaceOutgoingVideoTrack(this._blurRawTrack, { stopOld: true });
          this._blurRawTrack = null;
        }
        this.blurEnabled = false;
        try { this.onLocalVideo(this.localStream, true, { preview: false }); } catch (_) { /* ignore */ }
        return false;
      }
      const current = this.localStream?.getVideoTracks?.()?.[0];
      if (!current) return false;
      this._blurRawTrack = current;
      const processed = await this._startBlurPipeline(current);
      if (!processed) { this._blurRawTrack = null; return false; }
      await this._replaceOutgoingVideoTrack(processed, { stopOld: false });
      this.blurEnabled = true;
      try { this.onLocalVideo(this.localStream, true, { preview: false, blur: true }); } catch (_) { /* ignore */ }
      return true;
    }

    _stopBlurPipeline() {
      if (this._blurRaf) { global.cancelAnimationFrame(this._blurRaf); this._blurRaf = 0; }
      if (this._blurCanvas) {
        try { this._blurCanvas.getTracks?.().forEach((t) => t.stop()); } catch (_) { /* ignore */ }
        this._blurCanvas = null;
      }
    }

    async _startBlurPipeline(sourceTrack) {
      try {
        const video = document.createElement("video");
        video.playsInline = true;
        video.muted = true;
        video.srcObject = new MediaStream([sourceTrack]);
        await video.play();
        const canvas = document.createElement("canvas");
        const ctx = canvas.getContext("2d", { alpha: false });
        canvas.width = sourceTrack.getSettings?.().width || 640;
        canvas.height = sourceTrack.getSettings?.().height || 480;
        const out = canvas.captureStream(24);
        const draw = () => {
          if (!this.blurEnabled && !this._blurRaf) return;
          try {
            ctx.filter = "blur(10px)";
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            ctx.filter = "none";
            ctx.save();
            ctx.beginPath();
            ctx.ellipse(canvas.width * 0.5, canvas.height * 0.45, canvas.width * 0.28, canvas.height * 0.38, 0, 0, Math.PI * 2);
            ctx.clip();
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            ctx.restore();
          } catch (_) { /* ignore */ }
          this._blurRaf = global.requestAnimationFrame(draw);
        };
        this.blurEnabled = true;
        this._blurCanvas = out;
        this._blurRaf = global.requestAnimationFrame(draw);
        return out.getVideoTracks()[0] || null;
      } catch (_) { return null; }
    }

    async setScreenShareEnabled(enabled) {
      const next = Boolean(enabled);
      if (this.ended || !this.pc) return false;
      if (next === this.screenSharing) return this.screenSharing;
      if (!next) {
        const restore = this._cameraTrackBeforeShare;
        this._cameraTrackBeforeShare = null;
        if (this._screenTrack) { try { this._screenTrack.stop(); } catch (_) { /* ignore */ } this._screenTrack = null; }
        this.screenSharing = false;
        if (restore && restore.readyState !== "ended") {
          await this._replaceOutgoingVideoTrack(restore, { stopOld: false });
          this.cameraOn = true;
        } else if (this.cameraOn) {
          await this.setCameraEnabled(false);
          await this.setCameraEnabled(true, { skipPreview: true });
        }
        try { this.onScreenShare(false); this.onLocalVideo(this.localStream, this.cameraOn, { preview: false }); } catch (_) { /* ignore */ }
        return false;
      }
      if (!navigator.mediaDevices?.getDisplayMedia) {
        throw Object.assign(new Error("screen_share_unsupported"), { code: "screen_share_unsupported" });
      }
      let display;
      try {
        display = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 15, max: 30 } }, audio: false });
      } catch (error) {
        throw Object.assign(new Error("screen_share_denied"), { code: "screen_share_denied", cause: error });
      }
      const screenTrack = display.getVideoTracks()[0];
      if (!screenTrack) throw Object.assign(new Error("screen_share_failed"), { code: "screen_share_failed" });
      if (this.blurEnabled) await this.setBlurEnabled(false);
      this._cameraTrackBeforeShare = this.localStream?.getVideoTracks?.()?.[0] || null;
      this._screenTrack = screenTrack;
      if (!this.cameraOn && !this._cameraTrackBeforeShare) {
        await this.sendCameraIntent(true);
        await sleep(200);
        if (!this.localStream) this.localStream = new MediaStream([screenTrack]);
        else this.localStream.addTrack(screenTrack);
        this.pc.addTrack(screenTrack, this.localStream);
        await this._renegotiate();
        this.cameraOn = true;
      } else {
        await this._replaceOutgoingVideoTrack(screenTrack, { stopOld: false });
      }
      this.screenSharing = true;
      screenTrack.addEventListener("ended", () => { void this.setScreenShareEnabled(false); });
      try { this.onScreenShare(true); this.onLocalVideo(this.localStream, true, { preview: false, screen: true }); } catch (_) { /* ignore */ }
      return true;
    }

    async startRecording() {
      if (this._recorder) return true;
      const parts = [];
      (this.localStream?.getAudioTracks?.() || []).forEach((t) => parts.push(t));
      (this.remoteStream?.getAudioTracks?.() || []).forEach((t) => parts.push(t));
      const video = this.remoteStream?.getVideoTracks?.()?.[0] || this.localStream?.getVideoTracks?.()?.[0] || null;
      if (video) parts.push(video);
      if (!parts.length) throw Object.assign(new Error("recording_no_media"), { code: "recording_no_media" });
      const mixed = new MediaStream(parts);
      let mime = "";
      if (typeof MediaRecorder !== "undefined") {
        if (MediaRecorder.isTypeSupported?.("video/webm;codecs=vp8,opus")) mime = "video/webm;codecs=vp8,opus";
        else if (MediaRecorder.isTypeSupported?.("video/webm")) mime = "video/webm";
      }
      this._recordChunks = [];
      this._recorder = new MediaRecorder(mixed, mime ? { mimeType: mime } : undefined);
      this._recorder.ondataavailable = (ev) => { if (ev.data && ev.data.size) this._recordChunks.push(ev.data); };
      this._recorder.onstop = () => {
        try {
          const blob = new Blob(this._recordChunks, { type: mime || "video/webm" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "workpass-call-" + Date.now() + ".webm";
          a.click();
          global.setTimeout(() => URL.revokeObjectURL(url), 5000);
        } catch (_) { /* ignore */ }
        this._recorder = null;
        this._recordChunks = [];
        try { this.onRecording(false); } catch (_) { /* ignore */ }
      };
      this._recorder.start(1000);
      try { this.onRecording(true); } catch (_) { /* ignore */ }
      return true;
    }

    stopRecording() {
      if (!this._recorder) return false;
      try { this._recorder.stop(); } catch (_) { this._recorder = null; }
      return true;
    }

    isRecording() { return Boolean(this._recorder && this._recorder.state === "recording"); }
    isScreenSharing() { return Boolean(this.screenSharing); }
    isBlurEnabled() { return Boolean(this.blurEnabled); }

    async switchCamera() {
      if (this.ended || !this.cameraOn || !this.pc) {
        throw new Error("camera_not_active");
      }
      const nextFacing = this.facingMode === "environment" ? "user" : "environment";
      const camStream = await navigator.mediaDevices.getUserMedia(
        videoConstraints(nextFacing, this.videoQuality || "hd"),
      );
      const newTrack = camStream.getVideoTracks()[0];
      if (!newTrack) throw new Error("camera_switch_failed");

      const sender = (this.pc.getSenders?.() || []).find((s) => s.track?.kind === "video");
      const oldTrack = this.localStream?.getVideoTracks?.()?.[0] || null;
      if (sender && typeof sender.replaceTrack === "function") {
        await sender.replaceTrack(newTrack);
      } else if (sender) {
        try {
          this.pc.removeTrack(sender);
        } catch (_) {
          /* ignore */
        }
        if (!this.localStream) this.localStream = camStream;
        this.pc.addTrack(newTrack, this.localStream);
        await this._renegotiate();
      } else {
        if (!this.localStream) this.localStream = camStream;
        else this.localStream.addTrack(newTrack);
        this.pc.addTrack(newTrack, this.localStream);
        await this._renegotiate();
      }

      if (oldTrack) {
        try {
          oldTrack.stop();
          this.localStream?.removeTrack?.(oldTrack);
        } catch (_) {
          /* ignore */
        }
      }
      if (this.localStream && !this.localStream.getVideoTracks().includes(newTrack)) {
        this.localStream.addTrack(newTrack);
      }
      // Stop leftover audio-less helper stream tracks except the one we keep.
      camStream.getTracks().forEach((t) => {
        if (t !== newTrack) {
          try {
            t.stop();
          } catch (_) {
            /* ignore */
          }
        }
      });
      this.facingMode = nextFacing;
      try {
        this.onLocalVideo(this.localStream, true);
      } catch (_) {
        /* ignore */
      }
      return this.facingMode;
    }

    async _renegotiate() {
      if (!this.pc || this.ended) return;
      // Wait briefly if a previous offer/answer is still in flight (glare).
      for (let i = 0; i < 8 && this.pc.signalingState !== "stable"; i += 1) {
        await sleep(120);
        if (this.ended || !this.pc) return;
      }
      if (this.pc.signalingState !== "stable") return;
      this._makingOffer = true;
      try {
        const offer = await this.pc.createOffer(OFFER_OPTS);
        await this.pc.setLocalDescription(offer);
        await this._sendSignal("offer", { type: offer.type, sdp: offer.sdp });
      } finally {
        this._makingOffer = false;
      }
    }

    _getAudioLevel(analyser, buffer) {
      if (!analyser || !buffer) return 0;
      analyser.getByteTimeDomainData(buffer);
      let sum = 0;
      for (let i = 0; i < buffer.length; i += 1) {
        const sample = (buffer[i] - 128) / 128;
        sum += sample * sample;
      }
      return Math.min(1, Math.sqrt(sum / buffer.length) * 5.5);
    }

    async _ensureAudioContext() {
      if (this.audioContext) return this.audioContext;
      try {
        this.audioContext = new (global.AudioContext || global.webkitAudioContext)();
        if (this.audioContext.state === "suspended") {
          await this.audioContext.resume();
        }
      } catch (_) {
        this.audioContext = null;
      }
      return this.audioContext;
    }

    _attachLocalAnalyser() {
      if (!this.audioContext || !this.localStream || this.localSource) return;
      try {
        this.localAnalyser = this.audioContext.createAnalyser();
        this.localAnalyser.fftSize = 256;
        this.localSource = this.audioContext.createMediaStreamSource(this.localStream);
        this.localSource.connect(this.localAnalyser);
      } catch (_) {
        /* ignore analyser setup errors */
      }
    }

    _attachRemoteAnalyser(stream) {
      if (!stream || this.remoteSource) return;
      void this._ensureAudioContext().then((ctx) => {
        if (!ctx || this.ended || this.remoteSource) return;
        try {
          this.remoteAnalyser = ctx.createAnalyser();
          this.remoteAnalyser.fftSize = 256;
          this.remoteSource = ctx.createMediaStreamSource(stream);
          this.remoteSource.connect(this.remoteAnalyser);
        } catch (_) {
          /* ignore analyser setup errors */
        }
      });
    }

    _startAudioMeters() {
      this._stopAudioMeters();
      void this._ensureAudioContext().then((ctx) => {
        if (!ctx || this.ended) return;
        this._attachLocalAnalyser();
        const tick = () => {
          if (this.ended) return;
          if (this.localAnalyser && !this.localMeterData) {
            this.localMeterData = new Uint8Array(this.localAnalyser.fftSize);
          }
          if (this.remoteAnalyser && !this.remoteMeterData) {
            this.remoteMeterData = new Uint8Array(this.remoteAnalyser.fftSize);
          }
          const local = this.muted ? 0 : this._getAudioLevel(this.localAnalyser, this.localMeterData);
          const remote =
            this.speakerOn && this.outputVolume > 0
              ? this._getAudioLevel(this.remoteAnalyser, this.remoteMeterData)
              : 0;
          try {
            this.onAudioLevels({ local, remote });
          } catch (_) {
            /* ignore UI callback errors */
          }
          if (!this.ended) this.meterTimer = global.requestAnimationFrame(tick);
        };
        this.meterTimer = global.requestAnimationFrame(tick);
      });
    }

    _stopAudioMeters() {
      if (this.meterTimer) global.cancelAnimationFrame(this.meterTimer);
      this.meterTimer = null;
      try {
        this.localSource?.disconnect();
        this.remoteSource?.disconnect();
      } catch (_) {
        /* ignore */
      }
      this.localSource = null;
      this.remoteSource = null;
      this.localAnalyser = null;
      this.remoteAnalyser = null;
      this.localMeterData = null;
      this.remoteMeterData = null;
      if (this.audioContext) {
        this.audioContext.close().catch(() => {});
        this.audioContext = null;
      }
      try {
        this.onAudioLevels({ local: 0, remote: 0 });
      } catch (_) {
        /* ignore */
      }
    }

    async _ensureMedia() {
      if (this.localStream) {
        this._applyMuteToLocalTracks();
        return this.localStream;
      }
      this.localStream = await navigator.mediaDevices.getUserMedia(AUDIO_CONSTRAINTS);
      this._applyMuteToLocalTracks();
      return this.localStream;
    }

    _ensureRemoteAudio() {
      if (this.remoteAudio) {
        this._applySpeakerToRemoteAudio();
        return this.remoteAudio;
      }
      const audio = document.createElement("audio");
      audio.autoplay = true;
      audio.playsInline = true;
      audio.style.display = "none";
      document.body.appendChild(audio);
      this.remoteAudio = audio;
      this._applySpeakerToRemoteAudio();
      return audio;
    }

    async _createPeer() {
      if (this.pc) return this.pc;
      this.pc = new RTCPeerConnection({
        iceServers: buildIceServers(this.iceServers),
        iceCandidatePoolSize: 4,
      });
      const stream = await this._ensureMedia();
      stream.getTracks().forEach((track) => this.pc.addTrack(track, stream));
      // Reserve a video m-line so late peer-camera renegotiation can be received
      // (offerToReceiveVideo is ignored on Unified Plan in many browsers).
      try {
        const hasVideoTx = (this.pc.getTransceivers?.() || []).some(
          (t) => t.receiver?.track?.kind === "video" || t.sender?.track?.kind === "video",
        );
        if (!hasVideoTx && (this.pc.getTransceivers?.() || []).length < 2) {
          this.pc.addTransceiver("video", { direction: "recvonly" });
        }
      } catch (_) { /* ignore */ }
      this._startAudioMeters();
      this.pc.ontrack = (event) => {
        const incoming = event.streams?.[0];
        const track = event.track;
        if (!track && !incoming) return;
        if (!this.remoteStream) {
          this.remoteStream = incoming || new MediaStream(track ? [track] : []);
        } else {
          const add = (t) => {
            if (!t) return;
            const exists = this.remoteStream.getTracks().some((x) => x.id === t.id);
            if (!exists) {
              try { this.remoteStream.addTrack(t); } catch (_) { /* ignore */ }
            }
          };
          add(track);
          (incoming?.getTracks?.() || []).forEach(add);
        }
        const remoteStream = this.remoteStream;
        const audio = this._ensureRemoteAudio();
        audio.srcObject = remoteStream;
        this._applySpeakerToRemoteAudio();
        audio.play().catch(() => {});
        this._attachRemoteAnalyser(remoteStream);
        const hasVideo = remoteStream.getVideoTracks().some(
          (t) => t && t.readyState !== "ended",
        );
        this.remoteHasVideo = hasVideo;
        try {
          this.onRemoteVideo(remoteStream, hasVideo);
        } catch (_) {
          /* ignore */
        }
        if (track) {
          track.onunmute = () => {
            const live = (this.remoteStream?.getVideoTracks?.() || []).some(
              (t) => t && t.readyState !== "ended",
            );
            this.remoteHasVideo = live;
            try { this.onRemoteVideo(this.remoteStream, live); } catch (_) { /* ignore */ }
          };
          track.onended = () => {
            const still = (this.remoteStream?.getVideoTracks?.() || []).some(
              (t) => t.readyState === "live" && t.enabled !== false,
            );
            this.remoteHasVideo = still;
            try {
              this.onRemoteVideo(this.remoteStream, still);
            } catch (_) {
              /* ignore */
            }
          };
        }
      };
      this.pc.onicecandidate = (event) => {
        if (!event.candidate || !this.callId) return;
        const prefix = this.role === "worker" ? "/api/worker-app" : "/api";
        this.api(`${prefix}/chat/calls/${encodeURIComponent(this.callId)}/signal`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            type: "ice-candidate",
            payload: event.candidate.toJSON(),
          }),
        }).catch(() => {
          /* ignore transient ICE signal errors while ringing */
        });
      };
      this.pc.onconnectionstatechange = () => {
        const state = this.pc?.connectionState || "";
        if (state === "connected") {
          this._stopRingtone();
          this.onState("connected");
          this._maybeAutoStartVideo();
        } else if (state === "failed") {
          void this.end("connection_failed");
        }
      };
      this.pc.oniceconnectionstatechange = () => {
        const ice = this.pc?.iceConnectionState || "";
        if (ice === "connected" || ice === "completed") {
          this._stopRingtone();
          this.onState("connected");
          this._maybeAutoStartVideo();
        } else if (ice === "failed") {
          void this.end("ice_failed");
        }
      };
      return this.pc;
    }

    async _sendSignal(type, payload) {
      const prefix = this.role === "worker" ? "/api/worker-app" : "/api";
      await this.api(`${prefix}/chat/calls/${encodeURIComponent(this.callId)}/signal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, payload }),
      });
    }

    async _applyRemoteSignal(signal) {
      const payload = signal.payload || {};
      const stype = signal.signalType;
      if (stype === "camera_intent") {
        try {
          this.onCameraIntent(payload || {});
        } catch (_) {
          /* ignore */
        }
        return;
      }
      if (stype === "camera_state") {
        try {
          this.onCameraState(payload || {});
        } catch (_) {
          /* ignore */
        }
        return;
      }
      if (stype === "call_image") {
        try {
          this.onCallImage(payload || {});
        } catch (_) {
          /* ignore */
        }
        return;
      }
      const pc = await this._createPeer();
      if (stype === "offer") {
        // Perfect negotiation: polite peer (worker) always accepts; admin yields if glare.
        const polite = this.role !== "admin";
        const offerCollision = this._makingOffer || pc.signalingState !== "stable";
        this._ignoreOffer = !polite && offerCollision;
        if (this._ignoreOffer) return;
        await pc.setRemoteDescription(new RTCSessionDescription(payload));
        await this._flushPendingIce(pc);
        const answer = await pc.createAnswer(OFFER_OPTS);
        await pc.setLocalDescription(answer);
        await this._sendSignal("answer", { type: answer.type, sdp: answer.sdp });
        this._stopRingtone();
        this.onState("connecting");
      } else if (stype === "answer") {
        if (this._ignoreOffer) return;
        await pc.setRemoteDescription(new RTCSessionDescription(payload));
        await this._flushPendingIce(pc);
        this._stopRingtone();
        this.onState("connecting");
      } else if (stype === "ice-candidate" && payload) {
        if (!pc.remoteDescription) {
          this.pendingIce.push(payload);
          return;
        }
        try {
          await pc.addIceCandidate(new RTCIceCandidate(payload));
        } catch (_) {
          /* ignore duplicate */
        }
      } else if (stype === "hangup") {
        await this.end("remote_hangup", { remote: true });
      }
    }

    async _flushPendingIce(pc) {
      const queued = this.pendingIce.splice(0, this.pendingIce.length);
      for (const candidate of queued) {
        try {
          await pc.addIceCandidate(new RTCIceCandidate(candidate));
        } catch (_) {
          /* ignore */
        }
      }
    }

    async _sendOfferAfterAccept() {
      if (this.offerSent || this.ended || !this.callId) return;
      this.offerSent = true;
      this._stopRingtone();
      await this._createPeer();
      this._makingOffer = true;
      try {
        const offer = await this.pc.createOffer(OFFER_OPTS);
        await this.pc.setLocalDescription(offer);
        await this._sendSignal("offer", { type: offer.type, sdp: offer.sdp });
      } finally {
        this._makingOffer = false;
      }
      this.onState("connecting");
    }

    _pollPath() {
      const prefix = this.role === "worker" ? "/api/worker-app" : "/api";
      let url = `${prefix}/chat/calls/${encodeURIComponent(this.callId)}/signals`;
      if (this.lastSignalId) url += `?since_id=${encodeURIComponent(this.lastSignalId)}`;
      return url;
    }

    _startPolling() {
      this._stopPolling();
      const tick = async () => {
        if (this.ended || !this.callId) return;
        try {
          const data = await this.api(this._pollPath());
          const call = data.call || {};
          if (call.status === "declined" || call.status === "missed" || call.status === "ended") {
            await this.end(call.endReason || call.status, { remote: true });
            return;
          }
          const signals = Array.isArray(data.signals) ? data.signals : [];
          for (const signal of signals) {
            try {
              await this._applyRemoteSignal(signal);
              this.lastSignalId = signal.id || this.lastSignalId;
            } catch (_) {
              /* keep cursor so a failed signal can be retried next tick */
            }
          }
          if (this.deferredOffer && !this.offerSent && call.status === "accepted") {
            await this._sendOfferAfterAccept();
          }
          if (this.role === "admin" && call.status === "accepted") {
            this._stopRingtone();
            this.onState("accepted");
          }
        } catch (_) {
          /* ignore transient poll errors while call is active */
        }
        if (!this.ended) this.pollTimer = global.setTimeout(tick, POLL_MS);
      };
      this.pollTimer = global.setTimeout(tick, POLL_MS);
    }

    _stopPolling() {
      if (this.pollTimer) global.clearTimeout(this.pollTimer);
      this.pollTimer = null;
    }

    _stopRingtone() {
      if (this.ringtone) this.ringtone.stop();
      this.ringtone = null;
    }

    async startOutgoing({ workerId, companyId }) {
      this.workerId = String(workerId || "");
      this.companyId = String(companyId || "");
      this.deferredOffer = true;
      this.offerSent = false;
      this.onState("dialing");
      const res = await this.api("/api/chat/calls", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ worker_id: this.workerId, company_id: companyId || undefined }),
      });
      const call = res.call || {};
      this.callId = String(call.id || "");
      this.iceServers = call.iceServers || [];
      if (!this.callId) throw new Error("call_start_failed");
      this.ringtone = createRingtone({ mode: "outgoing" });
      this.ringtone.start();
      this.ringDeadline = Date.now() + RING_TIMEOUT_MS;
      this.onState("ringing");
      // Wait until worker accepts before creating the offer (avoids lost early ICE).
      this._startPolling();
      this._scheduleRingTimeout();
    }

    async startWorkerOutgoing() {
      this.deferredOffer = true;
      this.offerSent = false;
      this.onState("dialing");
      const res = await this.api("/api/worker-app/chat/calls", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const call = res.call || {};
      this.callId = String(call.id || "");
      this.iceServers = call.iceServers || [];
      if (!this.callId) throw new Error("call_start_failed");
      this.ringtone = createRingtone({ mode: "outgoing" });
      this.ringtone.start();
      this.ringDeadline = Date.now() + RING_TIMEOUT_MS;
      this.onState("ringing");
      this._startPolling();
      this._scheduleRingTimeout();
    }

    startIncomingRingtone() {
      this._stopRingtone();
      this.ringtone = createRingtone({ mode: "incoming" });
      this.ringtone.start();
    }

    stopIncomingRingtone() {
      this._stopRingtone();
    }

    async acceptIncoming(callPayload) {
      this._stopRingtone();
      const call = callPayload || {};
      this.callId = String(call.id || "");
      this.iceServers = call.iceServers || [];
      if (!this.callId) throw new Error("call_missing");
      this.onState("connecting");
      const prefix = this.role === "worker" ? "/api/worker-app" : "/api";
      await this.api(`${prefix}/chat/calls/${encodeURIComponent(this.callId)}/accept`, { method: "POST" });
      await this._createPeer();
      this._startPolling();
    }

    async declineIncoming(callId) {
      this._stopRingtone();
      this.callId = String(callId || this.callId || "");
      const prefix = this.role === "worker" ? "/api/worker-app" : "/api";
      if (!this.callId) return;
      await this.api(`${prefix}/chat/calls/${encodeURIComponent(this.callId)}/decline`, { method: "POST" });
      await this.end("declined");
    }

    _maybeAutoStartVideo() {
      if (!this.preferVideo || this.cameraOn || this.cameraPreviewing || this._autoVideoStarted) return;
      this._autoVideoStarted = true;
      void this.setCameraEnabled(true).catch(() => {
        this._autoVideoStarted = false;
      });
    }

    async end(reason, opts = {}) {
      if (this.ended) return;
      this.ended = true;
      this._stopPolling();
      this._clearRingTimeout();
      this._stopRingtone();
      this._stopAudioMeters();
      this._stopQualityMonitor();
      try { this.stopRecording(); } catch (_) { /* ignore */ }
      try { this._stopBlurPipeline(); } catch (_) { /* ignore */ }
      try { await this.cancelCameraPreview(); } catch (_) { /* ignore */ }
      if (this._screenTrack) {
        try { this._screenTrack.stop(); } catch (_) { /* ignore */ }
        this._screenTrack = null;
      }
      const prefix = this.role === "worker" ? "/api/worker-app" : "/api";
      const remote = Boolean(opts?.remote) || /^(remote_|ended|missed|declined)/i.test(String(reason || ""));
      if (this.callId && !remote) {
        try {
          await this.api(`${prefix}/chat/calls/${encodeURIComponent(this.callId)}/end`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reason: reason || "hangup" }),
          });
        } catch (_) {
          /* ignore */
        }
      }
      if (this.pc) {
        this.pc.onicecandidate = null;
        this.pc.ontrack = null;
        this.pc.close();
        this.pc = null;
      }
      if (this.localStream) {
        this.localStream.getTracks().forEach((track) => track.stop());
        this.localStream = null;
      }
      this.remoteStream = null;
      this.cameraOn = false;
      this.cameraPreviewing = false;
      this.previewStream = null;
      this.remoteHasVideo = false;
      this.facingMode = "user";
      this.videoQuality = "hd";
      this.screenSharing = false;
      this.blurEnabled = false;
      this._blurRawTrack = null;
      this._cameraTrackBeforeShare = null;
      this._autoVideoStarted = false;
      this._lastQualityBytes = null;
      this._lastQualityTs = 0;
      if (this.remoteAudio) {
        this.remoteAudio.pause();
        this.remoteAudio.srcObject = null;
        this.remoteAudio.remove();
        this.remoteAudio = null;
      }
      this.onState("ended", reason || "hangup");
    }
  }

  global.SUPPIXVoiceCall = {
    isSupported() {
      return !!(global.RTCPeerConnection && navigator.mediaDevices?.getUserMedia);
    },
    createSession(options) {
      return new VoiceCallSession(options);
    },
    createRingtone,
    bindDraggablePip,
    resetDraggablePip,
    mapCameraError,
  };
})(window);
