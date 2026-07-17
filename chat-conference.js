/**
 * SUPPIX company conference — LiveKit SFU client (admin + worker web).
 * Requires LIVEKIT_* env on server; loads livekit-client from CDN on demand.
 */
(function initSuppixConference(global) {
  let room = null;
  let activeRoomId = "";
  let localVideoEl = null;

  function loadLiveKit() {
    if (global.LivekitClient || global.LiveKit) {
      return Promise.resolve(global.LivekitClient || global.LiveKit);
    }
    return new Promise((resolve, reject) => {
      const existing = document.querySelector("script[data-livekit]");
      if (existing) {
        existing.addEventListener("load", () => resolve(global.LivekitClient || global.LiveKit));
        existing.addEventListener("error", reject);
        return;
      }
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/livekit-client@2.9.1/dist/livekit-client.umd.min.js";
      s.async = true;
      s.dataset.livekit = "1";
      s.onload = () => resolve(global.LivekitClient || global.LiveKit);
      s.onerror = () => reject(new Error("livekit_cdn_failed"));
      document.head.appendChild(s);
    });
  }

  function ensureVideoGrid() {
    return document.getElementById("voiceCallVideoGrid");
  }

  function attachTrack(track, identity, isLocal) {
    const grid = ensureVideoGrid();
    if (!grid || !track) return;
    if (track.kind === "audio" && !isLocal) {
      const audio = document.createElement("audio");
      audio.autoplay = true;
      audio.playsInline = true;
      audio.dataset.identity = identity;
      track.attach(audio);
      document.body.appendChild(audio);
      return;
    }
    if (track.kind !== "video") return;
    let tile = grid.querySelector(`[data-identity="${CSS.escape(identity)}"]`);
    if (!tile) {
      tile = document.createElement("div");
      tile.className = "voice-call-video-tile";
      tile.dataset.identity = identity;
      tile.innerHTML = `<video autoplay playsinline ${isLocal ? "muted" : ""}></video><span class="tile-label"></span>`;
      grid.appendChild(tile);
    }
    const video = tile.querySelector("video");
    const label = tile.querySelector(".tile-label");
    if (label) label.textContent = isLocal ? "Sie" : identity;
    track.attach(video);
    if (isLocal) localVideoEl = video;
  }

  function renderParticipantRail(participants) {
    const rail = document.getElementById("voiceCallParticipantRail");
    if (!rail) return;
    const list = Array.isArray(participants) ? participants : [];
    rail.classList.toggle("hidden", !list.length);
    rail.innerHTML = list
      .map((p) => {
        const name = String(p.displayName || p.participantId || "?");
        const initials = name.split(/\s+/).map((x) => x[0] || "").join("").slice(0, 2).toUpperCase() || "?";
        const st = String(p.status || "");
        return `<div class="voice-call-participant-chip"><div class="ava">${initials}</div><div class="nm">${name}</div><div class="st">${st}</div></div>`;
      })
      .join("");
  }

  async function connect({ livekitUrl, token, roomId, participants, onDisconnect } = {}) {
    const LK = await loadLiveKit();
    if (!LK?.Room) throw new Error("livekit_unavailable");
    await disconnect();
    activeRoomId = String(roomId || "");
    const overlay = document.getElementById("voiceCallOverlay");
    overlay?.classList.add("is-conference");
    const chip = document.getElementById("voiceCallModeChip");
    if (chip) {
      chip.textContent = global.adminChatT?.("voiceCallModeConference") || "Firmenkonferenz";
      chip.classList.add("is-conference");
    }
    document.getElementById("voiceCallInviteBtn")?.removeAttribute("disabled");
    renderParticipantRail(participants);

    room = new LK.Room({ adaptiveStream: true, dynacast: true });
    room.on(LK.RoomEvent.TrackSubscribed, (track, _pub, participant) => {
      attachTrack(track, participant.identity || "remote", false);
    });
    room.on(LK.RoomEvent.TrackUnsubscribed, (track) => {
      track.detach().forEach((el) => el.remove());
    });
    room.on(LK.RoomEvent.Disconnected, () => {
      onDisconnect?.();
    });
    await room.connect(livekitUrl, token);
    await room.localParticipant.setMicrophoneEnabled(true);
    try {
      await room.localParticipant.setCameraEnabled(false);
    } catch (_) {
      /* cam optional */
    }
    room.localParticipant.audioTrackPublications?.forEach?.((pub) => {
      if (pub.track) attachTrack(pub.track, "local", true);
    });
    return room;
  }

  async function setCameraEnabled(enabled) {
    if (!room) return false;
    await room.localParticipant.setCameraEnabled(Boolean(enabled));
    room.localParticipant.videoTrackPublications?.forEach?.((pub) => {
      if (pub.track) attachTrack(pub.track, "local", true);
    });
    return Boolean(enabled);
  }

  async function setMicrophoneEnabled(enabled) {
    if (!room) return false;
    await room.localParticipant.setMicrophoneEnabled(Boolean(enabled));
    return Boolean(enabled);
  }

  async function disconnect() {
    try {
      await room?.disconnect();
    } catch (_) {
      /* ignore */
    }
    room = null;
    activeRoomId = "";
    document.querySelectorAll("audio[data-identity]").forEach((el) => el.remove());
    const grid = ensureVideoGrid();
    if (grid) grid.innerHTML = "";
    document.getElementById("voiceCallOverlay")?.classList.remove("is-conference");
    const chip = document.getElementById("voiceCallModeChip");
    if (chip) {
      chip.classList.remove("is-conference");
      chip.textContent = global.adminChatT?.("voiceCallModeDirect") || "1:1 Anruf";
    }
    document.getElementById("voiceCallInviteBtn")?.setAttribute("disabled", "disabled");
    document.getElementById("voiceCallParticipantRail")?.classList.add("hidden");
  }

  global.SUPPIXConference = {
    connect,
    disconnect,
    setCameraEnabled,
    setMicrophoneEnabled,
    renderParticipantRail,
    getActiveRoomId: () => activeRoomId,
    isActive: () => Boolean(room),
  };
})(typeof window !== "undefined" ? window : globalThis);
