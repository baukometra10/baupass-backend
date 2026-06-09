/**
 * BauPass — vendor-agnostic signature pad bridge (core registry)
 * Providers register via signature-pad-providers.js
 * @see docs/signature-pad-setup-AR.md
 */
(function initBaupassSignaturePadBridge(global) {
  const providers = [];
  let probeCache = null;
  let probeCacheAt = 0;
  const PROBE_TTL_MS = 15000;

  function registerProvider(spec) {
    if (!spec?.id || typeof spec.probe !== "function" || typeof spec.capture !== "function") {
      throw new Error("signature_pad_provider_invalid");
    }
    providers.push({
      id: String(spec.id),
      labelKey: String(spec.labelKey || spec.id),
      order: Number(spec.order ?? 100),
      probe: spec.probe,
      capture: spec.capture,
    });
    providers.sort((a, b) => a.order - b.order);
  }

  async function probeProviders(force) {
    const now = Date.now();
    if (!force && probeCache && (now - probeCacheAt) < PROBE_TTL_MS) {
      return probeCache.slice();
    }
    const results = [];
    for (const provider of providers) {
      let entry = { id: provider.id, labelKey: provider.labelKey, ok: false, detail: "" };
      try {
        const probe = await provider.probe();
        entry = {
          id: provider.id,
          labelKey: provider.labelKey,
          ok: Boolean(probe?.ok),
          detail: String(probe?.detail || probe?.reason || ""),
          meta: probe?.meta || null,
        };
      } catch (err) {
        entry.detail = String(err?.message || err || "probe_failed");
      }
      results.push(entry);
    }
    probeCache = results;
    probeCacheAt = now;
    return results.slice();
  }

  function getAvailableProviders() {
    return (probeCache || []).filter((p) => p.ok);
  }

  async function captureSignature(options = {}) {
    const mode = String(options.mode || "auto").toLowerCase();
    const preferredId = String(options.providerId || "").trim();
    await probeProviders(true);

    let candidates = providers.filter((p) => {
      const hit = (probeCache || []).find((x) => x.id === p.id);
      return hit?.ok;
    });

    if (preferredId) {
      candidates = candidates.filter((p) => p.id === preferredId);
    } else if (mode === "auto") {
      candidates = candidates.filter((p) => p.id !== "canvas");
    }

    let lastErr = null;
    for (const provider of candidates) {
      try {
        const result = await provider.capture(options);
        if (result?.dataUrl) {
          probeCacheAt = 0;
          return { ...result, provider: result.provider || provider.id };
        }
        lastErr = new Error("signature_empty");
      } catch (err) {
        lastErr = err instanceof Error ? err : new Error(String(err || "capture_failed"));
        if (String(lastErr.message) === "signature_cancelled") throw lastErr;
      }
    }

    if (lastErr) throw lastErr;
    throw new Error("signature_pad_none_available");
  }

  global.BaupassSignaturePad = {
    registerProvider,
    probeProviders,
    getAvailableProviders,
    captureSignature,
    providerIds: () => providers.map((p) => p.id),
  };
})(window);
