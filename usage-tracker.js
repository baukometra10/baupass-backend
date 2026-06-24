/**
 * Shared feature-usage tracker for legacy dashboard, admin-v2, and worker PWA.
 * Throttles duplicate events; fails silently when offline or unauthenticated.
 */
(function initBaupassUsageTracker(global) {
  const THROTTLE_MS = 15000;
  const lastSent = new Map();

  const ADMIN_TOKEN_KEYS = window.WorkPassStorage?.SESSION_TOKEN_KEYS || [
    "workpass-admin-token",
    "workpass-session-token",
    "workpass-token",
  ];
  const WORKER_TOKEN_KEYS = [window.WorkPassStorage?.KEYS?.WORKER_TOKEN || "workpass-worker-token", "worker_app_token"];

  function readToken(keys) {
    const WP = window.WorkPassStorage;
    for (const key of keys) {
      try {
        const value = String((WP?.getItem ? WP.getItem(key) : global.localStorage?.getItem(key)) || "").trim();
        if (value) return value;
      } catch {
        // no-op
      }
    }
    return "";
  }

  function resolveEndpoint(source) {
    const workerSources = new Set(["worker-app", "worker-pwa", "mobile"]);
    if (workerSources.has(source)) {
      return { url: "/api/worker-app/usage/event", token: readToken(WORKER_TOKEN_KEYS) };
    }
    return { url: "/api/v2/usage/event", token: readToken(ADMIN_TOKEN_KEYS) };
  }

  function track(featureId, source) {
    const fid = String(featureId || "").trim().toLowerCase().slice(0, 64);
    const src = String(source || "unknown").trim().slice(0, 32);
    if (!fid) return;

    const key = `${src}:${fid}`;
    const now = Date.now();
    if (lastSent.has(key) && now - lastSent.get(key) < THROTTLE_MS) return;
    lastSent.set(key, now);

    const { url, token } = resolveEndpoint(src);
    if (!token) return;

    global.fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        Accept: "application/json",
      },
      body: JSON.stringify({ feature_id: fid, source: src }),
      keepalive: true,
    }).catch(() => {});
  }

  global.BaupassUsage = { track };
})(typeof window !== "undefined" ? window : globalThis);
