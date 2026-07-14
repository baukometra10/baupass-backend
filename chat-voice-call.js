/**
 * SUPPIX voice call — WebRTC audio + HTTP signaling (admin + worker web).
 */
(function (global) {
  const POLL_MS = 700;
  const RING_TIMEOUT_MS = 45000;
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

  function createRingtone() {
    let ctx = null;
    let timer = null;
    let stopped = false;
    return {
      start() {
        try {
          ctx = new (global.AudioContext || global.webkitAudioContext)();
          const playPulse = () => {
            if (stopped || !ctx) return;
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = "sine";
            osc.frequency.value = 440;
            gain.gain.value = 0.08;
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.35);
          };
          playPulse();
          timer = global.setInterval(playPulse, 1200);
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
    constructor({ api, role, onState, onError }) {
      this.api = api;
      this.role = role;
      this.onState = onState || (() => {});
      this.onError = onError || (() => {});
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
      this.companyId = "";
      this.ringTimeoutTimer = null;
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
      if (this.localStream) {
        this.localStream.getAudioTracks().forEach((track) => {
          track.enabled = !this.muted;
        });
      }
      return this.muted;
    }

    async _ensureMedia() {
      if (this.localStream) return this.localStream;
      this.localStream = await navigator.mediaDevices.getUserMedia(AUDIO_CONSTRAINTS);
      return this.localStream;
    }

    _ensureRemoteAudio() {
      if (this.remoteAudio) return this.remoteAudio;
      const audio = document.createElement("audio");
      audio.autoplay = true;
      audio.playsInline = true;
      audio.style.display = "none";
      document.body.appendChild(audio);
      this.remoteAudio = audio;
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
      this.pc.ontrack = (event) => {
        const audio = this._ensureRemoteAudio();
        audio.srcObject = event.streams[0];
        audio.play().catch(() => {});
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
      this.ringtone = createRingtone();
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

    async acceptIncoming(callPayload) {
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
  };
})(window);
