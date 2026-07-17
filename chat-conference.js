/**
 * SUPPIX company conference — LiveKit SFU client (admin + worker web).
 * Requires LIVEKIT_* env on server; loads livekit-client from CDN on demand.
 */
(function initSuppixConference(global) {
  const LIVEKIT_CDN = "https://cdn.jsdelivr.net/npm/livekit-client@2.20.1/dist/livekit-client.umd.min.js";
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
        existing.addEventListener("error", () => reject(new Error("livekit_cdn_failed")));
        return;
      }
      const s = document.createElement("script");
      s.src = LIVEKIT_CDN;
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

  function formatConnectError(err, url) {
    const host = String(url || "").replace(/^wss?:\/\//i, "").split("/")[0];
    const msg = String(err?.message || err || "connect_failed");
    const reason = err?.reasonName || err?.reason || "";
    const status = err?.status != null ? ` status=${err.status}` : "";
    const ctx = err?.context ? ` ctx=${JSON.stringify(err.context)}` : "";
    const hint =
      (typeof global.adminChatT === "function" && global.adminChatT("conferenceConnectHint"))
      || (typeof global.t === "function" && global.t("conferenceConnectHint"))
      || "Tip: VPN off · https://livekit.io/connection-test";
    const parts = [msg];
    if (reason) parts.push(`reason=${reason}`);
    if (status) parts.push(status.trim());
    if (ctx) parts.push(ctx.trim());
    parts.push(`(LiveKit: ${host || url || "?"})`);
    parts.push(hint);
    return parts.join(" ");
  }

  function youLabel() {
    return (
      (typeof global.adminChatT === "function" && global.adminChatT("conferenceYou"))
      || (typeof global.t === "function" && global.t("conferenceYou"))
      || (typeof global.t === "function" && global.t("voiceCallMicLabel"))
      || "You"
    );
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
    if (label) label.textContent = isLocal ? youLabel() : identity;
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
      chip.textContent = global.adminChatT?.("voiceCallModeConference") || global.t?.("voiceCallModeConference") || "Conference";
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
    const url = String(livekitUrl || "").trim().replace(/\/+$/, "");
    if (!url || !token) {
      throw new Error("livekit_connect_missing_url_or_token");
    }
    try {
      if (typeof room.prepareConnection === "function") {
        try {
          await room.prepareConnection(url, token);
        } catch (_) {
          /* prepare is best-effort */
        }
      }
      await room.connect(url, token, {
        autoSubscribe: true,
        maxRetries: 2,
      });
    } catch (err) {
      try {
        await room.disconnect();
      } catch (_) {
        /* ignore */
      }
      room = null;
      throw new Error(formatConnectError(err, url));
    }
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
      chip.textContent = global.adminChatT?.("voiceCallModeDirect") || global.t?.("voiceCallModeDirect") || "1:1";
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
