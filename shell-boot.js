/**
 * Safe shell boot: paint HTML/CSS first, then run the large app.js.
 * No bundler — only deferred classic-script injection + idle secondary chunk.
 */
(function (global) {
  var APP_SRC = "./app.js?v=20260818assist14";
  var SECONDARY_SRC = "./app-secondary.js?v=20260817sector1";

  var bootResolve;
  var bootReject;
  global.BaupassAppReady = new Promise(function (resolve, reject) {
    bootResolve = resolve;
    bootReject = reject;
  });

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[data-baupass-boot="' + src + '"]');
      if (existing) {
        if (existing.dataset.loaded === "1") {
          resolve();
          return;
        }
        existing.addEventListener("load", function () { resolve(); }, { once: true });
        existing.addEventListener(
          "error",
          function () { reject(new Error("script_load_failed")); },
          { once: true },
        );
        return;
      }
      var script = document.createElement("script");
      script.src = src;
      // Preserve classic-script order semantics relative to other injected files.
      script.async = false;
      script.dataset.baupassBoot = src;
      script.onload = function () {
        script.dataset.loaded = "1";
        resolve();
      };
      script.onerror = function () {
        reject(new Error("script_load_failed:" + src));
      };
      document.head.appendChild(script);
    });
  }

  global.BaupassLazy = global.BaupassLazy || {};
  global.BaupassLazy.loadScript = loadScript;
  global.BaupassLazy.loadSecondary = function loadSecondary() {
    if (global.__baupassSecondaryPromise) return global.__baupassSecondaryPromise;
    global.__baupassSecondaryPromise = loadScript(SECONDARY_SRC).catch(function () {
      global.__baupassSecondaryPromise = null;
    });
    return global.__baupassSecondaryPromise;
  };

  document.documentElement.classList.add("app-booting");

  function startMain() {
    loadScript(APP_SRC)
      .then(function () {
        document.documentElement.classList.remove("app-booting");
        document.documentElement.classList.add("app-ready");
        bootResolve();
        var warm = function () {
          global.BaupassLazy.loadSecondary();
        };
        if (typeof requestIdleCallback === "function") {
          requestIdleCallback(warm, { timeout: 5000 });
        } else {
          global.setTimeout(warm, 2500);
        }
      })
      .catch(function (err) {
        document.documentElement.classList.remove("app-booting");
        document.documentElement.classList.add("app-boot-failed");
        var loader = document.getElementById("appBootLoader");
        if (loader) {
          loader.classList.remove("hidden");
          loader.setAttribute("aria-hidden", "false");
          loader.innerHTML =
            '<div style="max-width:28rem;padding:1.25rem;border-radius:12px;background:#0f172a;color:#e2e8f0;text-align:center;line-height:1.45">' +
            "<strong>App konnte nicht geladen werden.</strong><br>" +
            "<span style=\"opacity:.85;font-size:.92rem\">Bitte Strg+F5 und erneut versuchen.</span>" +
            "</div>";
        }
        bootReject(err);
      });
  }

  function afterFirstPaint(fn) {
    var run = function () {
      if (typeof requestAnimationFrame === "function") {
        requestAnimationFrame(function () {
          requestAnimationFrame(fn);
        });
      } else {
        global.setTimeout(fn, 0);
      }
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", run, { once: true });
    } else {
      run();
    }
  }

  afterFirstPaint(startMain);
})(window);
