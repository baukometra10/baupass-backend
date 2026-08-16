/**
 * Worker PWA voice call — incoming poll + full-screen overlay (uses chat-voice-call.js).
 */
(function initWorkerVoiceCall(global) {
  const POLL_MS = 2200;

  function t(key, fallback) {
    try {
      const v = typeof global.t === "function" ? global.t(key) : "";
      if (v && v !== key) return v;
    } catch (_) {
      /* ignore */
    }
    return fallback || key;
  }

  function formatDuration(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const m = String(Math.floor(total / 60)).padStart(2, "0");
    const s = String(total % 60).padStart(2, "0");
    return `${m}:${s}`;
  }

  function ensureOverlay() {
    let overlay = document.getElementById("workerVoiceCallOverlay");
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.id = "workerVoiceCallOverlay";
    overlay.className = "worker-voice-call-overlay hidden";
    overlay.setAttribute("role", "dialog");
    overlay.innerHTML = `
      <div id="workerVoiceCallVideoStage" class="worker-voice-call-video-stage" aria-hidden="true">
        <video id="workerVoiceCallRemoteVideo" playsinline autoplay></video>
        <video id="workerVoiceCallLocalPip" class="worker-voice-call-local-pip hidden" playsinline autoplay muted></video>
      </div>
      <div class="worker-voice-call-stage">
        <div class="worker-voice-call-badge">🔒 ${t("voiceCallSecure", "Sicherer Sprachkanal")}</div>
        <div class="worker-voice-call-avatar" id="workerVoiceCallAvatar">AG</div>
        <h4 id="workerVoiceCallTitle">${t("voiceCallTitle", "Sprachanruf")}</h4>
        <p id="workerVoiceCallStatus">${t("voiceCallRinging", "Eingehender Anruf…")}</p>
        <p id="workerVoiceCallPeerBanner" class="worker-voice-call-peer-banner hidden" role="status" aria-live="assertive"></p>
        <p id="workerVoiceCallTimer" class="worker-voice-call-timer hidden">00:00</p>
        <div id="workerVoiceCallLiveWave" class="worker-voice-call-live-wave"></div>
        <div class="worker-voice-call-meters" id="workerVoiceCallMeters">
          <div class="worker-voice-call-meter"><span>${t("voiceCallMicLabel", "Sie")}</span><div><i id="workerVoiceCallMicFill"></i></div></div>
          <div class="worker-voice-call-meter"><span>${t("voiceCallRemoteLabel", "Arbeitgeber")}</span><div><i id="workerVoiceCallRemoteFill"></i></div></div>
        </div>
        <div id="workerVoiceCallPreviewBar" class="worker-voice-call-preview-bar hidden">
          <span>${t("voiceCallCamPreviewHint", "Kamera-Vorschau — noch nicht gesendet")}</span>
          <div>
            <button type="button" id="workerVoiceCallPreviewCancel">${t("voiceCallCamPreviewCancel", "Abbrechen")}</button>
            <button type="button" id="workerVoiceCallPreviewConfirm" class="primary">${t("voiceCallCamPreviewConfirm", "Freigeben")}</button>
          </div>
          <p id="workerVoiceCallCamError" class="hidden"></p>
        </div>
      </div>
      <div class="worker-voice-call-footer">
        <div class="worker-voice-call-controls incoming-only">
          <button type="button" id="workerVoiceCallDeclineBtn" class="danger" aria-label="${t("voiceCallDecline", "Ablehnen")}" title="${t("voiceCallDecline", "Ablehnen")}"><span class="wvc-ico" aria-hidden="true"><svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg></span><span class="wvc-label">${t("voiceCallDecline", "Ablehnen")}</span></button>
          <button type="button" id="workerVoiceCallAcceptBtn" class="primary" aria-label="${t("voiceCallAccept", "Annehmen")}" title="${t("voiceCallAccept", "Annehmen")}"><span class="wvc-ico" aria-hidden="true"><svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor"><path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1.1-.2 1.2.4 2.5.6 3.8.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.6 21 3 13.4 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.6.6 3.8.1.4 0 .8-.2 1.1L6.6 10.8z"/></svg></span><span class="wvc-label">${t("voiceCallAccept", "Annehmen")}</span></button>
        </div>
        <div class="worker-voice-call-controls active-only hidden">
          <button type="button" id="workerVoiceCallMuteBtn" aria-label="${t("voiceCallMute", "Stumm")}" title="${t("voiceCallMute", "Stumm")}"><span class="wvc-ico" aria-hidden="true"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"/><path d="M19 11a7 7 0 0 1-14 0"/><path d="M12 19v3"/></svg></span><span class="wvc-label">${t("voiceCallMute", "Stumm")}</span></button>
          <button type="button" id="workerVoiceCallCamBtn" aria-label="${t("voiceCallCamera", "Kamera")}" title="${t("voiceCallCamera", "Kamera")}"><span class="wvc-ico" aria-hidden="true"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="7" width="13" height="10" rx="2"/><path d="M16 10l5-3v10l-5-3z"/></svg></span><span class="wvc-label">${t("voiceCallCamera", "Kamera")}</span></button>
          <button type="button" id="workerVoiceCallFlipBtn" class="flip-only" aria-label="${t("voiceCallFlipCamera", "Kamera wechseln")}" title="${t("voiceCallFlipCamera", "Kamera wechseln")}"><span class="wvc-ico" aria-hidden="true"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M16 4h4v4"/><path d="M20 4l-5.5 5.5"/><path d="M8 20H4v-4"/><path d="M4 20l5.5-5.5"/><rect x="7" y="8" width="10" height="8" rx="1.5"/></svg></span><span class="wvc-label">${t("voiceCallFlipCamera", "Drehen")}</span></button>
          <button type="button" id="workerVoiceCallSpeakerBtn" aria-label="${t("voiceCallSpeaker", "Lautsprecher")}" title="${t("voiceCallSpeaker", "Lautsprecher")}"><span class="wvc-ico" aria-hidden="true"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 10v4h3l5 4V6l-5 4H4z"/><path d="M16 9a4 4 0 0 1 0 6"/><path d="M18.5 7a7 7 0 0 1 0 10"/></svg></span><span class="wvc-label">${t("voiceCallSpeaker", "Lautsp.")}</span></button>
          <button type="button" id="workerVoiceCallHangupBtn" class="danger" aria-label="${t("voiceCallHangup", "Auflegen")}" title="${t("voiceCallHangup", "Auflegen")}"><span class="wvc-ico" aria-hidden="true"><svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor"><path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1.1-.2 1.2.4 2.5.6 3.8.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.6 21 3 13.4 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.6.6 3.8.1.4 0 .8-.2 1.1L6.6 10.8z" transform="rotate(135 12 12)"/></svg></span><span class="wvc-label">${t("voiceCallHangup", "Auflegen")}</span></button>
        </div>
        <div class="worker-voice-call-toolbar" id="workerVoiceCallToolbar">
          <button type="button" id="workerVoiceCallShareBtn" class="wvc-pill" aria-label="${t("voiceCallShareImage", "Bild")}" title="${t("voiceCallShareImage", "Bild")}">${t("voiceCallShareImage", "Bild")}</button>
          <button type="button" id="workerVoiceCallBlurBtn" class="wvc-pill" aria-label="${t("voiceCallBlur", "Blur")}" title="${t("voiceCallBlur", "Blur")}">${t("voiceCallBlur", "Blur")}</button>
          <button type="button" id="workerVoiceCallScreenBtn" class="wvc-pill" aria-label="${t("voiceCallScreenShare", "Screen")}" title="${t("voiceCallScreenShare", "Screen")}">${t("voiceCallScreenShare", "Screen")}</button>
          <button type="button" id="workerVoiceCallRecordBtn" class="wvc-pill" aria-label="${t("voiceCallRecord", "REC")}" title="${t("voiceCallRecord", "REC")}">${t("voiceCallRecord", "REC")}</button>
        </div>
        <input type="file" id="workerVoiceCallShareInput" accept="image/*" style="display:none" />
      </div>`;
    document.body.appendChild(overlay);
    if (!document.getElementById("workerVoiceCallStyles")) {
      const style = document.createElement("style");
      style.id = "workerVoiceCallStyles";
      style.textContent = `
.worker-voice-call-overlay{position:fixed;inset:0;z-index:14000;display:grid;grid-template-rows:minmax(0,1fr) auto;padding:0;height:100%;height:100dvh;max-height:100dvh;background:radial-gradient(ellipse 120% 80% at 50% -10%,rgba(0,168,132,.22),transparent 55%),radial-gradient(ellipse 60% 40% at 100% 100%,rgba(37,99,235,.12),transparent 50%),linear-gradient(165deg,#071018 0%,#0b141a 45%,#0a1620 100%);overflow:hidden}
.worker-voice-call-overlay.hidden{display:none}
.worker-voice-call-overlay.is-conference .worker-voice-call-avatar{width:112px;height:112px;font-size:2rem}
.worker-voice-call-overlay.is-ringing .worker-voice-call-avatar,.worker-voice-call-overlay.is-connecting .worker-voice-call-avatar{width:112px;height:112px;font-size:2rem;margin-bottom:.65rem}
.worker-voice-call-overlay.is-ringing .worker-voice-call-live-wave,.worker-voice-call-overlay.is-ringing .worker-voice-call-meters,.worker-voice-call-overlay.is-ringing .worker-voice-call-toolbar,.worker-voice-call-overlay.is-connecting .worker-voice-call-live-wave,.worker-voice-call-overlay.is-connecting .worker-voice-call-meters,.worker-voice-call-overlay.is-connecting .worker-voice-call-toolbar{display:none!important}
.worker-voice-call-video-stage{display:none;position:absolute;inset:0;z-index:1;background:#0b141a;overflow:hidden}
.worker-voice-call-overlay.is-video .worker-voice-call-video-stage{display:block}
.worker-voice-call-overlay.is-video{background:#0b141a;grid-template-rows:1fr}
.worker-voice-call-overlay.is-video .worker-voice-call-avatar,
.worker-voice-call-overlay.is-video .worker-voice-call-live-wave,
.worker-voice-call-overlay.is-video .worker-voice-call-meters,
.worker-voice-call-overlay.is-video .worker-voice-call-badge{display:none!important}
.worker-voice-call-overlay.is-video .worker-voice-call-stage{position:relative;z-index:2;pointer-events:none;justify-content:flex-start;padding-top:max(1.25rem,env(safe-area-inset-top,0px))}
.worker-voice-call-overlay.is-video .worker-voice-call-stage h4,
.worker-voice-call-overlay.is-video #workerVoiceCallStatus,
.worker-voice-call-overlay.is-video #workerVoiceCallTimer,
.worker-voice-call-overlay.is-video #workerVoiceCallPeerBanner{text-shadow:0 1px 8px rgba(0,0,0,.75);pointer-events:auto}
.worker-voice-call-overlay.is-video .worker-voice-call-footer{position:absolute;left:0;right:0;bottom:0;z-index:4;pointer-events:auto;background:linear-gradient(0deg,rgba(0,0,0,.78),rgba(0,0,0,.28) 55%,transparent);padding:.85rem 1rem calc(1.05rem + env(safe-area-inset-bottom,0px));transition:opacity .28s ease,transform .28s ease}
.worker-voice-call-overlay.is-video.chrome-hidden .worker-voice-call-footer{opacity:.96;pointer-events:auto;transform:none}
.worker-voice-call-overlay.is-video.chrome-hidden .worker-voice-call-stage h4,
.worker-voice-call-overlay.is-video.chrome-hidden #workerVoiceCallStatus{opacity:.35}
.worker-voice-call-overlay.is-video .worker-voice-call-toolbar{display:flex;justify-content:center;margin-top:.45rem}
.worker-voice-call-overlay.is-video .worker-voice-call-controls{padding:.15rem 0 .1rem}
.worker-voice-call-overlay.is-video .worker-voice-call-controls button{backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}
#workerVoiceCallRemoteVideo{width:100%;height:100%;object-fit:cover;background:#0b141a}
.worker-voice-call-local-pip{position:absolute;right:max(12px,env(safe-area-inset-right,0px));top:max(72px,calc(env(safe-area-inset-top,0px) + 4.5rem));bottom:auto;width:min(118px,26vw);aspect-ratio:3/4;border-radius:14px;object-fit:cover;background:#111b21;border:2px solid rgba(255,255,255,.35);box-shadow:0 12px 32px rgba(0,0,0,.45);transform:scaleX(-1);z-index:3;touch-action:none;cursor:grab;user-select:none}
.worker-voice-call-local-pip.hidden{display:none}
#workerVoiceCallFlipBtn{display:none}
.worker-voice-call-overlay.is-video #workerVoiceCallFlipBtn,
.worker-voice-call-overlay.cam-on #workerVoiceCallFlipBtn{display:inline-flex}
.worker-voice-call-stage{width:100%;max-width:520px;margin:0 auto;min-height:0;overflow:auto;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;color:#e9edef;padding:max(1.25rem,env(safe-area-inset-top,0px)) 1.25rem .5rem;-webkit-overflow-scrolling:touch}
.worker-voice-call-footer{width:100%;max-width:640px;margin:0 auto;padding:.55rem 1rem calc(.95rem + env(safe-area-inset-bottom,0px));background:linear-gradient(180deg,transparent,rgba(0,0,0,.62) 22%);position:relative;z-index:30}
.worker-voice-call-badge{display:inline-flex;padding:.35rem .75rem;border-radius:999px;border:1px solid rgba(0,168,132,.35);font-size:.75rem;margin-bottom:1rem;color:rgba(233,237,239,.85);background:rgba(0,168,132,.12)}
.worker-voice-call-avatar{width:180px;height:180px;margin:0 auto 1.25rem;border-radius:50%;display:grid;place-items:center;font-size:3rem;font-weight:800;background:linear-gradient(145deg,#00a884,#128c7e);color:#e9edef;box-shadow:0 24px 64px rgba(0,168,132,.28)}
.worker-voice-call-stage h4{margin:0 0 .35rem;font-size:2rem;color:#e9edef}
.worker-voice-call-stage p{color:rgba(233,237,239,.72);max-width:22rem;line-height:1.35}
.worker-voice-call-timer.hidden{display:none}
.worker-voice-call-live-wave{display:flex;align-items:flex-end;justify-content:center;gap:3px;height:72px;width:min(320px,88vw);margin:1rem auto}
.worker-voice-call-live-wave span{width:3px;border-radius:999px;height:18%;background:linear-gradient(180deg,#00a884,#128c7e);transition:height .08s linear}
.worker-voice-call-meters{width:min(300px,100%);margin:.5rem auto;display:grid;gap:.45rem;text-align:left}
.worker-voice-call-meter{display:grid;grid-template-columns:4.5rem 1fr;gap:.5rem;align-items:center;font-size:.72rem;text-transform:uppercase;opacity:.8}
.worker-voice-call-meter div{height:8px;border-radius:999px;background:rgba(255,255,255,.12);overflow:hidden}
.worker-voice-call-meter i{display:block;height:100%;width:0%;background:linear-gradient(90deg,#00a884,#128c7e)}
.worker-voice-call-controls{display:flex;gap:.75rem 1rem;justify-content:center;align-items:flex-start;flex-wrap:wrap;padding:.35rem 0 .15rem}
.worker-voice-call-controls.hidden{display:none}
.worker-voice-call-controls button{min-width:4.4rem;width:4.4rem;height:auto;min-height:4.35rem;border-radius:1.15rem;padding:.65rem .35rem .4rem;border:1px solid rgba(255,255,255,.14);color:#e9edef;font-weight:600;cursor:pointer;box-shadow:0 10px 28px rgba(0,0,0,.32);display:inline-flex;flex-direction:column;align-items:center;justify-content:center;gap:.28rem;transition:transform .12s ease,filter .15s ease;background:rgba(255,255,255,.12)}
.worker-voice-call-controls button:active{transform:scale(.92)}
.worker-voice-call-controls button .wvc-ico{display:grid;place-items:center;line-height:0;width:1.55rem;height:1.55rem}
.worker-voice-call-controls button .wvc-ico svg{display:block;width:100%;height:100%;filter:drop-shadow(0 1px 2px rgba(0,0,0,.25))}
.worker-voice-call-controls button .wvc-label{display:block;font-size:.62rem;font-weight:650;letter-spacing:.01em;line-height:1.05;opacity:.9;white-space:nowrap;max-width:4.6rem;overflow:hidden;text-overflow:ellipsis}
.worker-voice-call-controls button.primary{background:#00a884;border-color:rgba(52,211,153,.45);width:4.85rem;min-width:4.85rem;min-height:4.85rem;border-radius:1.25rem}
.worker-voice-call-controls button.danger{background:#e53935;border-color:rgba(248,113,113,.4);width:4.85rem;min-width:4.85rem;min-height:4.85rem;border-radius:1.25rem}
.worker-voice-call-controls button.danger#workerVoiceCallHangupBtn{width:5.25rem;min-width:5.25rem;min-height:5.25rem;border-radius:1.35rem}
.worker-voice-call-controls button.is-active{background:#f8fafc!important;color:#b91c1c!important;box-shadow:0 0 0 3px rgba(248,113,113,.35)}
.worker-voice-call-controls button.is-active .wvc-ico{color:#b91c1c}
.worker-voice-call-toolbar{display:flex;gap:.4rem;justify-content:center;flex-wrap:wrap;margin-top:.55rem}
.worker-voice-call-toolbar.hidden{display:none}
.worker-voice-call-toolbar .wvc-pill{border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.08);color:#e9edef;border-radius:999px;padding:.45rem .9rem;font:inherit;font-size:.82rem;font-weight:600;cursor:pointer;min-width:auto;width:auto;height:auto;min-height:auto;box-shadow:none}
.worker-voice-call-toolbar .wvc-pill.is-active{background:#f8fafc;color:#b91c1c}
.worker-voice-call-peer-banner{margin:.55rem auto 0;max-width:22rem;padding:.55rem .85rem;border-radius:12px;background:rgba(251,191,36,.16);border:1px solid rgba(251,191,36,.45);color:#fde68a;font-size:.84rem;font-weight:600;line-height:1.35}
.worker-voice-call-peer-banner.hidden{display:none}
.worker-voice-call-preview-bar{margin:.65rem auto 0;max-width:22rem;padding:.7rem .85rem;border-radius:14px;background:rgba(15,23,42,.72);border:1px solid rgba(148,163,184,.35);color:#e2e8f0;display:grid;gap:.5rem;pointer-events:auto;position:relative;z-index:5}
.worker-voice-call-preview-bar.hidden{display:none}
.worker-voice-call-preview-bar div{display:flex;gap:.45rem;justify-content:center;flex-wrap:wrap}
.worker-voice-call-preview-bar button{min-width:auto;width:auto;height:auto;min-height:36px;border-radius:999px;padding:.35rem .85rem;font-size:.8rem;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.1);color:#e9edef;cursor:pointer}
.worker-voice-call-preview-bar button.primary{background:#00a884}
.worker-voice-call-preview-bar p{margin:0;color:#fecaca;font-size:.78rem}
.worker-voice-call-preview-bar p.hidden{display:none}
#voiceCallVideoGrid{width:min(920px,94vw);margin:.75rem auto 0;display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:.65rem;max-height:36vh;overflow:auto}
.chat-call-log,.worker-chat-call-log{display:inline-flex;align-items:center;gap:.55rem;padding:.45rem .75rem;border-radius:999px;background:rgba(255,255,255,.08);border:1px solid rgba(0,168,132,.22)}
.chat-call-log-btn,.worker-chat-call-log-btn{margin-top:.35rem;border-radius:999px;padding:.35rem .75rem;border:1px solid rgba(0,168,132,.35);background:rgba(0,168,132,.18);color:#ecfeff;font-size:.75rem;font-weight:600;cursor:pointer}`;
      document.head.appendChild(style);
    }
    overlay.querySelector("#workerVoiceCallDeclineBtn")?.addEventListener("click", () => controller?.decline());
    overlay.querySelector("#workerVoiceCallAcceptBtn")?.addEventListener("click", () => controller?.accept());
    overlay.querySelector("#workerVoiceCallHangupBtn")?.addEventListener("click", () => controller?.hangup());
    overlay.querySelector("#workerVoiceCallMuteBtn")?.addEventListener("click", () => controller?.toggleMute());
    overlay.querySelector("#workerVoiceCallSpeakerBtn")?.addEventListener("click", () => controller?.toggleSpeaker());
    overlay.querySelector("#workerVoiceCallCamBtn")?.addEventListener("click", () => controller?.toggleCamera());
    overlay.querySelector("#workerVoiceCallFlipBtn")?.addEventListener("click", () => controller?.flipCamera());
    overlay.querySelector("#workerVoiceCallShareBtn")?.addEventListener("click", () => controller?.shareImage());
    overlay.querySelector("#workerVoiceCallBlurBtn")?.addEventListener("click", () => controller?.toggleBlur());
    overlay.querySelector("#workerVoiceCallScreenBtn")?.addEventListener("click", () => controller?.toggleScreen());
    overlay.querySelector("#workerVoiceCallRecordBtn")?.addEventListener("click", () => controller?.toggleRecord());
    overlay.querySelector("#workerVoiceCallPreviewConfirm")?.addEventListener("click", () => controller?.confirmPreview());
    overlay.querySelector("#workerVoiceCallPreviewCancel")?.addEventListener("click", () => controller?.cancelPreview());
    overlay.querySelector("#workerVoiceCallShareInput")?.addEventListener("change", (event) => {
      void controller?.shareImageFile?.(event.target?.files?.[0]);
      if (event.target) event.target.value = "";
    });
    overlay.querySelector("#workerVoiceCallVideoStage")?.addEventListener("click", () => bumpChrome());
    const wave = overlay.querySelector("#workerVoiceCallLiveWave");
    if (wave && !wave.childElementCount) wave.innerHTML = Array.from({ length: 28 }, () => "<span></span>").join("");
    return overlay;
  }

  let chromeHideTimer = null;
  let directLocalOn = false;
  let directRemoteOn = false;

  function bumpChrome() {
    const overlay = document.getElementById("workerVoiceCallOverlay");
    if (!overlay?.classList.contains("is-video")) return;
    overlay.classList.remove("chrome-hidden");
    if (chromeHideTimer) clearTimeout(chromeHideTimer);
    // Keep controls dock reachable; only fade name/status chrome.
    chromeHideTimer = setTimeout(() => {
      if (document.getElementById("workerVoiceCallOverlay")?.classList.contains("is-video")) {
        document.getElementById("workerVoiceCallOverlay")?.classList.add("chrome-hidden");
      }
    }, 5200);
  }

  function syncVideoStage() {
    const overlay = document.getElementById("workerVoiceCallOverlay");
    const stage = document.getElementById("workerVoiceCallVideoStage");
    const remoteEl = document.getElementById("workerVoiceCallRemoteVideo");
    const pip = document.getElementById("workerVoiceCallLocalPip");
    const conference = Boolean(conferenceActive);
    const videoActive = !conference && (directLocalOn || directRemoteOn);
    overlay?.classList.toggle("is-video", videoActive);
    overlay?.classList.toggle("cam-on", directLocalOn);
    if (stage) stage.setAttribute("aria-hidden", videoActive ? "false" : "true");
    if (!videoActive) {
      if (chromeHideTimer) clearTimeout(chromeHideTimer);
      overlay?.classList.remove("chrome-hidden");
      if (remoteEl) {
        remoteEl.srcObject = null;
        remoteEl.style.transform = "";
      }
      if (pip) {
        pip.srcObject = null;
        pip.classList.add("hidden");
        global.SUPPIXVoiceCall?.resetDraggablePip?.(pip);
      }
      return;
    }
    bumpChrome();
  }

  function revealLocalPip(stream) {
    const pip = document.getElementById("workerVoiceCallLocalPip");
    if (!pip || !stream) return;
    if (pip.srcObject !== stream) pip.srcObject = stream;
    pip.muted = true;
    pip.play?.().catch?.(() => {});
    pip.classList.remove("hidden");
    global.SUPPIXVoiceCall?.bindDraggablePip?.(pip);
  }

  function setLocalVideo(stream, enabled) {
    const pip = document.getElementById("workerVoiceCallLocalPip");
    const remoteEl = document.getElementById("workerVoiceCallRemoteVideo");
    directLocalOn = Boolean(enabled && stream);
    document.getElementById("workerVoiceCallOverlay")?.classList.toggle("cam-on", directLocalOn);
    if (directLocalOn) {
      if (!directRemoteOn && remoteEl) {
        if (remoteEl.srcObject !== stream) remoteEl.srcObject = stream;
        remoteEl.muted = true;
        remoteEl.style.transform = "scaleX(-1)";
        remoteEl.play?.().catch?.(() => {});
        pip?.classList.add("hidden");
      } else {
        revealLocalPip(stream);
        if (remoteEl) remoteEl.style.transform = "";
      }
    } else if (pip) {
      pip.srcObject = null;
      pip.classList.add("hidden");
      global.SUPPIXVoiceCall?.resetDraggablePip?.(pip);
      if (remoteEl && !directRemoteOn) {
        remoteEl.srcObject = null;
        remoteEl.style.transform = "";
      }
    }
    syncVideoStage();
  }

  function setRemoteVideo(stream, hasVideo) {
    const remoteEl = document.getElementById("workerVoiceCallRemoteVideo");
    const pip = document.getElementById("workerVoiceCallLocalPip");
    directRemoteOn = Boolean(hasVideo && stream);
    if (remoteEl) {
      if (directRemoteOn) {
        // Always re-bind: late video tracks can join an existing MediaStream object.
        if (remoteEl.srcObject !== stream) {
          remoteEl.srcObject = stream;
        } else {
          remoteEl.srcObject = null;
          remoteEl.srcObject = stream;
        }
        remoteEl.muted = true;
        remoteEl.style.transform = "";
        remoteEl.play?.().catch?.(() => {});
        if (directLocalOn && session?.getLocalStream) {
          const local = session.getLocalStream();
          if (local) revealLocalPip(local);
        }
      } else if (!directLocalOn) {
        remoteEl.srcObject = null;
      } else if (session?.getLocalStream) {
        const local = session.getLocalStream();
        if (local) {
          if (remoteEl.srcObject !== local) remoteEl.srcObject = local;
          remoteEl.style.transform = "scaleX(-1)";
          remoteEl.play?.().catch?.(() => {});
        }
        pip?.classList.add("hidden");
      }
    }
    syncVideoStage();
  }

  async function compressImageFileForCall(file, maxEdge = 720, quality = 0.68) {
    const bitmap = await createImageBitmap(file);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    const targetChars = 160000;
    let edge = Math.min(maxEdge, Math.max(bitmap.width, bitmap.height));
    let q = quality;
    let dataUrl = "";
    for (let attempt = 0; attempt < 8; attempt += 1) {
      const scale = Math.min(1, edge / Math.max(bitmap.width, bitmap.height));
      const w = Math.max(1, Math.round(bitmap.width * scale));
      const h = Math.max(1, Math.round(bitmap.height * scale));
      canvas.width = w;
      canvas.height = h;
      ctx.clearRect(0, 0, w, h);
      ctx.drawImage(bitmap, 0, 0, w, h);
      dataUrl = canvas.toDataURL("image/jpeg", q);
      if (dataUrl.length <= targetChars) break;
      if (q > 0.42) q = Math.max(0.4, q - 0.1);
      else edge = Math.max(320, Math.round(edge * 0.78));
    }
    bitmap.close?.();
    if (dataUrl.length > 300000) throw new Error(t("voiceCallImageFailed", "Bild zu groß"));
    return dataUrl;
  }

  function clearVideoStage() {
    directLocalOn = false;
    directRemoteOn = false;
    syncVideoStage();
  }

  function showPeerBanner(message) {
    const el = document.getElementById("workerVoiceCallPeerBanner");
    if (!el) return;
    el.textContent = String(message || "").trim();
    el.classList.toggle("hidden", !el.textContent);
    if (el._hideTimer) clearTimeout(el._hideTimer);
    if (el.textContent) {
      el._hideTimer = setTimeout(() => {
        el.classList.add("hidden");
        el.textContent = "";
      }, 8000);
    }
  }

  function clearPeerBanner() {
    const el = document.getElementById("workerVoiceCallPeerBanner");
    if (!el) return;
    if (el._hideTimer) clearTimeout(el._hideTimer);
    el.classList.add("hidden");
    el.textContent = "";
  }

  let controller = null;
  let pollTimer = null;
  let session = null;
  let timerInterval = null;
  let startedAt = 0;
  let apiFn = null;
  let dismissedCallId = "";
  let incomingTone = null;
  let conferenceActive = false;

  function setOverlay(visible, statusText, mode, phase) {
    const overlay = ensureOverlay();
    const status = overlay.querySelector("#workerVoiceCallStatus");
    const incoming = overlay.querySelector(".incoming-only");
    const active = overlay.querySelector(".active-only");
    const meters = overlay.querySelector("#workerVoiceCallMeters");
    const wave = overlay.querySelector("#workerVoiceCallLiveWave");
    const toolbar = overlay.querySelector("#workerVoiceCallToolbar");
    if (status && statusText) status.textContent = statusText;
    overlay.classList.toggle("hidden", !visible);
    incoming?.classList.toggle("hidden", mode !== "incoming");
    active?.classList.toggle("hidden", mode !== "active");
    const ringing = phase === "ringing" || mode === "incoming";
    const connecting = phase === "connecting";
    const connected = phase === "connected";
    overlay.classList.toggle("is-ringing", Boolean(visible && ringing && !connected));
    overlay.classList.toggle("is-connecting", Boolean(visible && connecting && !connected));
    meters?.classList.toggle("hidden", !connected);
    wave?.classList.toggle("hidden", !connected);
    toolbar?.classList.toggle("hidden", !connected);
    if (!visible) {
      stopTimer();
      clearPeerBanner();
      clearVideoStage();
      try { incomingTone?.stop?.(); } catch (_) { /* ignore */ }
      incomingTone = null;
      overlay.classList.remove("is-conference", "is-video", "cam-on", "chrome-hidden", "is-ringing", "is-connecting");
    }
  }

  function stopTimer() {
    if (timerInterval) global.clearInterval(timerInterval);
    timerInterval = null;
    startedAt = 0;
    document.getElementById("workerVoiceCallTimer")?.classList.add("hidden");
  }

  function startTimer() {
    stopTimer();
    startedAt = Date.now();
    const el = document.getElementById("workerVoiceCallTimer");
    el?.classList.remove("hidden");
    timerInterval = global.setInterval(() => {
      if (el && startedAt) el.textContent = formatDuration(Date.now() - startedAt);
    }, 1000);
  }

  function updateLevels(local, remote) {
    const mic = document.getElementById("workerVoiceCallMicFill");
    const remoteFill = document.getElementById("workerVoiceCallRemoteFill");
    if (mic) mic.style.width = `${Math.round((local || 0) * 100)}%`;
    if (remoteFill) remoteFill.style.width = `${Math.round((remote || 0) * 100)}%`;
    const wave = document.getElementById("workerVoiceCallLiveWave");
    if (!wave) return;
    const level = Math.max(Number(local || 0), Number(remote || 0));
    wave.querySelectorAll("span").forEach((bar, index) => {
      const phase = (Date.now() / 120 + index * 0.35) % (Math.PI * 2);
      const base = 0.2 + Math.sin(phase) * 0.14;
      bar.style.height = `${Math.max(14, Math.min(100, Math.round((base + level * 0.66) * 100)))}%`;
    });
  }

  function initials(name) {
    return String(name || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part.charAt(0).toUpperCase())
      .join("") || "AG";
  }

  function stopIncomingTone() {
    try { incomingTone?.stop?.(); } catch (_) { /* ignore */ }
    incomingTone = null;
  }
  function startIncomingTone() {
    stopIncomingTone();
    try {
      incomingTone = global.SUPPIXVoiceCall?.createRingtone?.({ mode: "incoming" });
      incomingTone?.start?.();
    } catch (_) { /* ignore */ }
  }

  function showIncoming(call) {
    const name = call.callerName || call.caller_name || call.companyName || call.company_name || t("senderCompany", "Arbeitgeber");
    document.getElementById("workerVoiceCallTitle").textContent = name;
    document.getElementById("workerVoiceCallAvatar").textContent = initials(name);
    setOverlay(true, t("voiceCallRinging", "Eingehender Anruf…"), "incoming", "ringing");
    startIncomingTone();
  }

  controller = {
    async accept() {
      if (!session || !global.SUPPIXVoiceCall) return;
      stopIncomingTone();
      setOverlay(true, t("voiceCallConnected", "Verbunden"), "active", "connected");
      try {
        await session.acceptIncoming(session._incomingCall);
        startTimer();
      } catch (_) {
        setOverlay(false);
        session = null;
      }
    },
    async decline() {
      if (!session) return;
      stopIncomingTone();
      const callId = session.callId;
      try {
        await session.declineIncoming(callId);
      } catch (_) {
        /* ignore */
      }
      if (callId) dismissedCallId = callId;
      session = null;
      setOverlay(false);
    },
    async hangup() {
      stopIncomingTone();
      if (!session) return;
      await session.end("hangup");
      session = null;
      setOverlay(false);
    },
    toggleMute() {
      if (session) {
        const muted = session.toggleMute();
        document.getElementById("workerVoiceCallMuteBtn")?.classList.toggle("is-active", muted);
        return muted;
      }
      if (conferenceActive && global.SUPPIXConference?.isActive?.()) {
        void global.SUPPIXConference.toggleMute?.().then((muted) => {
          if (muted == null) return;
          document.getElementById("workerVoiceCallMuteBtn")?.classList.toggle("is-active", Boolean(muted));
        });
        return;
      }
      const btn = document.getElementById("workerVoiceCallMuteBtn");
      const next = !btn?.classList.contains("is-active");
      btn?.classList.toggle("is-active", next);
      return next;
    },
    toggleSpeaker() {
      let on = true;
      if (session) {
        on = session.toggleSpeaker();
      } else if (conferenceActive && global.SUPPIXConference?.isActive?.()) {
        on = Boolean(global.SUPPIXConference.toggleSpeaker?.());
      } else {
        const btn = document.getElementById("workerVoiceCallSpeakerBtn");
        const currentlyOff = btn?.classList.contains("is-active");
        on = Boolean(currentlyOff); // if off → turn on
      }
      document.getElementById("workerVoiceCallSpeakerBtn")?.classList.toggle("is-active", !on);
      try { incomingTone?.setOutputEnabled?.(on); } catch (_) { /* ignore */ }
      return on;
    },
    async toggleCamera() {
      if (conferenceActive && global.SUPPIXConference?.isActive?.()) {
        const next = !Boolean(global.SUPPIXConference.isCameraOn?.());
        try {
          await global.SUPPIXConference.setCameraEnabled?.(next);
          document.getElementById("workerVoiceCallCamBtn")?.classList.toggle("is-active", next);
        } catch (error) {
          showPeerBanner(cameraErrorMessage(error));
        }
        return;
      }
      if (!session?.setCameraEnabled) return;
      try {
        const next = !Boolean(session.isCameraOn?.() || session.isCameraPreviewing?.());
        const on = await session.setCameraEnabled(next);
        document.getElementById("workerVoiceCallCamBtn")?.classList.toggle("is-active", Boolean(on));
        setPreviewBar(on === "preview" || Boolean(session.isCameraPreviewing?.()));
        bumpChrome();
      } catch (error) {
        document.getElementById("workerVoiceCallCamBtn")?.classList.remove("is-active");
        setPreviewBar(true, cameraErrorMessage(error));
      }
    },
    async confirmPreview() {
      try {
        await session?.confirmCameraPreview?.();
        document.getElementById("workerVoiceCallCamBtn")?.classList.add("is-active");
        setPreviewBar(false);
      } catch (error) {
        setPreviewBar(true, cameraErrorMessage(error));
      }
    },
    async cancelPreview() {
      await session?.cancelCameraPreview?.();
      document.getElementById("workerVoiceCallCamBtn")?.classList.remove("is-active");
      setPreviewBar(false);
    },
    async flipCamera() {
      if (!session?.switchCamera || !session.isCameraOn?.()) return;
      try {
        await session.switchCamera();
        bumpChrome();
      } catch (_) { /* ignore */ }
    },
    async toggleBlur() {
      if (!session?.setBlurEnabled) return;
      try {
        const on = await session.setBlurEnabled(!session.isBlurEnabled?.());
        document.getElementById("workerVoiceCallBlurBtn")?.classList.toggle("is-active", Boolean(on));
      } catch (error) {
        showPeerBanner(cameraErrorMessage(error));
      }
    },
    async toggleScreen() {
      if (!session?.setScreenShareEnabled) return;
      try {
        const on = await session.setScreenShareEnabled(!session.isScreenSharing?.());
        document.getElementById("workerVoiceCallScreenBtn")?.classList.toggle("is-active", Boolean(on));
      } catch (error) {
        showPeerBanner(cameraErrorMessage(error));
      }
    },
    async toggleRecord() {
      if (!session) return;
      try {
        if (session.isRecording?.()) {
          session.stopRecording?.();
          document.getElementById("workerVoiceCallRecordBtn")?.classList.remove("is-active");
        } else {
          await session.startRecording?.();
          document.getElementById("workerVoiceCallRecordBtn")?.classList.add("is-active");
        }
      } catch (error) {
        showPeerBanner(cameraErrorMessage(error));
      }
    },
    shareImage() {
      if (!session?.sendCallImage) {
        showPeerBanner(t("voiceCallControlsWait", "Anruf noch nicht verbunden — kurz warten."));
        return;
      }
      document.getElementById("workerVoiceCallShareInput")?.click();
    },
    async shareImageFile(file) {
      if (!file || !session?.sendCallImage) return;
      try {
        const dataUrl = await compressImageFileForCall(file);
        await session.sendCallImage(dataUrl, {
          fromName: t("workerDefault", "Mitarbeiter"),
        });
        showPeerBanner(t("voiceCallImageSent", "Bild gesendet"));
        bumpChrome();
      } catch (error) {
        showPeerBanner(String(error?.message || t("voiceCallImageFailed", "Bild fehlgeschlagen")));
      }
    },
  };

  function cameraErrorMessage(error) {
    const code = String(error?.code || error?.message || "");
    const map = {
      camera_permission_denied: t("voiceCallCameraDenied", "Kamerazugriff verweigert"),
      camera_not_found: t("voiceCallCameraMissing", "Keine Kamera gefunden"),
      camera_in_use: t("voiceCallCameraBusy", "Kamera ist belegt"),
      camera_constraints: t("voiceCallCameraConstraints", "Kamera-Einstellungen nicht unterstützt"),
      camera_timeout: t("voiceCallCameraTimeout", "Kamera-Timeout"),
      screen_share_denied: t("voiceCallScreenDenied", "Bildschirmfreigabe abgebrochen"),
      screen_share_unsupported: t("voiceCallScreenUnsupported", "Bildschirm teilen nicht unterstützt"),
    };
    return map[code] || String(error?.message || error || t("voiceCallCameraFailed", "Kamera fehlgeschlagen"));
  }

  function setPreviewBar(visible, error = "") {
    const bar = document.getElementById("workerVoiceCallPreviewBar");
    const err = document.getElementById("workerVoiceCallCamError");
    bar?.classList.toggle("hidden", !visible && !error);
    if (err) {
      err.textContent = error || "";
      err.classList.toggle("hidden", !error);
    }
  }

  function attachCallMediaCallbacks(opts = {}) {
    return {
      displayName: opts.displayName || t("workerDefault", "Mitarbeiter"),
      preferVideo: Boolean(opts.preferVideo),
      onLocalVideo: (stream, enabled, meta) => {
        setLocalVideo(stream, enabled || Boolean(meta?.preview));
        if (meta?.preview) setPreviewBar(true);
        else if (!session?.isCameraPreviewing?.()) setPreviewBar(false);
      },
      onCameraPreview: (active) => setPreviewBar(Boolean(active)),
      onRemoteVideo: (stream, hasVideo) => setRemoteVideo(stream, hasVideo),
      onVideoQuality: (tier) => {
        const status = document.getElementById("workerVoiceCallStatus");
        if (!status) return;
        if (String(tier) === "sd") {
          status.textContent = t("voiceCallVideoQualitySd", "Video: 480p (Netz)");
        } else {
          status.textContent = t("voiceCallVideoQualityHd", "Video: 720p");
        }
      },
      onCameraIntent: (payload) => {
        const name = String(payload?.fromName || t("senderCompany", "Arbeitgeber")).trim();
        showPeerBanner(t("voiceCallPeerCameraIntent", `${name} möchte die Kamera öffnen.`).replace("{name}", name));
      },
      onCameraState: (payload) => {
        if (payload?.enabled) {
          const name = String(payload?.fromName || t("senderCompany", "Arbeitgeber")).trim();
          showPeerBanner(t("voiceCallPeerCameraOn", `${name} hat die Kamera eingeschaltet.`).replace("{name}", name));
        } else {
          clearPeerBanner();
        }
      },
      onCallImage: (payload) => {
        const dataUrl = String(payload?.dataUrl || "");
        if (!dataUrl.startsWith("data:image/")) return;
        const name = String(payload?.fromName || t("senderCompany", "Arbeitgeber")).trim();
        showPeerBanner(t("voiceCallImageFrom", `Bild von ${name}`).replace("{name}", name));
        let toast = document.getElementById("workerVoiceCallImageToast");
        if (!toast) {
          toast = document.createElement("div");
          toast.id = "workerVoiceCallImageToast";
          toast.style.cssText = "position:fixed;inset:0;z-index:15000;display:grid;place-items:center;background:rgba(0,0,0,.72);padding:1rem;";
          toast.innerHTML = `<div style="width:min(480px,94vw);background:#111b21;border-radius:16px;padding:.85rem;border:1px solid rgba(255,255,255,.1)"><img id="workerVoiceCallImageToastImg" alt="" style="width:100%;max-height:60vh;object-fit:contain;border-radius:10px"/><div style="display:flex;justify-content:space-between;align-items:center;gap:.75rem;margin-top:.65rem;color:#e9edef"><span id="workerVoiceCallImageToastLabel"></span><button type="button" id="workerVoiceCallImageToastClose" style="border:0;border-radius:999px;padding:.35rem .75rem;background:rgba(255,255,255,.12);color:#fff;cursor:pointer">✕</button></div></div>`;
          document.body.appendChild(toast);
          toast.querySelector("#workerVoiceCallImageToastClose")?.addEventListener("click", () => toast.classList.add("hidden"));
          toast.addEventListener("click", (ev) => {
            if (ev.target === toast) toast.classList.add("hidden");
          });
        }
        const img = toast.querySelector("#workerVoiceCallImageToastImg");
        const label = toast.querySelector("#workerVoiceCallImageToastLabel");
        if (img) img.src = dataUrl;
        if (label) label.textContent = t("voiceCallImageFrom", `Bild von ${name}`).replace("{name}", name);
        toast.classList.remove("hidden");
      },
    };
  }

  async function handleIncoming(call) {
    if (!call || !call.id || !global.SUPPIXVoiceCall?.isSupported?.()) return;
    if (session || String(call.id) === dismissedCallId) return;
    if (call.status && call.status !== "ringing") return;
    session = global.SUPPIXVoiceCall.createSession({
      api: apiFn,
      role: "worker",
      ...attachCallMediaCallbacks(),
      onAudioLevels: ({ local, remote }) => updateLevels(local, remote),
      onState: (state) => {
        if (state === "connected" || state === "accepted") {
          setOverlay(true, t("voiceCallConnected", "Verbunden"), "active", "connected");
          startTimer();
        } else if (state === "ended") {
          dismissedCallId = session?.callId || dismissedCallId;
          session = null;
          setOverlay(false);
          global.dispatchEvent(new CustomEvent("worker-voice-call-ended"));
        }
      },
      onError: () => {
        session = null;
        setOverlay(false);
      },
    });
    session._incomingCall = call;
    session.callId = String(call.id);
    showIncoming(call);
  }

  async function handleConferenceInvite(invite) {
    if (!invite?.id || conferenceActive) return;
    const overlay = ensureOverlay();
    const title = document.getElementById("workerVoiceCallTitle");
    const status = document.getElementById("workerVoiceCallStatus");
    if (title) title.textContent = invite.title || t("conferenceJoined", "Firmenkonferenz");
    if (status) status.textContent = t("voiceCallIncomingRinging", "Einladung zur Konferenz…");
    setOverlay(true, status?.textContent || "", "incoming", "ringing");
    startIncomingTone();
    const accept = document.getElementById("workerVoiceCallAcceptBtn");
    const decline = document.getElementById("workerVoiceCallDeclineBtn");
    const onAccept = async () => {
      accept?.removeEventListener("click", onAccept);
      decline?.removeEventListener("click", onDecline);
      stopIncomingTone();
      try {
        const data = await apiFn(`/api/worker-app/chat/conferences/${encodeURIComponent(invite.id)}/join`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        });
        conferenceActive = true;
        setOverlay(true, t("conferenceJoined", "In Konferenz"), "active", "connected");
        overlay.classList.add("is-conference");
        // Reuse admin video grid if present; else create minimal stage
        if (!document.getElementById("voiceCallVideoGrid")) {
          const stage = overlay.querySelector(".worker-voice-call-stage");
          const grid = document.createElement("div");
          grid.id = "voiceCallVideoGrid";
          grid.className = "voice-call-video-grid";
          stage?.insertBefore(grid, status);
        }
        document.getElementById("voiceCallOverlay")?.classList.add("is-conference");
        global.SUPPIXConference?.setOnCameraIntent?.((name) => {
          const who = String(name || t("senderCompany", "Arbeitgeber")).trim();
          showPeerBanner(
            t("voiceCallPeerCameraIntent", `${who} möchte die Kamera öffnen.`).replace("{name}", who),
          );
        });
        await global.SUPPIXConference?.connect?.({
          livekitUrl: data.livekitUrl,
          token: data.token,
          roomId: data.id,
          participants: data.participants || [],
          onDisconnect: async () => {
            conferenceActive = false;
            overlay.classList.remove("is-conference");
            setOverlay(false);
          },
        });
      } catch (error) {
        conferenceActive = false;
        overlay.classList.remove("is-conference");
        const raw = String(error?.message || error || "");
        const msg = /ServerUnreachable|websocket|Internal error/i.test(raw)
          ? t("conferenceNetworkUnreachable", "Konferenz-Server nicht erreichbar (VPN/Netz).")
          : raw;
        setOverlay(false);
        global.showWorkerNotice?.(msg);
      }
    };
    const onDecline = async () => {
      accept?.removeEventListener("click", onAccept);
      decline?.removeEventListener("click", onDecline);
      stopIncomingTone();
      try {
        await apiFn(`/api/worker-app/chat/conferences/${encodeURIComponent(invite.id)}/leave`, { method: "POST" });
      } catch (_) { /* ignore */ }
      setOverlay(false);
    };
    accept?.addEventListener("click", onAccept, { once: true });
    decline?.addEventListener("click", onDecline, { once: true });
    document.getElementById("workerVoiceCallHangupBtn")?.addEventListener("click", async () => {
      if (!conferenceActive) return;
      try {
        await apiFn(`/api/worker-app/chat/conferences/${encodeURIComponent(invite.id)}/leave`, { method: "POST" });
      } catch (_) { /* ignore */ }
      await global.SUPPIXConference?.disconnect?.();
      conferenceActive = false;
      setOverlay(false);
    }, { once: true });
  }

  function startPolling() {
    stopPolling();
    if (!apiFn) return;
    const tick = async () => {
      if (session || conferenceActive) {
        pollTimer = global.setTimeout(tick, POLL_MS);
        return;
      }
      try {
        if (global.SUPPIXVoiceCall?.isSupported?.()) {
          const data = await apiFn("/api/worker-app/chat/calls/incoming");
          if (data?.call) await handleIncoming(data.call);
        }
        const conf = await apiFn("/api/worker-app/chat/conferences/incoming");
        if (conf?.conference) await handleConferenceInvite(conf.conference);
      } catch (_) {
        /* ignore */
      }
      pollTimer = global.setTimeout(tick, POLL_MS);
    };
    pollTimer = global.setTimeout(tick, 200);
  }

  async function pollIncomingOnce(api) {
    if (typeof api === "function") apiFn = api;
    if (!apiFn || session || conferenceActive) return;
    try {
      if (global.SUPPIXVoiceCall?.isSupported?.()) {
        const data = await apiFn("/api/worker-app/chat/calls/incoming");
        if (data?.call) await handleIncoming(data.call);
      }
      const conf = await apiFn("/api/worker-app/chat/conferences/incoming");
      if (conf?.conference) await handleConferenceInvite(conf.conference);
    } catch (_) {
      /* ignore */
    }
  }

  function stopPolling() {
    if (pollTimer) global.clearTimeout(pollTimer);
    pollTimer = null;
  }

  function wakeForCallId(callId) {
    const id = String(callId || "").trim();
    if (!id || !apiFn) return;
    void apiFn(`/api/worker-app/chat/calls/${encodeURIComponent(id)}`).then((data) => {
      if (data?.call) void handleIncoming(data.call);
    }).catch(() => {});
  }

  global.SUPPIXWorkerVoiceCall = {
    init(options = {}) {
      apiFn = options.api;
      dismissedCallId = "";
      ensureOverlay();
      if (options.enabled === false) {
        stopPolling();
        return;
      }
      startPolling();
    },
    stop: stopPolling,
    wakeForCallId,
    pollIncomingOnce,
    showCameraIntentBanner(name) {
      const who = String(name || t("senderCompany", "Arbeitgeber")).trim();
      ensureOverlay();
      showPeerBanner(
        t("voiceCallPeerCameraIntent", `${who} möchte die Kamera öffnen.`).replace("{name}", who),
      );
    },
    async startOutgoingCall(api, opts = {}) {
      if (typeof api !== "function" || !global.SUPPIXVoiceCall?.isSupported?.()) {
        return Promise.reject(new Error("voice_call_unsupported"));
      }
      if (session) {
        return Promise.reject(new Error("worker_busy"));
      }
      apiFn = api;
      const preferVideo = Boolean(opts.preferVideo);
      session = global.SUPPIXVoiceCall.createSession({
        api,
        role: "worker",
        ...attachCallMediaCallbacks({ preferVideo }),
        onAudioLevels: ({ local, remote }) => updateLevels(local, remote),
        onState: (state) => {
          if (state === "ringing" || state === "dialing") {
            setOverlay(true, t("voiceCallRinging", "Klingelt…"), "active", "ringing");
          } else if (state === "connected" || state === "accepted") {
            setOverlay(true, t("voiceCallConnected", "Verbunden"), "active", "connected");
            startTimer();
          } else if (state === "ended") {
            session = null;
            setOverlay(false);
            global.dispatchEvent(new CustomEvent("worker-voice-call-ended"));
          }
        },
        onError: () => {
          session = null;
          setOverlay(false);
        },
      });
      const overlayEl = ensureOverlay();
      document.getElementById("workerVoiceCallTitle").textContent = t("senderCompany", "Arbeitgeber");
      document.getElementById("workerVoiceCallAvatar").textContent = "AG";
      setOverlay(true, t("voiceCallDialing", "Wählt…"), "active", "ringing");
      overlayEl.querySelector(".incoming-only")?.classList.add("hidden");
      overlayEl.querySelector(".active-only")?.classList.remove("hidden");
      try {
        await session.startWorkerOutgoing();
      } catch (error) {
        session = null;
        setOverlay(false);
        throw error;
      }
    },
    requestCallback(api, callId) {
      if (typeof api !== "function") return Promise.reject(new Error("api_required"));
      return api("/api/worker-app/chat/calls/callback-request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(callId ? { call_id: callId } : {}),
      });
    },
    parseCallLogBody(body) {
      const text = String(body || "").trim();
      if (!text.startsWith("@voice-call|")) return null;
      const meta = {};
      text.slice("@voice-call|".length).split("|").forEach((part) => {
        const idx = part.indexOf("=");
        if (idx < 0) return;
        meta[part.slice(0, idx)] = part.slice(idx + 1);
      });
      return meta.status ? meta : null;
    },
    shouldShowCallLogToWorker(meta) {
      const audience = String(meta?.audience || "both").toLowerCase();
      if (audience === "admin") return false;
      return true;
    },
    renderCallLogHtml(meta, options = {}) {
      const status = String(meta?.status || "ended");
      const duration = Number(meta?.duration || 0);
      const map = {
        ended: t("voiceCallLogEnded", "Anruf beendet"),
        declined: t("voiceCallLogDeclined", "Abgelehnt"),
        missed: t("voiceCallLogMissed", "Verpasst"),
        cancelled: t("voiceCallLogCancelled", "Abgebrochen"),
        callback_requested: t("voiceCallLogCallbackRequested", "Rückruf angefordert"),
      };
      let summary = map[status] || map.ended;
      if (duration > 0) summary += ` · ${formatDuration(duration * 1000)}`;
      const callbackBtn = options.showCallback && ["missed", "declined", "ended", "cancelled"].includes(status)
        ? `<button type="button" class="worker-chat-call-log-btn" data-voice-callback="1" data-call-id="${String(meta.callId || "")}">${t("voiceCallRequestCallback", "Rückruf anfordern")}</button>`
        : "";
      return `<div class="worker-chat-call-log"><span aria-hidden="true"><svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1.1-.2 1.2.4 2.5.6 3.8.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.6 21 3 13.4 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.6.6 3.8.1.4 0 .8-.2 1.1L6.6 10.8z"/></svg></span><span>${summary}</span>${callbackBtn}</div>`;
    },
  };
})(window);
