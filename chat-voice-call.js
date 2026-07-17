/**
 * SUPPIX voice call — WebRTC audio + HTTP signaling (admin + worker web).
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

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Pleasant dual-voice ring / ringback (Web Audio).
   * mode: "incoming" = phone-like dual tone; "outgoing" = soft melodic ringback.
   */
  function createRingtone(options = {}) {
    const mode = options.mode === "incoming" ? "incoming" : "outgoing";
    let ctx = null;
    let timer = null;
    let stopped = false;
    let master = null;

    function tone(freqs, start, dur, peak = 0.11) {
      if (!ctx || !master) return;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.0001, start);
      g.gain.exponentialRampToValueAtTime(peak, start + 0.04);
      g.gain.exponentialRampToValueAtTime(peak * 0.75, start + dur * 0.55);
      g.gain.exponentialRampToValueAtTime(0.0001, start + dur);
      g.connect(master);
      freqs.forEach((hz, i) => {
        const osc = ctx.createOscillator();
        osc.type = i === 0 ? "sine" : "triangle";
        osc.frequency.setValueAtTime(hz, start);
        const og = ctx.createGain();
        og.gain.value = i === 0 ? 0.85 : 0.28;
        osc.connect(og);
        og.connect(g);
        osc.start(start);
        osc.stop(start + dur + 0.02);
      });
    }

    function playPattern() {
      if (stopped || !ctx) return;
      const t0 = ctx.currentTime + 0.02;
      if (mode === "incoming") {
        // Classic dual-tone ring (approx. 440 + 480), two bursts
        tone([440, 480], t0, 0.42, 0.13);
        tone([440, 480], t0 + 0.55, 0.42, 0.13);
      } else {
        // Soft ascending ringback motif
        tone([523.25], t0, 0.22, 0.09);
        tone([659.25], t0 + 0.2, 0.22, 0.1);
        tone([783.99, 523.25], t0 + 0.4, 0.38, 0.11);
      }
    }

    return {
      start() {
        if (stopped) return;
        try {
          ctx = new (global.AudioContext || global.webkitAudioContext)();
          master = ctx.createGain();
          master.gain.value = 0.85;
          master.connect(ctx.destination);
          const resume = () => {
            if (ctx?.state === "suspended") void ctx.resume();
          };
          resume();
          global.addEventListener?.("pointerdown", resume, { once: true });
          playPattern();
          timer = global.setInterval(playPattern, mode === "incoming" ? 2200 : 2400);
        } catch (_) {
          /* ignore */
        }
      },
      stop() {
        stopped = true;
        if (timer) global.clearInterval(timer);
        timer = null;
        if (ctx) {
          ctx.close().catch(() => {});
          ctx = null;
        }
        master = null;
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
    constructor({ api, role, onState, onError, onAudioLevels }) {
      this.api = api;
      this.role = role;
      this.onState = onState || (() => {});
      this.onError = onError || (() => {});
      this.onAudioLevels = onAudioLevels || (() => {});
      this.callId = "";
      this.workerId = "";
      this.iceServers = [];
      this.pc = null;
      this.localStream = null;
      this.remoteAudio = null;
      this.pollTimer = null;
      this.lastSignalId = "";
      this.ringtone = null;
      this.ended = false;
      this.ringDeadline = 0;
      this.muted = false;
      this.speakerOn = true;
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
              if (status === "ringing") void this.end("timeout");
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
        const remoteStream = event.streams[0];
        const audio = this._ensureRemoteAudio();
        audio.srcObject = remoteStream;
        this._applySpeakerToRemoteAudio();
        audio.play().catch(() => {});
        this._attachRemoteAnalyser(remoteStream);
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
      const pc = await this._createPeer();
      const payload = signal.payload || {};
      if (signal.signalType === "offer") {
        await pc.setRemoteDescription(new RTCSessionDescription(payload));
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        await this._sendSignal("answer", { type: answer.type, sdp: answer.sdp });
        this.onState("connected");
      } else if (signal.signalType === "answer") {
        await pc.setRemoteDescription(new RTCSessionDescription(payload));
        this._stopRingtone();
        this.onState("connected");
      } else if (signal.signalType === "ice-candidate" && payload) {
        try {
          await pc.addIceCandidate(new RTCIceCandidate(payload));
        } catch (_) {
          /* ignore duplicate */
        }
      } else if (signal.signalType === "hangup") {
        await this.end("remote_hangup");
      }
    }

    async _sendOfferAfterAccept() {
      if (this.offerSent || this.ended || !this.callId) return;
      this.offerSent = true;
      this._stopRingtone();
      await this._createPeer();
      const offer = await this.pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: false });
      await this.pc.setLocalDescription(offer);
      await this._sendSignal("offer", { type: offer.type, sdp: offer.sdp });
      this.onState("connected");
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
            await this.end(call.endReason || call.status);
            return;
          }
          const signals = Array.isArray(data.signals) ? data.signals : [];
          for (const signal of signals) {
            this.lastSignalId = signal.id || this.lastSignalId;
            await this._applyRemoteSignal(signal);
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
      await this._createPeer();
      const offer = await this.pc.createOffer({ offerToReceiveAudio: true, offerToReceiveVideo: false });
      await this.pc.setLocalDescription(offer);
      await this._sendSignal("offer", { type: offer.type, sdp: offer.sdp });
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

    async end(reason) {
      if (this.ended) return;
      this.ended = true;
      this._stopPolling();
      this._clearRingTimeout();
      this._stopRingtone();
      this._stopAudioMeters();
      const prefix = this.role === "worker" ? "/api/worker-app" : "/api";
      if (this.callId) {
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
