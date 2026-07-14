(function (global) {
  "use strict";

  const PRESETS = {
    maps: {
      minSamples: 3,
      maxSamples: 14,
      targetAccuracyMeters: 10,
      maxWaitMs: 45000,
      stableThresholdMeters: 6,
      singleTimeoutMs: 20000,
    },
    balanced: {
      minSamples: 2,
      maxSamples: 8,
      targetAccuracyMeters: 15,
      maxWaitMs: 25000,
      stableThresholdMeters: 10,
      singleTimeoutMs: 15000,
    },
    fast: {
      minSamples: 1,
      maxSamples: 4,
      targetAccuracyMeters: 25,
      maxWaitMs: 12000,
      stableThresholdMeters: 15,
      singleTimeoutMs: 10000,
    },
    instant: {
      fastTimeoutMs: 1500,
      fastMaximumAgeMs: 60000,
      cachedTimeoutMs: 3500,
      cachedMaximumAgeMs: 30000,
      freshTimeoutMs: 12000,
    },
    site: {
      minSamples: 1,
      maxSamples: 10,
      targetAccuracyMeters: 10,
      maxWaitMs: 9000,
      stableThresholdMeters: 8,
      singleTimeoutMs: 2000,
    },
    chat: {
      minSamples: 1,
      maxSamples: 10,
      targetAccuracyMeters: 5,
      acceptAccuracyMeters: 8,
      maxWaitMs: 2500,
      stableThresholdMeters: 2,
      singleTimeoutMs: 2000,
    },
  };

  const UI_POINT_MAX_WAIT_MS = 5000;
  const UI_POINT_EARLY_BEST_MS = 3000;
  const UI_POINT_ACCEPT_ACCURACY_METERS = 25;
  const SITE_ANCHOR_MAX_ACCEPT_ACCURACY_METERS = 15;
  const SITE_ANCHOR_FALLBACK_MAX_ACCURACY_METERS = 25;
  const SITE_ANCHOR_FAST_TIMEOUT_MS = 1200;
  const SITE_ANCHOR_HARD_MAX_MS = 5000;

  function haversineMeters(latitudeA, longitudeA, latitudeB, longitudeB) {
    const earthRadiusMeters = 6371000;
    const toRadians = (value) => (value * Math.PI) / 180;
    const lat1 = toRadians(Number(latitudeA));
    const lat2 = toRadians(Number(latitudeB));
    const dLat = lat2 - lat1;
    const dLon = toRadians(Number(longitudeB)) - toRadians(Number(longitudeA));
    const haversine =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
    return 2 * earthRadiusMeters * Math.asin(Math.sqrt(haversine));
  }

  function median(values) {
    if (!values.length) {
      return 0;
    }
    const sorted = [...values].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 0
      ? (sorted[mid - 1] + sorted[mid]) / 2
      : sorted[mid];
  }

  function weightedAverage(samples) {
    if (!samples.length) {
      return null;
    }
    let weightedLat = 0;
    let weightedLon = 0;
    let totalWeight = 0;
    let bestAccuracy = Infinity;
    for (const sample of samples) {
      const accuracy = Math.max(Number(sample.accuracy) || 50, 1);
      const weight = 1 / (accuracy * accuracy);
      weightedLat += sample.latitude * weight;
      weightedLon += sample.longitude * weight;
      totalWeight += weight;
      if (accuracy < bestAccuracy) {
        bestAccuracy = accuracy;
      }
    }
    return {
      latitude: weightedLat / totalWeight,
      longitude: weightedLon / totalWeight,
      accuracy: bestAccuracy,
      sampleCount: samples.length,
    };
  }

  function rejectOutliers(samples) {
    if (samples.length <= 2) {
      return samples;
    }
    const sorted = [...samples].sort(
      (a, b) => (Number(a.accuracy) || 999) - (Number(b.accuracy) || 999),
    );
    const candidates = sorted.slice(0, Math.min(6, sorted.length));
    const centerLat = median(candidates.map((sample) => sample.latitude));
    const centerLon = median(candidates.map((sample) => sample.longitude));
    const maxSpread = Math.max(
      12,
      Math.min(...candidates.map((sample) => Number(sample.accuracy) || 20)) * 1.5,
    );
    return candidates.filter(
      (sample) =>
        haversineMeters(sample.latitude, sample.longitude, centerLat, centerLon) <=
        maxSpread,
    );
  }

  function finalizePosition(samples) {
    const filtered = rejectOutliers(samples);
    if (!filtered.length) {
      return null;
    }
    const sorted = [...filtered].sort(
      (a, b) => (Number(a.accuracy) || 999) - (Number(b.accuracy) || 999),
    );
    const best = sorted[0];
    const top = sorted.slice(0, Math.min(3, sorted.length));
    if ((Number(best.accuracy) || 999) <= 15 && top.length >= 2) {
      return weightedAverage(top);
    }
    return {
      latitude: best.latitude,
      longitude: best.longitude,
      accuracy: Number(best.accuracy) || null,
      sampleCount: filtered.length,
    };
  }

  function samplesAreStable(samples, thresholdMeters) {
    if (samples.length < 3) {
      return false;
    }
    const recent = samples.slice(-3);
    const centerLat = recent.reduce((sum, sample) => sum + sample.latitude, 0) / recent.length;
    const centerLon = recent.reduce((sum, sample) => sum + sample.longitude, 0) / recent.length;
    return recent.every(
      (sample) =>
        haversineMeters(sample.latitude, sample.longitude, centerLat, centerLon) <=
        thresholdMeters,
    );
  }

  function normalizeGeolocationError(error, fallbackCode) {
    if (error && typeof error.code === "number") {
      return error;
    }
    const wrapped = new Error(error?.message || "geolocation_failed");
    wrapped.code = typeof fallbackCode === "number" ? fallbackCode : 2;
    return wrapped;
  }

  function readPosition(position) {
    return {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      accuracy: Number(position.coords.accuracy) || null,
      capturedAt: Date.now(),
    };
  }

  function getCurrentGeolocationReading(options) {
    const opts = Object.assign(
      {
        enableHighAccuracy: true,
        timeout: 20000,
        maximumAge: 0,
      },
      options || {},
    );

    return new Promise((resolve, reject) => {
      global.navigator.geolocation.getCurrentPosition(
        (position) => resolve(readPosition(position)),
        (error) => reject(normalizeGeolocationError(error, 2)),
        opts,
      );
    });
  }

  function watchGeolocationSamples(options) {
    const opts = Object.assign({}, PRESETS.balanced, options || {});

    return new Promise((resolve, reject) => {
      const samples = [];
      let settled = false;
      let watchId = null;

      const reportProgress = () => {
        if (typeof opts.onProgress !== "function" || !samples.length) {
          return;
        }
        const bestAccuracy = Math.min(
          ...samples.map((sample) => Number(sample.accuracy) || 999),
        );
        opts.onProgress({
          sampleCount: samples.length,
          bestAccuracyMeters: bestAccuracy,
          latestAccuracyMeters: Number(samples[samples.length - 1].accuracy) || null,
        });
      };

      const finish = (error, result) => {
        if (settled) {
          return;
        }
        settled = true;
        if (watchId != null) {
          try {
            global.navigator.geolocation.clearWatch(watchId);
          } catch (_) {
            // ignore
          }
        }
        clearTimeout(timer);
        if (error) {
          reject(error);
          return;
        }
        resolve(result);
      };

      const maybeFinishEarly = () => {
        const bestAccuracy = Math.min(
          ...samples.map((sample) => Number(sample.accuracy) || 999),
        );
        const acceptAccuracy = Number(opts.acceptAccuracyMeters);
        if (Number.isFinite(acceptAccuracy) && acceptAccuracy > 0 && bestAccuracy <= acceptAccuracy) {
          finish(null, finalizePosition(samples));
          return true;
        }
        const stable = samplesAreStable(samples, opts.stableThresholdMeters);
        if (
          samples.length >= opts.minSamples &&
          bestAccuracy <= opts.targetAccuracyMeters &&
          stable
        ) {
          finish(null, finalizePosition(samples));
          return true;
        }
        if (
          samples.length >= opts.maxSamples &&
          bestAccuracy <= opts.targetAccuracyMeters + 5
        ) {
          finish(null, finalizePosition(samples));
          return true;
        }
        return false;
      };

      const timer = setTimeout(() => {
        if (!samples.length) {
          const error = new Error("geolocation_timeout");
          error.code = 3;
          finish(error);
          return;
        }
        finish(null, finalizePosition(samples));
      }, opts.maxWaitMs);

      watchId = global.navigator.geolocation.watchPosition(
        (position) => {
          samples.push(readPosition(position));
          if (samples.length > opts.maxSamples + 4) {
            samples.splice(0, samples.length - (opts.maxSamples + 2));
          }
          reportProgress();
          maybeFinishEarly();
        },
        (error) => finish(normalizeGeolocationError(error, 2)),
        { enableHighAccuracy: true, maximumAge: 0, timeout: opts.maxWaitMs },
      );
    });
  }

  async function capturePreciseGeolocation(options) {
    if (!global.navigator || !global.navigator.geolocation) {
      const error = new Error("geolocation_unsupported");
      error.code = 0;
      throw error;
    }

    const preset = PRESETS[options?.preset] || PRESETS.balanced;
    const opts = Object.assign({}, preset, options || {});
    delete opts.preset;

    try {
      return await watchGeolocationSamples(opts);
    } catch (error) {
      if (Number(error?.code) === 1) {
        throw error;
      }
      try {
        const single = await getCurrentGeolocationReading({
          enableHighAccuracy: true,
          timeout: opts.singleTimeoutMs,
          maximumAge: 0,
        });
        return {
          latitude: single.latitude,
          longitude: single.longitude,
          accuracy: single.accuracy,
          sampleCount: 1,
        };
      } catch (singleError) {
        if (Number(singleError?.code) === 1) {
          throw singleError;
        }
        throw error.code != null ? error : singleError;
      }
    }
  }

  async function captureMapsGradeGeolocation(options) {
    return capturePreciseGeolocation(
      Object.assign({ preset: "maps" }, options || {}),
    );
  }

  async function captureSiteAnchorGeolocation(options) {
    if (!global.navigator || !global.navigator.geolocation) {
      const error = new Error("geolocation_unsupported");
      error.code = 0;
      throw error;
    }

    const opts = Object.assign(
      {
        maxAcceptAccuracyMeters: SITE_ANCHOR_MAX_ACCEPT_ACCURACY_METERS,
        quickReturnMs: SITE_ANCHOR_FAST_TIMEOUT_MS,
        hardMaxMs: SITE_ANCHOR_HARD_MAX_MS,
        fallbackMaxAccuracyMeters: SITE_ANCHOR_FALLBACK_MAX_ACCURACY_METERS,
      },
      options || {},
    );
    const maxAccept = Number(opts.maxAcceptAccuracyMeters) || SITE_ANCHOR_MAX_ACCEPT_ACCURACY_METERS;
    const fallbackMax =
      Number(opts.fallbackMaxAccuracyMeters) || SITE_ANCHOR_FALLBACK_MAX_ACCURACY_METERS;
    const quickReturnMs = Number(opts.quickReturnMs) || SITE_ANCHOR_FAST_TIMEOUT_MS;
    const hardMaxMs = Number(opts.hardMaxMs) || SITE_ANCHOR_HARD_MAX_MS;

    return new Promise((resolve, reject) => {
      const samples = [];
      let settled = false;
      let watchId = null;
      let quickTimer = null;
      let hardTimer = null;

      const pickBest = () => {
        if (!samples.length) {
          return null;
        }
        return [...samples].sort(
          (a, b) => (Number(a.accuracy) || 999) - (Number(b.accuracy) || 999),
        )[0];
      };

      const cleanup = () => {
        if (quickTimer) {
          clearTimeout(quickTimer);
          quickTimer = null;
        }
        if (hardTimer) {
          clearTimeout(hardTimer);
          hardTimer = null;
        }
        if (watchId != null) {
          try {
            global.navigator.geolocation.clearWatch(watchId);
          } catch (_) {
            // ignore
          }
          watchId = null;
        }
      };

      const finish = (error, result) => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        if (error) {
          reject(error);
          return;
        }
        resolve(result);
      };

      const tryFinishWithReading = (reading) => {
        const accuracy = Number(reading?.accuracy);
        if (!reading || !Number.isFinite(accuracy) || accuracy > maxAccept) {
          return false;
        }
        finish(null, reading);
        return true;
      };

      const handleSample = (reading) => {
        samples.push(reading);
        if (samples.length > 20) {
          samples.splice(0, samples.length - 16);
        }
        const best = pickBest();
        if (typeof opts.onSample === "function") {
          opts.onSample(reading, best);
        }
        if (tryFinishWithReading(reading) || tryFinishWithReading(best)) {
          return true;
        }
        if (typeof opts.onProgress === "function" && best) {
          opts.onProgress({
            sampleCount: samples.length,
            bestAccuracyMeters: Number(best.accuracy),
            phase: "watch",
          });
        }
        return false;
      };

      quickTimer = setTimeout(() => {
        const best = pickBest();
        if (typeof opts.onQuickReturn === "function" && best) {
          opts.onQuickReturn(best);
        }
      }, quickReturnMs);

      hardTimer = setTimeout(() => {
        const best = pickBest();
        if (!best) {
          const timeoutError = new Error("geolocation_timeout");
          timeoutError.code = 3;
          finish(timeoutError);
          return;
        }
        const accuracy = Number(best.accuracy);
        if (Number.isFinite(accuracy) && accuracy <= maxAccept) {
          finish(null, best);
          return;
        }
        if (Number.isFinite(accuracy) && accuracy <= fallbackMax) {
          finish(null, Object.assign({}, best, { weakAccuracy: true }));
          return;
        }
        const refined = finalizePosition(samples);
        if (refined && Number(refined.accuracy) <= fallbackMax) {
          finish(null, Object.assign({}, refined, { weakAccuracy: true }));
          return;
        }
        const inaccurateError = new Error("geolocation_inaccurate");
        inaccurateError.code = 4;
        inaccurateError.accuracyMeters = Number.isFinite(accuracy) ? accuracy : null;
        finish(inaccurateError);
      }, hardMaxMs);

      watchId = global.navigator.geolocation.watchPosition(
        (position) => {
          if (handleSample(readPosition(position))) {
            return;
          }
        },
        (error) => {
          const best = pickBest();
          if (Number(error?.code) === 1) {
            finish(normalizeGeolocationError(error, 1));
            return;
          }
          if (best && tryFinishWithReading(best)) {
            return;
          }
          if (!best) {
            finish(normalizeGeolocationError(error, 2));
            return;
          }
          const inaccurateError = new Error("geolocation_inaccurate");
          inaccurateError.code = 4;
          inaccurateError.accuracyMeters = Number(best.accuracy) || null;
          finish(inaccurateError);
        },
        { enableHighAccuracy: true, maximumAge: 0, timeout: hardMaxMs },
      );
    });
  }

  async function captureInstantGeolocation(options) {
    if (!global.navigator || !global.navigator.geolocation) {
      const error = new Error("geolocation_unsupported");
      error.code = 0;
      throw error;
    }

    const opts = Object.assign({}, PRESETS.instant, options || {});
    const attempts = [
      {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: Number(opts.fastTimeoutMs) || 1500,
      },
      {
        enableHighAccuracy: true,
        maximumAge: Number(opts.cachedMaximumAgeMs) || 15000,
        timeout: Number(opts.cachedTimeoutMs) || 3500,
      },
    ];

    let lastError = null;
    for (let index = 0; index < attempts.length; index += 1) {
      try {
        const reading = await getCurrentGeolocationReading(attempts[index]);
        if (typeof opts.onAttempt === "function") {
          opts.onAttempt({ index, reading, attempt: attempts[index] });
        }
        return reading;
      } catch (error) {
        if (Number(error?.code) === 1) {
          throw error;
        }
        lastError = error;
        if (typeof opts.onAttempt === "function") {
          opts.onAttempt({ index, error, attempt: attempts[index] });
        }
      }
    }

    const timeoutError = lastError || new Error("geolocation_timeout");
    if (timeoutError.code == null) {
      timeoutError.code = 3;
    }
    throw timeoutError;
  }

  async function capturePointGeolocation(options) {
    if (!global.navigator || !global.navigator.geolocation) {
      const error = new Error("geolocation_unsupported");
      error.code = 0;
      throw error;
    }

    const opts = Object.assign(
      {
        maxWaitMs: UI_POINT_MAX_WAIT_MS,
        cachedMaximumAgeMs: 300000,
      },
      options || {},
    );
    const maxWaitMs = Math.min(
      Math.max(Number(opts.maxWaitMs) || UI_POINT_MAX_WAIT_MS, 1500),
      UI_POINT_MAX_WAIT_MS,
    );
    const deadline = Date.now() + maxWaitMs;
    const onProgress = typeof opts.onProgress === "function" ? opts.onProgress : null;

    const attempts = [
      {
        enableHighAccuracy: false,
        maximumAge: Number(opts.cachedMaximumAgeMs) || 300000,
        timeout: 1500,
      },
      {
        enableHighAccuracy: true,
        maximumAge: 120000,
        timeout: 2000,
      },
      {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: 3000,
      },
    ];

    for (let index = 0; index < attempts.length; index += 1) {
      const remainingMs = deadline - Date.now();
      if (remainingMs <= 200) {
        break;
      }
      const attempt = attempts[index];
      try {
        const reading = await getCurrentGeolocationReading({
          enableHighAccuracy: attempt.enableHighAccuracy,
          maximumAge: attempt.maximumAge,
          timeout: Math.min(attempt.timeout, remainingMs),
        });
        if (
          reading &&
          Number.isFinite(Number(reading.latitude)) &&
          Number.isFinite(Number(reading.longitude))
        ) {
          if (onProgress) {
            onProgress({
              sampleCount: 1,
              bestAccuracyMeters: Number(reading.accuracy),
              phase: index === 0 ? "cached" : "single",
            });
          }
          return reading;
        }
      } catch (error) {
        if (Number(error?.code) === 1) {
          throw error;
        }
      }
    }

    const remainingMs = deadline - Date.now();
    if (remainingMs <= 200) {
      const timeoutError = new Error("geolocation_timeout");
      timeoutError.code = 3;
      throw timeoutError;
    }

    return new Promise((resolve, reject) => {
      const samples = [];
      let settled = false;
      let watchId = null;
      let hardTimer = null;
      let refineTimer = null;
      const startedAt = Date.now();

      const pickBest = () => {
        if (!samples.length) {
          return null;
        }
        return [...samples].sort(
          (a, b) => (Number(a.accuracy) || 999) - (Number(b.accuracy) || 999),
        )[0];
      };

      const cleanup = () => {
        if (hardTimer) {
          clearTimeout(hardTimer);
          hardTimer = null;
        }
        if (refineTimer) {
          clearTimeout(refineTimer);
          refineTimer = null;
        }
        if (watchId != null) {
          try {
            global.navigator.geolocation.clearWatch(watchId);
          } catch (_) {
            // ignore
          }
          watchId = null;
        }
      };

      const finish = (error, result) => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        if (error) {
          reject(error);
          return;
        }
        resolve(result);
      };

      const finishWithBest = () => {
        const best = pickBest();
        if (best) {
          finish(null, best);
          return;
        }
        const timeoutError = new Error("geolocation_timeout");
        timeoutError.code = 3;
        finish(timeoutError);
      };

      const noteSample = () => {
        if (!onProgress) {
          return;
        }
        const best = pickBest();
        onProgress({
          sampleCount: samples.length,
          bestAccuracyMeters: best ? Number(best.accuracy) : null,
          phase: "watch",
        });
      };

      const scheduleRefineFinish = () => {
        if (refineTimer || settled) {
          return;
        }
        refineTimer = setTimeout(() => {
          refineTimer = null;
          if (!settled) {
            finishWithBest();
          }
        }, Math.min(700, Math.max(200, deadline - Date.now())));
      };

      hardTimer = setTimeout(finishWithBest, Math.max(200, deadline - Date.now()));

      watchId = global.navigator.geolocation.watchPosition(
        (position) => {
          samples.push(readPosition(position));
          if (samples.length > 6) {
            samples.splice(0, samples.length - 4);
          }
          noteSample();
          const best = pickBest();
          if (!best) {
            return;
          }
          const accuracy = Number(best.accuracy);
          if (Number.isFinite(accuracy) && accuracy <= UI_POINT_ACCEPT_ACCURACY_METERS) {
            finish(null, best);
            return;
          }
          if (samples.length === 1) {
            scheduleRefineFinish();
          } else if (Date.now() - startedAt >= 700) {
            finish(null, best);
          }
        },
        (error) => {
          if (Number(error?.code) === 1) {
            finish(normalizeGeolocationError(error, 1));
            return;
          }
          const best = pickBest();
          if (best) {
            finish(null, best);
          }
        },
        {
          enableHighAccuracy: true,
          maximumAge: 0,
          timeout: Math.max(200, deadline - Date.now()),
        },
      );
    });
  }

  global.capturePreciseGeolocation = capturePreciseGeolocation;
  global.captureMapsGradeGeolocation = captureMapsGradeGeolocation;
  global.captureSiteAnchorGeolocation = captureSiteAnchorGeolocation;
  global.capturePointGeolocation = capturePointGeolocation;
  global.captureInstantGeolocation = captureInstantGeolocation;
  global.getCurrentGeolocationReading = getCurrentGeolocationReading;

  /**
   * High-accuracy GPS stream for live UI (chat location sheet).
   * Uses multi-sample averaging like maps-grade capture, never low-accuracy cache.
   */
  function startPreciseLocationWatch(options = {}) {
    if (!global.navigator?.geolocation) {
      return { stop() {}, finalize() { return null; } };
    }
    const preset = PRESETS[options.preset] || PRESETS.site;
    const opts = Object.assign({}, preset, options || {});
    const samples = [];
    let watchId = null;
    let timer = null;
    let stopped = false;
    const onProgress = typeof opts.onProgress === "function" ? opts.onProgress : null;
    const onError = typeof opts.onError === "function" ? opts.onError : null;
    const onDone = typeof opts.onDone === "function" ? opts.onDone : null;

    const emit = () => {
      const finalized = finalizePosition(samples);
      if (!finalized || !onProgress) return;
      onProgress({
        reading: finalized,
        sampleCount: samples.length,
        bestAccuracyMeters: Number(finalized.accuracy) || null,
        phase: "watch",
      });
    };

    const stop = () => {
      if (stopped) return finalizePosition(samples);
      stopped = true;
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      if (watchId != null) {
        try {
          global.navigator.geolocation.clearWatch(watchId);
        } catch (_) {
          // ignore
        }
        watchId = null;
      }
      const finalReading = finalizePosition(samples);
      if (finalReading && onDone) onDone(finalReading);
      return finalReading;
    };

    watchId = global.navigator.geolocation.watchPosition(
      (position) => {
        samples.push(readPosition(position));
        if (samples.length > opts.maxSamples + 4) {
          samples.splice(0, samples.length - (opts.maxSamples + 2));
        }
        emit();
        const bestAccuracy = Math.min(
          ...samples.map((sample) => Number(sample.accuracy) || 999),
        );
        const acceptAccuracy = Number(opts.acceptAccuracyMeters);
        if (
          Number.isFinite(acceptAccuracy)
          && acceptAccuracy > 0
          && bestAccuracy <= acceptAccuracy
        ) {
          stop();
          return;
        }
        if (
          samples.length >= opts.minSamples
          && bestAccuracy <= opts.targetAccuracyMeters
          && samplesAreStable(samples, opts.stableThresholdMeters)
        ) {
          stop();
        }
      },
      (error) => {
        if (Number(error?.code) === 1) {
          stop();
          if (onError) onError(normalizeGeolocationError(error, 1));
          return;
        }
        const finalReading = finalizePosition(samples);
        if (finalReading) {
          stop();
          return;
        }
        if (onError) onError(normalizeGeolocationError(error, 2));
      },
      {
        enableHighAccuracy: true,
        maximumAge: 0,
        timeout: Math.max(1000, Number(opts.maxWaitMs) || preset.maxWaitMs),
      },
    );

    timer = setTimeout(stop, Math.max(1000, Number(opts.maxWaitMs) || preset.maxWaitMs));

    return {
      stop,
      finalize: () => finalizePosition(samples),
    };
  }

  global.startPreciseLocationWatch = startPreciseLocationWatch;
})(typeof globalThis !== "undefined" ? globalThis : window);
