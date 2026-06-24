/**

 * SUPPIX — signature pad providers (Signotec, Wacom, StepOver, Topaz, canvas)

 * Loaded after signature-pad-bridge.js

 */

(function initBaupassSignaturePadProviders(global) {

  const bridge = global.BaupassSignaturePad;

  if (!bridge?.registerProvider) return;



  function sleep(ms) {

    return new Promise((resolve) => global.setTimeout(resolve, ms));

  }



  function newMessageId() {

    if (global.crypto?.randomUUID) return global.crypto.randomUUID();

    return `bp-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  }



  async function vendorAssetExists(src) {

    try {

      const res = await fetch(src, { method: "HEAD", credentials: "omit" });

      return res.ok;

    } catch {

      return false;

    }

  }



  function loadScriptOnce(src, key, timeoutMs = 15000) {

    const attr = `data-baupass-vendor-${key}`;

    if (key === "topaz" && typeof global.IsSigWebInstalled === "function") {

      return Promise.resolve(true);

    }

    if (key === "wacom-q" && global.Q) return Promise.resolve(true);

    if (key === "wacom-sdk" && global.WacomGSS?.STU) return Promise.resolve(true);

    const existing = global.document?.querySelector(`script[${attr}]`);

    if (existing) {

      return new Promise((resolve) => {

        let settled = false;

        const finish = (ok) => {

          if (settled) return;

          settled = true;

          global.clearTimeout(timer);

          resolve(ok);

        };

        const timer = global.setTimeout(() => finish(false), timeoutMs);

        if (existing.dataset.loaded === "1") {

          finish(true);

          return;

        }

        existing.addEventListener("load", () => finish(true), { once: true });

        existing.addEventListener("error", () => finish(false), { once: true });

      });

    }

    return new Promise((resolve) => {

      let settled = false;

      const finish = (ok) => {

        if (settled) return;

        settled = true;

        global.clearTimeout(timer);

        resolve(ok);

      };

      const timer = global.setTimeout(() => finish(false), timeoutMs);

      const script = global.document.createElement("script");

      script.src = src;

      script.defer = true;

      script.setAttribute(attr, "1");

      script.onload = () => {

        script.dataset.loaded = "1";

        if (String(key || "").startsWith("signotec")) {

          signotecBindGlobals();

          finish(signotecLibsReady());

          return;

        }

        finish(true);

      };

      script.onerror = () => finish(false);

      global.document.head.appendChild(script);

    });

  }



  /* ── Signotec ─────────────────────────────────────────────────────────── */



  // CERT_SEL=Localhost install — certificate is valid for localhost only, not 127.0.0.1.
  const SIGNOTEC_WS_URLS = [
    "wss://localhost:49494",
  ];

  const SIGNOTEC_INTERFACE_VERSION = "3.5.0.0";

  const SIGNOTEC_PAD_INDEX = 0;

  const signotecState = { wsConnected: false, padOpen: false, activeCapture: null };

  const SIGNOTEC_LIB_CACHE_KEY = "baupass-signotec-stpad-lib-v1";



  function signotecBindGlobals() {

    const bundle = global.STPadServerLib;

    if (bundle?.STPadServerLibCommons) {

      global.STPadServerLibCommons = bundle.STPadServerLibCommons;

      global.STPadServerLibDefault = bundle.STPadServerLibDefault;

      global.STPadServerLibApi = bundle.STPadServerLibApi;

      return true;

    }

    return Boolean(global.STPadServerLibCommons && global.STPadServerLibDefault);

  }



  function signotecLibsReady() {

    signotecBindGlobals();

    return Boolean(

      global.STPadServerLibCommons

      && global.STPadServerLibDefault

      && typeof global.STPadServerLibCommons.createConnection === "function",

    );

  }



  function signotecInjectScriptSource(code, key) {

    const attr = `data-baupass-vendor-signotec-${key}`;

    if (global.document?.querySelector(`script[${attr}]`)) {

      return signotecLibsReady();

    }

    const script = global.document.createElement("script");

    script.textContent = code;

    script.setAttribute(attr, "1");

    script.dataset.loaded = "1";

    global.document.head.appendChild(script);

    return signotecLibsReady();

  }



  function signotecCacheLib(code) {

    try {

      if (code && code.includes("STPadServerLibCommons")) {

        global.localStorage?.setItem(SIGNOTEC_LIB_CACHE_KEY, code);

      }

    } catch {

      // ignore quota / private mode

    }

  }



  function signotecLoadFromCache() {

    try {

      const code = global.localStorage?.getItem(SIGNOTEC_LIB_CACHE_KEY);

      if (!code || !code.includes("STPadServerLibCommons")) return false;

      return signotecInjectScriptSource(code, "cache");

    } catch {

      return false;

    }

  }



  async function signotecFetchAndInject(url, key) {

    try {

      const res = await fetch(url, { credentials: "omit", mode: "cors" });

      if (!res.ok) return false;

      const code = await res.text();

      if (!code || !code.includes("STPadServerLibCommons")) return false;

      signotecInjectScriptSource(code, key);

      signotecCacheLib(code);

      return signotecLibsReady();

    } catch {

      return false;

    }

  }



  let signotecLoadLibPromise = null;



  async function signotecLoadLib() {

    if (signotecLibsReady()) return true;

    if (signotecLoadFromCache()) return true;

    if (signotecLoadLibPromise) return signotecLoadLibPromise;

    signotecLoadLibPromise = (async () => {

      const sources = [

        "./vendor/signotec/STPadServerLib.js",

        "/vendor/signotec/STPadServerLib.js",

        "/api/signotec/lib.js",

      ];

      for (let i = 0; i < sources.length; i += 1) {

        const src = sources[i];

        const ok = await loadScriptOnce(src, `signotec-${i}`);

        if (ok && signotecLibsReady()) {

          try {

            const res = await fetch(src, { credentials: "omit" });

            if (res.ok) {

              const code = await res.text();

              signotecCacheLib(code);

            }

          } catch {

            // ignore cache write failures

          }

          return true;

        }

      }

      return signotecLibsReady();

    })();

    try {

      return await signotecLoadLibPromise;

    } finally {

      signotecLoadLibPromise = null;

    }

  }



  async function signotecSetInterfaceVersionSafe() {

    if (typeof global.STPadServerLibCommons.setInterfaceVersion !== "function") return;

    const params = new global.STPadServerLibCommons.Params.setInterfaceVersion(SIGNOTEC_INTERFACE_VERSION);

    try {

      await global.STPadServerLibCommons.setInterfaceVersion(params);

    } catch {

      // ignore

    }

  }



  function signotecCreateConnection(url, timeoutMs = 8000) {

    return new Promise((resolve, reject) => {

      let settled = false;

      const finishOk = () => {

        if (settled) return;

        settled = true;

        signotecState.wsConnected = true;

        resolve();

      };

      const finishErr = (err) => {

        if (settled) return;

        settled = true;

        signotecState.wsConnected = false;

        reject(err instanceof Error ? err : new Error(String(err || "signotec_ws_error")));

      };

      const timer = global.setTimeout(() => finishErr(new Error("signotec_ws_timeout")), timeoutMs);

      try {

        global.STPadServerLibCommons.createConnection(

          url,

          () => {

            global.clearTimeout(timer);

            finishOk();

          },

          () => {

            signotecState.wsConnected = false;

            signotecState.padOpen = false;

          },

          () => {

            global.clearTimeout(timer);

            finishErr(new Error("signotec_ws_error"));

          },

        );

      } catch (err) {

        global.clearTimeout(timer);

        finishErr(err);

      }

    });

  }



  async function signotecEnsureConnection(options = {}) {

    const timeoutMs = Number(options.timeoutMs) > 0 ? Number(options.timeoutMs) : 8000;

    if (!(await signotecLoadLib())) throw new Error("signotec_lib_missing");

    if (signotecState.wsConnected) return;

    let lastErr = null;

    for (const url of SIGNOTEC_WS_URLS) {

      try {

        await signotecCreateConnection(url, timeoutMs);

        await signotecSetInterfaceVersionSafe();

        return;

      } catch (err) {

        lastErr = err;

        try {

          global.STPadServerLibCommons.destroyConnection?.();

        } catch {

          // ignore

        }

        signotecState.wsConnected = false;

        await sleep(120);

      }

    }

    throw lastErr || new Error("signotec_ws_unreachable");

  }



  async function signotecClosePadQuiet() {

    if (!signotecState.padOpen || typeof global.STPadServerLibDefault.closePad !== "function") {

      signotecState.padOpen = false;

      return;

    }

    try {

      const params = new global.STPadServerLibDefault.Params.closePad(SIGNOTEC_PAD_INDEX);

      await global.STPadServerLibDefault.closePad(params);

    } catch {

      // ignore

    }

    signotecState.padOpen = false;

  }



  async function signotecResetSession(options = {}) {

    const reconnect = options.reconnect !== false;

    const pending = signotecState.activeCapture;

    signotecState.activeCapture = null;

    if (pending) {

      try {

        pending.reject(new Error("signotec_cancelled"));

      } catch {

        // ignore

      }

    }

    if (!signotecLibsReady()) {

      signotecState.wsConnected = false;

      signotecState.padOpen = false;

      return;

    }

    try {

      await global.STPadServerLibDefault.cancelSignature?.();

    } catch {

      // ignore

    }

    await signotecClosePadQuiet();

    if (reconnect && signotecState.wsConnected) {

      try {

        global.STPadServerLibCommons.destroyConnection?.();

      } catch {

        // ignore

      }

      signotecState.wsConnected = false;

      await sleep(180);

    }

  }



  function signotecInstallCaptureHandlers() {

    global.STPadServerLibDefault.handleConfirmSignature = async function onConfirmSignature() {

      const capture = signotecState.activeCapture;

      if (!capture) return;

      try {

        const confirmed = await global.STPadServerLibDefault.confirmSignature();

        const points = Number(confirmed?.countedPoints || 0);

        if (points < 1) throw new Error("signotec_empty_signature");

        const imgParams = new global.STPadServerLibDefault.Params.getSignatureImage();

        if (global.STPadServerLibDefault.FileType?.PNG != null) {

          imgParams.setFileType(global.STPadServerLibDefault.FileType.PNG);

        }

        if (typeof imgParams.setPenWidth === "function") imgParams.setPenWidth(4);

        const img = await global.STPadServerLibDefault.getSignatureImage(imgParams);

        const raw = String(img?.file || "").trim();

        if (!raw) throw new Error("signotec_no_image");

        const dataUrl = raw.startsWith("data:") ? raw : `data:image/png;base64,${raw}`;

        await signotecClosePadQuiet();

        capture.resolve({ dataUrl, points, provider: "signotec" });

      } catch (err) {

        await signotecClosePadQuiet();

        capture.reject(err instanceof Error ? err : new Error(String(err || "signotec_capture_failed")));

      } finally {

        signotecState.activeCapture = null;

      }

    };



    global.STPadServerLibDefault.handleRetrySignature = function onRetrySignature() {

      try {

        global.STPadServerLibDefault.retrySignature?.();

      } catch {

        // ignore

      }

    };



    global.STPadServerLibDefault.handleCancelSignature = async function onCancelSignature() {

      try {

        await global.STPadServerLibDefault.cancelSignature?.();

      } catch {

        // ignore

      }

      await signotecClosePadQuiet();

      const capture = signotecState.activeCapture;

      if (capture) {

        capture.reject(new Error("signature_cancelled"));

        signotecState.activeCapture = null;

      }

    };

  }



  async function signotecCapture(options = {}) {

    if (signotecState.activeCapture) throw new Error("signotec_busy");

    await signotecResetSession();

    await signotecEnsureConnection();

    signotecInstallCaptureHandlers();

    const fieldName = String(options.fieldName || "SUPPIX").trim() || "SUPPIX";

    const customText = String(options.customText || options.hint || "").trim();

    return new Promise(async (resolve, reject) => {

      signotecState.activeCapture = { resolve, reject };

      try {

        const openParams = new global.STPadServerLibDefault.Params.openPad(SIGNOTEC_PAD_INDEX);

        await global.STPadServerLibDefault.openPad(openParams);

        signotecState.padOpen = true;

        const sigParams = new global.STPadServerLibDefault.Params.startSignature();

        if (typeof sigParams.setFieldName === "function") sigParams.setFieldName(fieldName);

        if (customText && typeof sigParams.setCustomText === "function") {

          sigParams.setCustomText(customText);

        }

        await global.STPadServerLibDefault.startSignature(sigParams);

      } catch (err) {

        signotecState.activeCapture = null;

        await signotecClosePadQuiet();

        reject(err instanceof Error ? err : new Error(String(err || "signotec_start_failed")));

      }

    });

  }



  /* ── Wacom SigCaptX ───────────────────────────────────────────────────── */



  const STEPOVER_WS = "wss://signsocket.stepover.com:57357/signsocket/";



  async function loadWacomScripts() {

    if (!(await vendorAssetExists("./vendor/wacom/q.js"))) return false;

    const qOk = await loadScriptOnce("./vendor/wacom/q.js", "wacom-q");

    if (!qOk || !global.Q) return false;

    if (!(await vendorAssetExists("./vendor/wacom/wgssStuSdk.js"))) return false;

    const sdkOk = await loadScriptOnce("./vendor/wacom/wgssStuSdk.js", "wacom-sdk");

    return sdkOk && Boolean(global.WacomGSS?.STU);

  }



  async function wacomWaitServiceReady(maxRetries, delayMs) {

    for (let i = 0; i < maxRetries; i += 1) {

      if (global.WacomGSS?.STU?.isServiceReady?.()) return true;

      await sleep(delayMs);

    }

    return global.WacomGSS?.STU?.isServiceReady?.() || false;

  }



  function wacomRectangle(x, y, width, height) {

    return {

      x, y, width, height,

      Contains(pt) {

        return pt.x >= this.x && pt.x <= (this.x + this.width)

          && pt.y >= this.y && pt.y <= (this.y + this.height);

      },

    };

  }



  function wacomClearCanvas(canvas, ctx) {

    ctx.save();

    ctx.setTransform(1, 0, 0, 1, 0, 0);

    ctx.fillStyle = "white";

    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.restore();

  }



  async function wacomCapture(options = {}) {

    await loadWacomScripts();

    if (!global.WacomGSS?.STU || !global.Q) throw new Error("wacom_lib_missing");

    await wacomWaitServiceReady(20, 500);

    if (!global.WacomGSS.STU.isServiceReady()) throw new Error("wacom_service_not_ready");



    const dcaReady = await global.WacomGSS.STU.isDCAReady();

    if (!dcaReady) throw new Error("wacom_dca_not_ready");



    const hint = String(options.customText || options.hint || options.fieldName || "SUPPIX").trim();



    return new Promise((resolve, reject) => {

      const p = new global.WacomGSS.STU.Protocol();

      let tablet = null;

      let intf = null;

      let capability = null;

      let inkThreshold = null;

      let encodingMode = null;

      let imgData = null;

      let usbDevices = null;

      let penData = [];

      let isDown = false;

      let lastPoint = { x: 0, y: 0 };

      let clickBtn = -1;

      let buttons = [];

      let canvas = null;

      let ctx = null;

      let modalBg = null;

      let formDiv = null;

      let reportHandler = null;



      const cleanupDom = () => {

        try {

          if (modalBg?.parentNode) modalBg.parentNode.removeChild(modalBg);

        } catch {

          // ignore

        }

        try {

          if (formDiv?.parentNode) formDiv.parentNode.removeChild(formDiv);

        } catch {

          // ignore

        }

        modalBg = null;

        formDiv = null;

        canvas = null;

        ctx = null;

      };



      const disconnectTablet = () => {

        if (!tablet) return global.Q.resolve();

        return tablet.setInkingMode(p.InkingMode.InkingMode_Off)

          .then(() => tablet.endCapture())

          .then(() => (imgData ? imgData.remove() : null))

          .then(() => {

            imgData = null;

            return tablet.setClearScreen();

          })

          .then(() => tablet.disconnect())

          .then(() => {

            tablet = null;

          })

          .catch(() => {

            tablet = null;

          });

      };



      const finishCancel = () => {

        global.WacomGSS.STU.onDCAtimeout = null;

        disconnectTablet().finally(() => {

          cleanupDom();

          reject(new Error("signature_cancelled"));

        });

      };



      const finishOk = () => {

        const exportCanvas = global.document.createElement("canvas");

        exportCanvas.width = capability?.screenWidth || 520;

        exportCanvas.height = Math.max(80, Math.round((capability?.screenHeight || 160) * 0.55));

        const exportCtx = exportCanvas.getContext("2d");

        wacomClearCanvas(exportCanvas, exportCtx);

        exportCtx.lineWidth = 2;

        exportCtx.strokeStyle = "#111417";

        let down = false;

        let last = { x: 0, y: 0 };

        const replayPoint = (point) => {

          const nx = Math.round(exportCanvas.width * point.x / capability.tabletMaxX);

          const ny = Math.round(exportCanvas.height * point.y / capability.tabletMaxY);

          const down2 = down

            ? !(point.pressure <= inkThreshold.offPressureMark)

            : (point.pressure > inkThreshold.onPressureMark);

          if (!down && down2) last = { x: nx, y: ny };

          if ((down2 && ((last.x - nx) ** 2 + (last.y - ny) ** 2) > 10) || (down && !down2)) {

            exportCtx.beginPath();

            exportCtx.moveTo(last.x, last.y);

            exportCtx.lineTo(nx, ny);

            exportCtx.stroke();

            exportCtx.closePath();

            last = { x: nx, y: ny };

          }

          down = down2;

        };

        penData.forEach(replayPoint);

        if (penData.length < 1) {
          global.WacomGSS.STU.onDCAtimeout = null;
          disconnectTablet().finally(() => {
            cleanupDom();
            reject(new Error("wacom_empty_signature"));
          });
          return;
        }

        const dataUrl = exportCanvas.toDataURL("image/png");

        global.WacomGSS.STU.onDCAtimeout = null;

        disconnectTablet().finally(() => {

          cleanupDom();

          resolve({ dataUrl, provider: "wacom", points: penData.length });

        });

      };



      const drawButtons = () => {

        ctx.save();

        ctx.setTransform(1, 0, 0, 1, 0, 0);

        ctx.beginPath();

        ctx.lineWidth = 1;

        ctx.strokeStyle = "black";

        ctx.font = "24px Arial";

        buttons.forEach((btn) => {

          ctx.fillStyle = "lightgrey";

          ctx.fillRect(btn.Bounds.x, btn.Bounds.y, btn.Bounds.width, btn.Bounds.height);

          ctx.fillStyle = "black";

          ctx.rect(btn.Bounds.x, btn.Bounds.y, btn.Bounds.width, btn.Bounds.height);

          const xPos = btn.Bounds.x + ((btn.Bounds.width / 2) - (ctx.measureText(btn.Text).width / 2));

          ctx.fillText(btn.Text, xPos, btn.Bounds.y + 36);

        });

        ctx.stroke();

        ctx.closePath();

        ctx.restore();

      };



      const addButtons = () => {

        buttons = [{}, {}, {}];

        const w2 = capability.screenWidth / 3;

        const w3 = capability.screenWidth / 3;

        const w1 = capability.screenWidth - w2 - w3;

        const y = Math.round(capability.screenHeight * 6 / 7);

        const h = capability.screenHeight - y;

        buttons[0].Bounds = wacomRectangle(0, y, w1, h);

        buttons[1].Bounds = wacomRectangle(w1, y, w2, h);

        buttons[2].Bounds = wacomRectangle(w1 + w2, y, w3, h);

        buttons[0].Text = "OK";

        buttons[1].Text = "Clear";

        buttons[2].Text = "Cancel";

        buttons[0].Click = finishOk;

        buttons[1].Click = () => {

          penData = [];

          wacomClearCanvas(canvas, ctx);

          drawButtons();

          if (hint) {

            ctx.save();

            ctx.font = "18px Arial";

            ctx.fillStyle = "#333";

            ctx.fillText(hint.slice(0, 42), 12, 28);

            ctx.restore();

          }

          tablet.writeImage(encodingMode, imgData);

        };

        buttons[2].Click = finishCancel;

        wacomClearCanvas(canvas, ctx);

        if (hint) {

          ctx.save();

          ctx.font = "18px Arial";

          ctx.fillStyle = "#333";

          ctx.fillText(hint.slice(0, 42), 12, 28);

          ctx.restore();

        }

        drawButtons();

      };



      const processButtons = (point) => {

        const nextPoint = {

          x: Math.round(canvas.width * point.x / capability.tabletMaxX),

          y: Math.round(canvas.height * point.y / capability.tabletMaxY),

        };

        const isDown2 = isDown

          ? !(point.pressure <= inkThreshold.offPressureMark)

          : (point.pressure > inkThreshold.onPressureMark);

        let btn = -1;

        for (let i = 0; i < buttons.length; i += 1) {

          if (buttons[i].Bounds.Contains(nextPoint)) {

            btn = i;

            break;

          }

        }

        if (isDown && !isDown2) {

          if (btn !== -1 && clickBtn === btn) buttons[btn].Click();

          clickBtn = -1;

        } else if (btn !== -1 && !isDown && isDown2) {

          clickBtn = btn;

        }

        return btn === -1;

      };



      const processPoint = (point) => {

        const nextPoint = {

          x: Math.round(canvas.width * point.x / capability.tabletMaxX),

          y: Math.round(canvas.height * point.y / capability.tabletMaxY),

        };

        const isDown2 = isDown

          ? !(point.pressure <= inkThreshold.offPressureMark)

          : (point.pressure > inkThreshold.onPressureMark);

        if (!isDown && isDown2) lastPoint = nextPoint;

        if ((isDown2 && ((lastPoint.x - nextPoint.x) ** 2 + (lastPoint.y - nextPoint.y) ** 2) > 10) || (isDown && !isDown2)) {

          ctx.beginPath();

          ctx.moveTo(lastPoint.x, lastPoint.y);

          ctx.lineTo(nextPoint.x, nextPoint.y);

          ctx.stroke();

          ctx.closePath();

          lastPoint = nextPoint;

        }

        isDown = isDown2;

      };



      global.WacomGSS.STU.onDCAtimeout = finishCancel;



      global.WacomGSS.STU.getUsbDevices()

        .then((devices) => {

          if (!devices || devices.length === 0) throw new Error("wacom_no_device");

          usbDevices = devices;

          return global.WacomGSS.STU.isSupportedUsbDevice(devices[0].idVendor, devices[0].idProduct);

        })

        .then(() => {

          intf = new global.WacomGSS.STU.UsbInterface();

          return intf.Constructor();

        })

        .then(() => intf.connect(usbDevices[0], true))

        .then(() => {

          tablet = new global.WacomGSS.STU.Tablet();

          return tablet.Constructor(intf, null, null);

        })

        .then(() => {

          intf = null;

          return tablet.getInkThreshold();

        })

        .then((message) => {

          inkThreshold = message;

          return tablet.getCapability();

        })

        .then((message) => {

          capability = message;

          modalBg = global.document.createElement("div");

          modalBg.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:99998";

          formDiv = global.document.createElement("div");

          formDiv.style.cssText = `position:fixed;z-index:99999;top:50%;left:50%;transform:translate(-50%,-50%);background:#fff;border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,.25)`;

          formDiv.style.width = `${capability.screenWidth}px`;

          formDiv.style.height = `${capability.screenHeight}px`;

          canvas = global.document.createElement("canvas");

          canvas.width = capability.screenWidth;

          canvas.height = capability.screenHeight;

          formDiv.appendChild(canvas);

          global.document.body.appendChild(modalBg);

          global.document.body.appendChild(formDiv);

          ctx = canvas.getContext("2d");

          return tablet.getProductId();

        })

        .then((productId) => global.WacomGSS.STU.ProtocolHelper.simulateEncodingFlag(productId, capability.encodingFlag))

        .then((encodingFlag) => {

          if ((encodingFlag & p.EncodingFlag.EncodingFlag_24bit) !== 0) {

            return tablet.supportsWrite().then((bulk) => {

              encodingMode = bulk ? p.EncodingMode.EncodingMode_24bit_Bulk : p.EncodingMode.EncodingMode_24bit;

            });

          }

          if ((encodingFlag & p.EncodingFlag.EncodingFlag_16bit) !== 0) {

            return tablet.supportsWrite().then((bulk) => {

              encodingMode = bulk ? p.EncodingMode.EncodingMode_16bit_Bulk : p.EncodingMode.EncodingMode_16bit;

            });

          }

          encodingMode = p.EncodingMode.EncodingMode_1bit;

          return encodingMode;

        })

        .then(() => tablet.setClearScreen())

        .then(() => {

          addButtons();

          const canvasImage = canvas.toDataURL("image/jpeg");

          return global.WacomGSS.STU.ProtocolHelper.resizeAndFlatten(

            canvasImage, 0, 0, 0, 0,

            capability.screenWidth, capability.screenHeight,

            encodingMode, 1, false, 0, true,

          );

        })

        .then((message) => {

          imgData = message;

          return tablet.writeImage(encodingMode, message);

        })

        .then(() => tablet.setInkingMode(p.InkingMode.InkingMode_On))

        .then(() => {

          reportHandler = new global.WacomGSS.STU.ProtocolHelper.ReportHandler();

          penData = [];

          const penDataFn = (report) => {

            if (processButtons(report)) processPoint(report);

            penData.push(report);

          };

          const penDataEncrypted = (report) => {

            if (processButtons(report.penData[0])) processPoint(report.penData[0]);

            if (processButtons(report.penData[1])) processPoint(report.penData[1]);

            penData.push(report.penData[0], report.penData[1]);

          };

          reportHandler.onReportPenData = penDataFn;

          reportHandler.onReportPenDataOption = penDataFn;

          reportHandler.onReportPenDataTimeCountSequence = penDataFn;

          reportHandler.onReportPenDataEncrypted = penDataEncrypted;

          reportHandler.onReportPenDataEncryptedOption = penDataEncrypted;

          reportHandler.onReportPenDataTimeCountSequenceEncrypted = penDataFn;

          return reportHandler.startReporting(tablet, true);

        })

        .catch((err) => {

          global.WacomGSS.STU.onDCAtimeout = null;

          disconnectTablet().finally(() => {

            cleanupDom();

            reject(err instanceof Error ? err : new Error(String(err || "wacom_capture_failed")));

          });

        });

    });

  }



  /* ── StepOver Pad Connector ───────────────────────────────────────────── */



  class StepOverClient {

    constructor() {

      this.ws = null;

      this.pending = new Map();

      this.lazyListeners = [];
    }

    _removeLazy(fn) {
      this.lazyListeners = this.lazyListeners.filter((item) => item !== fn);
    }

    connect() {

      return new Promise((resolve, reject) => {

        const ws = new WebSocket(STEPOVER_WS);

        const timer = global.setTimeout(() => {

          try { ws.close(); } catch { /* ignore */ }

          reject(new Error("stepover_ws_timeout"));

        }, 8000);

        ws.onopen = () => {

          global.clearTimeout(timer);

          this.ws = ws;

          ws.onmessage = (event) => this._onMessage(event);

          ws.onclose = () => { this.ws = null; };

          resolve();

        };

        ws.onerror = () => {

          global.clearTimeout(timer);

          reject(new Error("stepover_ws_unreachable"));

        };

      });

    }



    close() {

      try {

        this.ws?.close();

      } catch {

        // ignore

      }

      this.ws = null;

      this.pending.clear();

      this.lazyListeners = [];

    }



    _onMessage(event) {

      let msg;

      try {

        msg = JSON.parse(String(event.data || "{}"));

      } catch {

        return;

      }

      const messageId = msg.messageId || msg.data?.messageId;

      if (messageId && this.pending.has(messageId)) {

        const entry = this.pending.get(messageId);

        this.pending.delete(messageId);

        if (msg.type === "response" && String(msg.data?.ret || "").toLowerCase() === "ok") {

          entry.resolve(msg.data);

          return;

        }

        if (msg.type === "response" && msg.data?.ret != null) {

          entry.resolve(msg.data);

          return;

        }

        entry.reject(new Error("stepover_response_error"));

        return;

      }

      if (msg.type && msg.type.startsWith("onStaticApplet")) {
        this.lazyListeners.slice().forEach((fn) => {
          try { fn(msg); } catch { /* ignore */ }
        });
      }
    }

    waitLazy(type, timeoutMs = 120000) {
      return new Promise((resolve, reject) => {
        const timer = global.setTimeout(() => {
          this._removeLazy(fn);
          reject(new Error("stepover_capture_timeout"));
        }, timeoutMs);
        const fn = (msg) => {
          if (msg.type !== type) return;
          global.clearTimeout(timer);
          this._removeLazy(fn);
          resolve(msg);
        };
        this.lazyListeners.push(fn);
      });
    }



    request(type, data = {}) {

      return new Promise((resolve, reject) => {

        if (!this.ws) {

          reject(new Error("stepover_ws_closed"));

          return;

        }

        const messageId = newMessageId();

        this.pending.set(messageId, { resolve, reject });

        this.ws.send(JSON.stringify({ messageId, type, data: { ...data, messageId } }));

      });

    }

  }



  async function stepoverCapture(options = {}) {

    const hint = String(options.customText || options.hint || options.fieldName || "SUPPIX").trim();

    const client = new StepOverClient();

    await client.connect();

    try {

      await client.request("start");

      await sleep(400);

      const count = await client.request("getDeviceCount");

      if (Number(count?.ret || 0) < 1) throw new Error("stepover_no_device");



      const textLines = { 0: hint.slice(0, 48) || "Bitte unterschreiben" };

      await client.request("startSigning", {

        page: 0,

        x: 36,

        y: 120,

        width: 320,

        height: 100,

        resolution: 150,

        signatureTimeout: Number(options.maxWaitMs || 120000),

        config: {

          signMode: "standard",

          textLines,

        },

      });



      const finishedPromise = client.waitLazy("onStaticAppletSignatureFinished");

      const cancelPromise = client.waitLazy("onStaticAppletSignatureCancel").then(() => {

        throw new Error("signature_cancelled");

      });

      await Promise.race([finishedPromise, cancelPromise]);



      const canvas = options.canvas || global.document?.getElementById?.("complianceSignatureCanvas");

      const width = canvas?.width || 520;

      const height = canvas?.height || 160;

      const prelim = await client.request("getPreliminaryData", {

        width,

        height,

        withAlpha: false,

      });

      const ret = prelim?.ret;

      const rawImage = Array.isArray(ret) ? String(ret[2] || "").trim() : "";

      if (!rawImage) throw new Error("stepover_empty_signature");

      const dataUrl = rawImage.startsWith("data:") ? rawImage : `data:image/png;base64,${rawImage}`;

      await client.request("stopSigning", { showManufacturerLogo: true }).catch(() => {});

      return { dataUrl, provider: "stepover" };

    } finally {

      client.close();

    }

  }



  async function stepoverProbe() {

    const client = new StepOverClient();

    try {

      await client.connect();

      const version = await client.request("getVersion");

      const count = await client.request("getDeviceCount");

      if (Number(count?.ret || 0) < 1) {

        return { ok: false, reason: "stepover_no_device", detail: String(version?.ret || "") };

      }

      return { ok: true, detail: String(version?.ret || "pad-connector"), meta: { devices: count.ret } };

    } catch (err) {

      return { ok: false, reason: err?.message || "stepover_ws_unreachable" };

    } finally {

      client.close();

    }

  }



  /* ── Topaz SigWeb ─────────────────────────────────────────────────────── */



  function topazApiReady() {

    return typeof global.IsSigWebInstalled === "function"

      && typeof global.SetTabletState === "function"

      && typeof global.GetSigImageB64 === "function";

  }



  async function loadTopazScript() {

    if (!(await vendorAssetExists("./vendor/topaz/SigWebTablet.js"))) return false;

    return loadScriptOnce("./vendor/topaz/SigWebTablet.js", "topaz");

  }



  function topazStopTablet(timerRef) {

    try {

      if (timerRef?.value != null) global.SetTabletState(0, timerRef.value);

    } catch {

      // ignore

    }

    timerRef.value = null;

    try {

      global.SetTabletComTest?.(false);

    } catch {

      // ignore

    }

  }



  function topazGetImageB64() {

    return new Promise((resolve, reject) => {

      try {

        global.GetSigImageB64((b64) => {

          const raw = String(b64 || "").trim();

          if (!raw) {

            reject(new Error("topaz_empty_signature"));

            return;

          }

          resolve(raw.startsWith("data:") ? raw : `data:image/png;base64,${raw}`);

        });

      } catch (err) {

        reject(err instanceof Error ? err : new Error(String(err || "topaz_capture_failed")));

      }

    });

  }



  async function topazCapture(options = {}) {

    await loadTopazScript();

    if (!topazApiReady()) throw new Error("topaz_lib_missing");

    if (!global.IsSigWebInstalled()) throw new Error("topaz_not_installed");



    const canvas = options.canvas || global.document?.getElementById?.("complianceSignatureCanvas");

    if (!canvas) throw new Error("topaz_no_canvas");

    const ctx = canvas.getContext("2d");

    if (!ctx) throw new Error("topaz_no_canvas");



    const timerRef = { value: null };

    try {

      global.ClearTablet?.();

      global.SetDisplayXSize?.(canvas.width);

      global.SetDisplayYSize?.(canvas.height);

      global.SetJustifyMode?.(0);

      if (typeof global.SetImagePenWidth === "function") global.SetImagePenWidth(4);

      if (typeof global.SetImageXSize === "function") global.SetImageXSize(canvas.width);

      if (typeof global.SetImageYSize === "function") global.SetImageYSize(canvas.height);



      ctx.fillStyle = "#ffffff";

      ctx.fillRect(0, 0, canvas.width, canvas.height);



      global.SetTabletComTest?.(true);

      timerRef.value = global.SetTabletState(1, ctx, 50);

      await sleep(300);



      if (typeof global.GetTabletState === "function" && global.GetTabletState() === 0) {

        throw new Error("topaz_no_device");

      }



      const idleMs = Number(options.idleMs || 1800);

      const maxWaitMs = Number(options.maxWaitMs || 120000);

      const started = Date.now();

      let lastSig = "";

      let lastChange = Date.now();

      const blankCanvas = global.document.createElement("canvas");

      blankCanvas.width = canvas.width;

      blankCanvas.height = canvas.height;

      const blankCtx = blankCanvas.getContext("2d");

      if (blankCtx) {

        blankCtx.fillStyle = "#ffffff";

        blankCtx.fillRect(0, 0, blankCanvas.width, blankCanvas.height);

      }

      const blankDataUrl = blankCanvas.toDataURL("image/png");



      while (Date.now() - started < maxWaitMs) {

        await sleep(200);

        const snap = canvas.toDataURL("image/png");

        if (snap !== lastSig) {

          lastSig = snap;

          lastChange = Date.now();

        }

        if (lastSig && lastSig !== blankDataUrl && (Date.now() - lastChange) >= idleMs) break;

      }



      if (!lastSig || lastSig === blankDataUrl) throw new Error("topaz_empty_signature");



      const dataUrl = await topazGetImageB64();

      return { dataUrl, provider: "topaz" };

    } finally {

      topazStopTablet(timerRef);

      try {

        global.ClearTablet?.();

      } catch {

        // ignore

      }

    }

  }



  /* ── Canvas fallback ────────────────────────────────────────────────────── */



  async function canvasCapture(options = {}) {

    const canvas = options.canvas || global.document?.getElementById?.("complianceSignatureCanvas");

    if (!canvas) throw new Error("canvas_missing");

    canvas.focus?.();

    canvas.scrollIntoView?.({ behavior: "smooth", block: "nearest" });

    throw new Error("signature_use_canvas");

  }



  /* ── Register providers (market priority: DE/EU first, then global) ───── */

  async function signotecProbe() {
    if (!(await signotecLoadLib())) return { ok: false, reason: "signotec_lib_missing" };
    try {
      await signotecEnsureConnection({ timeoutMs: 2500 });
      let serverVersion = "";
      try {
        const info = await global.STPadServerLibCommons.getServerVersion();
        serverVersion = String(info?.serverVersion || "");
      } catch {
        // ignore
      }
      return { ok: true, detail: serverVersion, meta: { serverVersion } };
    } catch (err) {
      return { ok: false, reason: err?.message || "signotec_ws_unreachable" };
    }
  }

  bridge.registerProvider({

    id: "signotec",

    labelKey: "signatureProviderSignotec",

    order: 10,

    probe: signotecProbe,

    capture: signotecCapture,

  });



  bridge.registerProvider({

    id: "wacom",

    labelKey: "signatureProviderWacom",

    order: 15,

    probe: async () => {

      const loaded = await loadWacomScripts();

      if (!loaded) return { ok: false, reason: "wacom_lib_missing" };

      await wacomWaitServiceReady(4, 250);

      if (!global.WacomGSS.STU.isServiceReady()) {

        return { ok: false, reason: "wacom_service_not_ready" };

      }

      const dcaReady = await global.WacomGSS.STU.isDCAReady();

      if (!dcaReady) return { ok: false, reason: "wacom_dca_not_ready" };

      try {

        const devices = await global.WacomGSS.STU.getUsbDevices();

        if (!devices || devices.length === 0) return { ok: false, reason: "wacom_no_device" };

        return { ok: true, detail: String(devices[0]?.modelName || "STU") };

      } catch (err) {

        return { ok: false, reason: err?.message || "wacom_probe_failed" };

      }

    },

    capture: wacomCapture,

  });



  bridge.registerProvider({

    id: "stepover",

    labelKey: "signatureProviderStepover",

    order: 18,

    probe: stepoverProbe,

    capture: stepoverCapture,

  });



  bridge.registerProvider({

    id: "topaz",

    labelKey: "signatureProviderTopaz",

    order: 20,

    probe: async () => {

      const loaded = await loadTopazScript();

      if (!loaded || !topazApiReady()) return { ok: false, reason: "topaz_lib_missing" };

      if (!global.IsSigWebInstalled()) return { ok: false, reason: "topaz_not_installed" };

      return { ok: true, detail: "sigweb" };

    },

    capture: topazCapture,

  });



  bridge.registerProvider({

    id: "canvas",

    labelKey: "signatureProviderCanvas",

    order: 900,

    probe: async () => {

      const canvas = global.document?.getElementById?.("complianceSignatureCanvas");

      return { ok: Boolean(canvas), detail: "pointer_events" };

    },

    capture: canvasCapture,

  });



  if (global.document) {

    const preloadSignotec = () => {

      signotecBindGlobals();

      void signotecLoadLib();

    };

    if (global.document.readyState === "loading") {

      global.document.addEventListener("DOMContentLoaded", preloadSignotec, { once: true });

    } else {

      preloadSignotec();

    }

  }



  global.BaupassSignotec = {

    isAvailable: signotecLibsReady,

    loadLib: signotecLoadLib,

    resetSession: signotecResetSession,

    captureSignature: signotecCapture,

    probeConnection: async () => {
      const probe = await signotecProbe();
      return probe.ok
        ? { ok: true, serverVersion: probe.meta?.serverVersion || probe.detail || "" }
        : { ok: false, reason: probe.reason || "signotec_ws_unreachable" };
    },

    destroyConnection: () => {

      void signotecResetSession({ reconnect: false });

    },

  };

})(window);


