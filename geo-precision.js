(function (global) {
  "use strict";

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
    };
  }

  async function capturePreciseGeolocation(options) {
    const opts = Object.assign(
      {
        minSamples: 3,
        maxSamples: 6,
        targetAccuracyMeters: 20,
        maxWaitMs: 18000,
        maxAcceptedAccuracyMeters: 80,
      },
      options || {},
    );

    if (!global.navigator || !global.navigator.geolocation) {
      const error = new Error("geolocation_unsupported");
      error.code = 0;
      throw error;
    }

    return new Promise((resolve, reject) => {
      const samples = [];
      let settled = false;
      let watchId = null;

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

      const timer = setTimeout(() => {
        if (!samples.length) {
          const error = new Error("geolocation_timeout");
          error.code = 3;
          finish(error);
          return;
        }
        finish(null, weightedAverage(samples));
      }, opts.maxWaitMs);

      watchId = global.navigator.geolocation.watchPosition(
        (position) => {
          const accuracy = Number(position.coords.accuracy) || 999;
          if (accuracy > opts.maxAcceptedAccuracyMeters) {
            return;
          }
          samples.push({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy,
          });
          const bestAccuracy = Math.min(...samples.map((sample) => sample.accuracy));
          if (
            samples.length >= opts.minSamples &&
            (bestAccuracy <= opts.targetAccuracyMeters || samples.length >= opts.maxSamples)
          ) {
            finish(null, weightedAverage(samples));
          }
        },
        (error) => finish(error || Object.assign(new Error("geolocation_failed"), { code: 2 })),
        { enableHighAccuracy: true, maximumAge: 0, timeout: opts.maxWaitMs },
      );
    });
  }

  global.capturePreciseGeolocation = capturePreciseGeolocation;
})(typeof globalThis !== "undefined" ? globalThis : window);
