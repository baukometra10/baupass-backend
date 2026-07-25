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
  const VIDEO_CONSTRAINTS = {
    video: {
      facingMode: "user",
      width: { ideal: 640 },
      height: { ideal: 480 },
      frameRate: { ideal: 24, max: 30 },
    },
    audio: false,
  };
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
      displayName,
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
      this.displayName = String(displayName || "").trim();
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

    async setCameraEnabled(enabled) {
      const next = Boolean(enabled);
      if (this.ended) return false;
      if (!this.pc || !this.callId) {
        throw new Error("call_not_connected");
      }
      if (next === this.cameraOn) return this.cameraOn;
      if (next) {
        await this.sendCameraIntent(true);
        await sleep(320);
        let videoTrack = this.localStream?.getVideoTracks?.()?.[0] || null;
        if (!videoTrack || videoTrack.readyState === "ended") {
          const camStream = await navigator.mediaDevices.getUserMedia(VIDEO_CONSTRAINTS);
          videoTrack = camStream.getVideoTracks()[0];
          if (!this.localStream) this.localStream = camStream;
          else this.localStream.addTrack(videoTrack);
          this.pc.addTrack(videoTrack, this.localStream);
        } else {
          videoTrack.enabled = true;
        }
        await this._renegotiate();
        this.cameraOn = true;
      } else {
        const senders = this.pc.getSenders?.() || [];
        for (const sender of senders) {
          if (sender.track?.kind === "video") {
            try {
              sender.track.stop();
            } catch (_) {
              /* ignore */
            }
            try {
              this.pc.removeTrack(sender);
            } catch (_) {
              /* ignore */
            }
          }
        }
        (this.localStream?.getVideoTracks?.() || []).forEach((track) => {
          try {
            track.stop();
            this.localStream.removeTrack(track);
          } catch (_) {
            /* ignore */
          }
        });
        await this._renegotiate();
        this.cameraOn = false;
      }
      try {
        await this._sendSignal("camera_state", {
          enabled: this.cameraOn,
          fromName: this.displayName || "",
        });
      } catch (_) {
        /* ignore */
      }
      try {
        this.onLocalVideo(this.localStream, this.cameraOn);
      } catch (_) {
        /* ignore */
      }
      return this.cameraOn;
    }

    async _renegotiate() {
      if (!this.pc || this.ended) return;
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
      this._startAudioMeters();
      this.pc.ontrack = (event) => {
        const remoteStream = event.streams[0] || (event.track ? new MediaStream([event.track]) : null);
        if (!remoteStream) return;
        this.remoteStream = remoteStream;
        const audio = this._ensureRemoteAudio();
        audio.srcObject = remoteStream;
        this._applySpeakerToRemoteAudio();
        audio.play().catch(() => {});
        this._attachRemoteAnalyser(remoteStream);
        const hasVideo = remoteStream.getVideoTracks().some((t) => t.readyState === "live" && t.enabled !== false);
        try {
          this.onRemoteVideo(remoteStream, hasVideo);
        } catch (_) {
          /* ignore */
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
        } else if (state === "failed") {
          void this.end("connection_failed");
        }
      };
      this.pc.oniceconnectionstatechange = () => {
        const ice = this.pc?.iceConnectionState || "";
        if (ice === "connected" || ice === "completed") {
          this._stopRingtone();
          this.onState("connected");
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

    async end(reason, opts = {}) {
      if (this.ended) return;
      this.ended = true;
      this._stopPolling();
      this._clearRingTimeout();
      this._stopRingtone();
      this._stopAudioMeters();
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
  };
})(window);
