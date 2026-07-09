/**
 * PWA fallback QR scanner (camera viewfinder) for worker activation.
 */
(function initWorkerQrScanner(global) {
  if (global.WorkerQrScanner) return;

  function parseActivationPayload(raw) {
    const trimmed = String(raw || "").trim();
    if (!trimmed) return null;
    try {
      const url = new URL(trimmed, global.location.origin);
      const access = String(url.searchParams.get("access") || url.searchParams.get("accessToken") || "").trim();
      const badge = String(url.searchParams.get("badge") || "").trim().toUpperCase();
      if (access || badge) {
        return { access, badge, launch: url.searchParams.get("launch") === "1" || url.searchParams.get("fast") === "1" };
      }
      if (url.protocol === "baupass:" && url.host === "join") {
        const deepAccess = String(url.searchParams.get("access") || "").trim();
        if (deepAccess) return { access: deepAccess, badge: "", launch: true };
      }
    } catch {
      /* not a URL */
    }
    if (/^[A-Za-z0-9._-]{12,}$/.test(trimmed) && !trimmed.includes(" ")) {
      return { access: trimmed, badge: "", launch: true };
    }
    const badgeOnly = trimmed.toUpperCase();
    if (badgeOnly.includes("-")) {
      return { access: "", badge: badgeOnly, launch: true };
    }
    return null;
  }

  function supported() {
    return Boolean(global.navigator?.mediaDevices?.getUserMedia) && "BarcodeDetector" in global;
  }

  async function start({ videoEl, onScan, onError }) {
    if (!supported()) {
      onError?.("qr_scanner_unsupported");
      return () => {};
    }
    let active = true;
    let stream = null;
    let timer = null;
    const detector = new global.BarcodeDetector({ formats: ["qr_code"] });

    try {
      stream = await global.navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      videoEl.srcObject = stream;
      await videoEl.play();
    } catch (err) {
      onError?.(err?.message || "camera_denied");
      return () => {};
    }

    const tick = async () => {
      if (!active || videoEl.readyState < 2) return;
      try {
        const codes = await detector.detect(videoEl);
        const raw = String(codes?.[0]?.rawValue || "").trim();
        if (!raw) return;
        const payload = parseActivationPayload(raw);
        if (!payload) return;
        active = false;
        await onScan(payload, raw);
      } catch {
        /* ignore frame errors */
      }
    };

    timer = global.setInterval(tick, 450);

    return () => {
      active = false;
      if (timer) global.clearInterval(timer);
      if (stream) {
        stream.getTracks().forEach((track) => track.stop());
      }
      videoEl.srcObject = null;
    };
  }

  global.WorkerQrScanner = {
    supported,
    parseActivationPayload,
    start,
  };
})(window);
