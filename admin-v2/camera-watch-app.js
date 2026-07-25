(() => {
  const WP = window.WorkPassStorage;
  const wpGet = (key) => (WP?.getItem ? WP.getItem(key) : localStorage.getItem(key));
  const params = new URLSearchParams(location.search);
  const companyId =
    params.get("company_id") || wpGet(WP?.KEYS?.ADMIN_COMPANY || "workpass-admin-company") || "";
  const token =
    wpGet(WP?.KEYS?.ADMIN_TOKEN || "workpass-admin-token") ||
    wpGet(WP?.KEYS?.SESSION_TOKEN || "workpass-session-token") ||
    "";

  let state = {
    watch: null,
    sites: [],
    overrides: [],
    escalations: [],
    cameras: [],
    selectedEscId: "",
    selectedSiteKey: "",
  };
  let map = null;
  let mapLayer = null;

  const $ = (id) => document.getElementById(id);

  function qs(path) {
    if (!companyId) return path;
    const sep = path.includes("?") ? "&" : "?";
    return `${path}${sep}company_id=${encodeURIComponent(companyId)}`;
  }

  function headers(extra = {}) {
    return {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...extra,
    };
  }

  async function api(path, options = {}) {
    const res = await fetch(qs(path), {
      ...options,
      headers: {
        ...headers(options.headers || {}),
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      },
      credentials: "include",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.error || data.message || res.statusText || "request_failed");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  function formToPayload(form) {
    const fd = new FormData(form);
    const get = (k) => String(fd.get(k) || "").trim();
    const enabledRaw = get("enabled");
    const lat = get("latitude");
    const lng = get("longitude");
    const dual = get("requireDualAck");
    const payload = {
      enabled: enabledRaw === "" ? true : enabledRaw === "1" || enabledRaw === "true",
      timezone: get("timezone") || "Europe/Berlin",
      workStart: get("workStart") || "06:00",
      workEnd: get("workEnd") || "18:00",
      workDays: get("workDays") || "1,2,3,4,5",
      country: get("country") || "DE",
      city: get("city") || "",
      latitude: lat === "" ? null : Number(lat),
      longitude: lng === "" ? null : Number(lng),
      securityWebhookUrl: get("securityWebhookUrl") || "",
      webhookSecret: get("webhookSecret") || "",
      webhookRetryMax: Number(get("webhookRetryMax") || 3) || 3,
      evidenceRetentionDays: Number(get("evidenceRetentionDays") || 30) || 30,
      privacyNotice: get("privacyNotice") || "",
      quietHours: {
        enabled: get("quietEnabled") === "1" || get("quietEnabled") === "true",
        start: get("quietStart") || "22:00",
        end: get("quietEnd") || "06:00",
        channels: ["sms"],
      },
      siteName: get("siteName") || "",
      siteKey: get("siteKey") || "",
      escalateAfterMinutes: Number(get("escalateAfterMinutes") || 15) || 15,
      escalateSecondContact: get("escalateSecondContact") || "",
      requireDualAck: dual === "" ? true : dual === "1" || dual === "true",
      notifyRules: {
        sms: get("notifySms") || "critical",
        push: get("notifyPush") || "high",
        email: get("notifyEmail") || "immediate",
      },
    };
    return payload;
  }

  function fillForm(form, data) {
    if (!form || !data) return;
    const set = (name, value) => {
      const el = form.elements.namedItem(name);
      if (!el) return;
      el.value = value == null ? "" : String(value);
    };
    set("enabled", data.enabled === false || data.enabled === 0 ? "0" : "1");
    set("timezone", data.timezone || "Europe/Berlin");
    set("workStart", data.workStart || "06:00");
    set("workEnd", data.workEnd || "18:00");
    set("workDays", data.workDays || "1,2,3,4,5");
    set("country", data.country || "DE");
    set("city", data.city || "");
    set("latitude", data.latitude ?? "");
    set("longitude", data.longitude ?? "");
    set("securityWebhookUrl", data.securityWebhookUrl || "");
    set("webhookSecret", data.webhookSecret || "");
    set("webhookRetryMax", data.webhookRetryMax ?? 3);
    set("evidenceRetentionDays", data.evidenceRetentionDays ?? 30);
    set("privacyNotice", data.privacyNotice || "");
    const qh = data.quietHours || {};
    set("quietEnabled", qh.enabled ? "1" : "0");
    set("quietStart", qh.start || "22:00");
    set("quietEnd", qh.end || "06:00");
    set("siteKey", data.siteKey || "");
    set("siteName", data.siteName || "");
    set("escalateAfterMinutes", data.escalateAfterMinutes ?? 15);
    set("escalateSecondContact", data.escalateSecondContact || "");
    set("requireDualAck", data.requireDualAck === false || data.requireDualAck === 0 ? "0" : "1");
    const rules = data.notifyRules || {};
    set("notifySms", rules.sms || "critical");
    set("notifyPush", rules.push || "high");
    set("notifyEmail", rules.email || "immediate");
  }

  function renderPrivacyAndWebhookHelp() {
    const notice = String(state.watch?.privacyNotice || "").trim();
    const banner = $("cwPrivacyBanner");
    const text = $("cwPrivacyText");
    if (banner && text) {
      if (notice) {
        banner.hidden = false;
        text.textContent = notice;
      } else {
        banner.hidden = true;
        text.textContent = "";
      }
    }
    const curl = $("cwWebhookCurl");
    if (!curl) return;
    const url = state.watch?.securityWebhookUrl || "https://hooks.example.com/services/…";
    curl.textContent = [
      "# Beispiel (Test-Webhook)",
      `curl -X POST '${url}' \\`,
      "  -H 'Content-Type: application/json' \\",
      "  -H 'X-WorkPass-Event: camera.test_webhook' \\",
      "  -H 'X-WorkPass-Delivery-Id: cwd-example' \\",
      "  -H 'X-WorkPass-Signature: sha256=<hmac-hex>' \\",
      `  -d '{"type":"camera.test_webhook","test":true,"autoDial":false,"companyId":"${companyId}"}'`,
      "",
      "# In dieser UI: URL + optional Secret speichern → „Test-Webhook“",
    ].join("\n");
  }

  function setMsg(id, text, ok = true) {
    const el = $(id);
    if (!el) return;
    el.textContent = text || "";
    el.className = ok ? "ok" : "err";
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replaceAll("'", "&#39;");
  }

  function mediaSrc(b64, mime) {
    const raw = String(b64 || "").trim();
    if (!raw) return "";
    if (raw.startsWith("data:")) return raw;
    return `data:${mime};base64,${raw}`;
  }

  function renderSites() {
    const list = $("cwSiteList");
    if (!list) return;
    if (!state.sites.length) {
      list.innerHTML = `<li class="muted">Noch keine Standorte — Firmen-Defaults gelten.</li>`;
      return;
    }
    list.innerHTML = state.sites
      .map((s) => {
        const active = s.siteKey === state.selectedSiteKey ? " active" : "";
        return `<li class="${active}" data-site="${escapeAttr(s.siteKey)}">
          <strong>${escapeHtml(s.siteName || s.siteKey)}</strong>
          <span class="muted"> · ${escapeHtml(s.workStart || "")}–${escapeHtml(s.workEnd || "")}</span>
        </li>`;
      })
      .join("");
    list.querySelectorAll("[data-site]").forEach((li) => {
      li.addEventListener("click", () => {
        const key = li.getAttribute("data-site");
        const site = state.sites.find((x) => x.siteKey === key);
        state.selectedSiteKey = key;
        fillForm($("cwSiteForm"), site);
        renderSites();
      });
    });
  }

  function renderOverrides() {
    const list = $("cwOverrideList");
    if (!list) return;
    if (!state.overrides.length) {
      list.innerHTML = `<li class="muted">Keine Overrides.</li>`;
      return;
    }
    list.innerHTML = state.overrides
      .map(
        (o) => `<li data-odate="${escapeAttr(o.overrideDate)}" data-osite="${escapeAttr(o.siteKey || "")}">
          <strong>${escapeHtml(o.overrideDate)}</strong> · ${escapeHtml(o.kind)}
          <span class="muted">${o.siteKey ? ` · ${escapeHtml(o.siteKey)}` : " · Firma"}${o.note ? ` · ${escapeHtml(o.note)}` : ""}</span>
        </li>`,
      )
      .join("");
    list.querySelectorAll("li[data-odate]").forEach((li) => {
      li.addEventListener("click", async () => {
        if (!confirm("Override löschen?")) return;
        try {
          const date = li.getAttribute("data-odate");
          const site = li.getAttribute("data-osite") || "";
          await api(
            `/api/integrations/cameras/watch/overrides?override_date=${encodeURIComponent(date)}&site_key=${encodeURIComponent(site)}`,
            { method: "DELETE" },
          );
          await refresh();
        } catch (err) {
          setMsg("cwCompanyMsg", err.message || "Fehler", false);
        }
      });
    });
  }

  function renderEscalations() {
    const list = $("cwEscList");
    if (!list) return;
    if (!state.escalations.length) {
      list.innerHTML = `<li class="muted">Keine offenen Eskalationen.</li>`;
      return;
    }
    list.innerHTML = state.escalations
      .map((e) => {
        const active = e.id === state.selectedEscId ? " active" : "";
        const dual = e.dualAckRequired
          ? ` · Ack ${e.ackCount || 0}/2`
          : "";
        const sla = e.slaLabel
          ? escapeHtml(e.slaLabel)
          : `Stufe ${escapeHtml(String(e.chainStage ?? 0))}`;
        const testTag = e.test ? " · TEST" : "";
        return `<li class="${active}" data-esc="${escapeAttr(e.id)}">
          <strong>${escapeHtml(e.cameraName || e.cameraId || "Kamera")}</strong>
          <span class="muted"> · ${escapeHtml(e.status || "")}${dual}${testTag}</span><br/>
          <span class="muted">${sla}</span><br/>
          <span class="muted">${escapeHtml(e.policeName || e.policePhone || "Polizei-Vorschlag")}</span>
        </li>`;
      })
      .join("");
    list.querySelectorAll("[data-esc]").forEach((li) => {
      li.addEventListener("click", () => loadEscalationDetail(li.getAttribute("data-esc")));
    });
  }

  function ensureMap() {
    if (!window.L || map) return map;
    map = L.map("cwMap").setView([51.16, 10.45], 5);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 18,
    }).addTo(map);
    mapLayer = L.layerGroup().addTo(map);
    return map;
  }

  function renderMap() {
    if (!ensureMap() || !mapLayer) return;
    mapLayer.clearLayers();
    const points = [];
    const siteByKey = Object.fromEntries((state.sites || []).map((s) => [s.siteKey, s]));
    const firmLat = state.watch?.latitude;
    const firmLng = state.watch?.longitude;

    for (const cam of state.cameras || []) {
      let lat = cam.latitude ?? cam.lat;
      let lng = cam.longitude ?? cam.lng;
      if ((lat == null || lng == null) && cam.location && siteByKey[cam.location]) {
        lat = siteByKey[cam.location].latitude;
        lng = siteByKey[cam.location].longitude;
      }
      if (lat == null || lng == null) {
        lat = firmLat;
        lng = firmLng;
      }
      if (lat == null || lng == null) continue;
      const color = cam.online ? "#34d399" : "#94a3b8";
      const m = L.circleMarker([Number(lat), Number(lng)], {
        radius: 7,
        color,
        fillColor: color,
        fillOpacity: 0.85,
      }).bindPopup(`<strong>${escapeHtml(cam.name || cam.id)}</strong><br/>${escapeHtml(cam.location || "")}`);
      mapLayer.addLayer(m);
      points.push([Number(lat), Number(lng)]);
    }

    for (const e of state.escalations || []) {
      if (!["open", "pending_second_ack"].includes(String(e.status || ""))) continue;
      const cam = (state.cameras || []).find((c) => c.id === e.cameraId);
      let lat = cam?.latitude ?? siteByKey[e.siteKey || ""]?.latitude ?? firmLat;
      let lng = cam?.longitude ?? siteByKey[e.siteKey || ""]?.longitude ?? firmLng;
      if (lat == null || lng == null) continue;
      const m = L.circleMarker([Number(lat), Number(lng)], {
        radius: 10,
        color: "#f59e0b",
        fillColor: "#f59e0b",
        fillOpacity: 0.9,
      }).bindPopup(
        `<strong>Eskalation</strong><br/>${escapeHtml(e.cameraId || "")}<br/><button type="button" data-open-esc="${escapeAttr(e.id)}">Öffnen</button>`,
      );
      m.on("popupopen", () => {
        document.querySelector(`[data-open-esc="${CSS.escape(e.id)}"]`)?.addEventListener("click", () => {
          loadEscalationDetail(e.id);
        });
      });
      mapLayer.addLayer(m);
      points.push([Number(lat), Number(lng)]);
    }

    if (points.length) {
      map.fitBounds(points, { padding: [24, 24], maxZoom: 14 });
    }
    setTimeout(() => map.invalidateSize(), 80);
  }

  async function loadEscalationDetail(id) {
    state.selectedEscId = id;
    renderEscalations();
    const detail = $("cwDetail");
    if (!detail) return;
    detail.hidden = false;
    setMsg("cwDetailMsg", "Lade…", true);
    try {
      const data = await api(`/api/integrations/cameras/escalations/${encodeURIComponent(id)}?media=1`);
      const e = data.escalation || {};
      $("cwDetailTitle").textContent = e.cameraName || e.cameraId || "Eskalation";
      $("cwDetailMeta").textContent = [
        e.status,
        e.eventType,
        e.siteKey || e.location,
        e.createdAt,
        e.test ? "TEST" : "",
        e.falsePositive ? "Fehlalarm" : "",
      ]
        .filter(Boolean)
        .join(" · ");
      const slaEl = $("cwDetailSla");
      if (slaEl) {
        slaEl.textContent = e.slaLabel || `offen · Stufe ${e.chainStage ?? 0}`;
      }
      const need = e.dualAckRequired ? 2 : 1;
      const have = Number(e.ackCount || 0);
      $("cwAckBadge").textContent = e.dualAckRequired
        ? `Zwei-Augen: ${have}/${need} Bestätigungen${have >= need ? " — fertig" : " — zweite Person nötig"}`
        : "";
      const media = $("cwMedia");
      const parts = [];
      const snap = mediaSrc(e.snapshotBase64, "image/jpeg");
      if (snap) parts.push(`<img alt="Snapshot" src="${snap}" />`);
      const clip = mediaSrc(e.clipBase64, "video/mp4");
      if (clip) parts.push(`<video controls src="${clip}"></video>`);
      if (!parts.length) parts.push(`<p class="muted">Kein Snapshot/Clip gespeichert.</p>`);
      media.innerHTML = parts.join("");
      const policeBits = [e.policeName, e.policeAddress, e.policePhone, e.policeCity, e.policeCountry].filter(Boolean);
      $("cwPolice").textContent = policeBits.join(" · ") || "Kein Stationsvorschlag — Notrufnummer lokal prüfen.";
      const hist = (e.history || [])
        .map((h) => `${escapeHtml(h.createdAt || "")}: ${escapeHtml(h.type || "")}${h.note ? ` — ${escapeHtml(h.note)}` : ""}`)
        .join("<br/>");
      $("cwHistory").innerHTML = hist || "<span class='muted'>Noch keine Verlaufseinträge.</span>";
      const camLink = $("cwCamLink");
      if (camLink && e.cameraId) {
        camLink.href = qs(`/api/integrations/cameras/${encodeURIComponent(e.cameraId)}/snapshot?format=jpeg`);
        camLink.hidden = false;
      }
      const zip = $("cwExportZip");
      const pdf = $("cwExportPdf");
      if (zip) zip.href = qs(`/api/integrations/cameras/escalations/${encodeURIComponent(id)}/export?format=zip`);
      if (pdf) pdf.href = qs(`/api/integrations/cameras/escalations/${encodeURIComponent(id)}/export?format=pdf`);
      setMsg("cwDetailMsg", "", true);
    } catch (err) {
      setMsg("cwDetailMsg", err.message || "Fehler", false);
    }
  }

  async function refresh() {
    if (!token) {
      $("cwStatusLine").textContent = "Bitte zuerst im Admin einloggen.";
      return;
    }
    if (!companyId) {
      $("cwStatusLine").textContent = "company_id fehlt — Firma wählen (Preview / URL).";
      return;
    }
    const back = $("cwBack");
    if (back) back.href = `/admin-v2/index.html?company_id=${encodeURIComponent(companyId)}`;
    try {
      const [data, cams] = await Promise.all([
        api("/api/integrations/cameras/watch"),
        api("/api/integrations/cameras").catch(() => ({ cameras: [] })),
      ]);
      state.watch = data.watch || {};
      state.sites = Array.isArray(data.sites) ? data.sites : [];
      state.overrides = Array.isArray(data.overrides) ? data.overrides : [];
      state.escalations = Array.isArray(data.escalations) ? data.escalations : [];
      state.cameras = Array.isArray(cams.cameras) ? cams.cameras : [];
      fillForm($("cwCompanyForm"), state.watch);
      renderPrivacyAndWebhookHelp();
      const badge = $("cwWatchBadge");
      if (badge) {
        badge.textContent = state.watch.afterHours
          ? "Nachtschicht aktiv"
          : state.watch.enabled === false
            ? "Watch aus"
            : "Watch bereit";
      }
      $("cwStatusLine").textContent = `${state.watch.workStart || "06:00"}–${state.watch.workEnd || "18:00"} · Kette ${state.watch.escalateAfterMinutes || 15} Min · ${state.escalations.length} Eskalation(en)`;
      renderSites();
      renderOverrides();
      renderEscalations();
      renderMap();
      const deepEsc = params.get("escalation") || "";
      const prefer = state.selectedEscId || deepEsc;
      if (prefer) await loadEscalationDetail(prefer);
      else if (state.escalations[0]?.id) await loadEscalationDetail(state.escalations[0].id);
    } catch (err) {
      $("cwStatusLine").textContent = err.message || "Laden fehlgeschlagen";
    }
  }

  function bind() {
    $("cwSaveCompany")?.addEventListener("click", async () => {
      try {
        const payload = formToPayload($("cwCompanyForm"));
        delete payload.siteKey;
        delete payload.siteName;
        await api("/api/integrations/cameras/watch", { method: "PUT", body: JSON.stringify(payload) });
        setMsg("cwCompanyMsg", "Gespeichert.", true);
        await refresh();
      } catch (err) {
        setMsg("cwCompanyMsg", err.message || "Fehler", false);
      }
    });

    $("cwSaveSite")?.addEventListener("click", async () => {
      try {
        const payload = formToPayload($("cwSiteForm"));
        const key = payload.siteKey || state.selectedSiteKey;
        if (!key) {
          setMsg("cwCompanyMsg", "Site-Key erforderlich", false);
          return;
        }
        await api(`/api/integrations/cameras/watch/sites/${encodeURIComponent(key)}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        state.selectedSiteKey = key;
        setMsg("cwCompanyMsg", "Standort gespeichert.", true);
        await refresh();
      } catch (err) {
        setMsg("cwCompanyMsg", err.message || "Fehler", false);
      }
    });

    $("cwDeleteSite")?.addEventListener("click", async () => {
      const key = String($("cwSiteForm")?.elements?.namedItem("siteKey")?.value || state.selectedSiteKey || "").trim();
      if (!key || !confirm(`Standort „${key}“ löschen?`)) return;
      try {
        await api(`/api/integrations/cameras/watch/sites/${encodeURIComponent(key)}`, { method: "DELETE" });
        state.selectedSiteKey = "";
        fillForm($("cwSiteForm"), {});
        setMsg("cwCompanyMsg", "Standort gelöscht.", true);
        await refresh();
      } catch (err) {
        setMsg("cwCompanyMsg", err.message || "Fehler", false);
      }
    });

    $("cwSaveOverride")?.addEventListener("click", async () => {
      const form = $("cwOverrideForm");
      const fd = new FormData(form);
      const get = (k) => String(fd.get(k) || "").trim();
      try {
        await api("/api/integrations/cameras/watch/overrides", {
          method: "PUT",
          body: JSON.stringify({
            overrideDate: get("overrideDate"),
            kind: get("kind") || "holiday",
            siteKey: get("siteKey") || "",
            note: get("note") || "",
            workStart: get("workStart") || "",
            workEnd: get("workEnd") || "",
          }),
        });
        setMsg("cwCompanyMsg", "Override gespeichert.", true);
        await refresh();
      } catch (err) {
        setMsg("cwCompanyMsg", err.message || "Fehler", false);
      }
    });

    $("cwAck")?.addEventListener("click", async () => {
      if (!state.selectedEscId) return;
      try {
        const data = await api(
          `/api/integrations/cameras/escalations/${encodeURIComponent(state.selectedEscId)}/ack`,
          { method: "POST", body: JSON.stringify({ securityNotified: true }) },
        );
        const e = data.escalation || {};
        if (e.status === "pending_second_ack" || (e.dualAckRequired && (e.ackCount || 0) < 2)) {
          setMsg("cwDetailMsg", "Erste Bestätigung gespeichert — zweite Person nötig.", true);
        } else {
          setMsg("cwDetailMsg", "Als bearbeitet markiert.", true);
        }
        await refresh();
      } catch (err) {
        setMsg("cwDetailMsg", err.message || "Fehler", false);
      }
    });

    $("cwFalse")?.addEventListener("click", async () => {
      if (!state.selectedEscId) return;
      const note = prompt("Kurznotiz zum Fehlalarm (optional):", "") || "";
      try {
        await api(
          `/api/integrations/cameras/escalations/${encodeURIComponent(state.selectedEscId)}/false-positive`,
          { method: "POST", body: JSON.stringify({ note }) },
        );
        setMsg("cwDetailMsg", "Als Fehlalarm markiert.", true);
        await refresh();
      } catch (err) {
        setMsg("cwDetailMsg", err.message || "Fehler", false);
      }
    });

    $("cwTestAlarm")?.addEventListener("click", async () => {
      try {
        const data = await api("/api/integrations/cameras/watch/test-alarm", {
          method: "POST",
          body: JSON.stringify({ severity: "high" }),
        });
        setMsg(
          "cwCompanyMsg",
          data.dryRun
            ? "Dry-Run OK (kein Escalation)."
            : `Test-Alarm erstellt${data.id ? `: ${data.id}` : ""}. Kein Auto-Notruf.`,
          true,
        );
        await refresh();
        if (data.id) await loadEscalationDetail(data.id);
      } catch (err) {
        setMsg("cwCompanyMsg", err.message || "Test-Alarm fehlgeschlagen", false);
      }
    });

    $("cwTestWebhook")?.addEventListener("click", async () => {
      try {
        const payload = formToPayload($("cwCompanyForm"));
        const data = await api("/api/integrations/cameras/watch/test-webhook", {
          method: "POST",
          body: JSON.stringify({
            url: payload.securityWebhookUrl || undefined,
            secret: payload.webhookSecret || undefined,
          }),
        });
        setMsg(
          "cwCompanyMsg",
          data.ok
            ? `Test-Webhook gesendet${data.signed ? " (signiert)" : ""}.`
            : data.error || "Webhook fehlgeschlagen",
          !!data.ok,
        );
      } catch (err) {
        setMsg("cwCompanyMsg", err.message || "Test-Webhook fehlgeschlagen", false);
      }
    });

    $("cwAuditExport")?.addEventListener("click", async () => {
      try {
        const res = await fetch(qs("/api/integrations/cameras/watch/audit-export?format=json"), {
          headers: headers(),
          credentials: "include",
        });
        if (!res.ok) throw new Error("audit_export_failed");
        const blob = await res.blob();
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `camera-watch-audit-${companyId || "export"}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
        setMsg("cwCompanyMsg", "Audit-Export heruntergeladen.", true);
      } catch (err) {
        setMsg("cwCompanyMsg", err.message || "Audit-Export fehlgeschlagen", false);
      }
    });

    // Auth header for export downloads (anchor alone may miss bearer)
    ["cwExportZip", "cwExportPdf"].forEach((id) => {
      $(id)?.addEventListener("click", async (ev) => {
        ev.preventDefault();
        if (!state.selectedEscId) return;
        const fmt = id.includes("Pdf") ? "pdf" : "zip";
        try {
          const res = await fetch(
            qs(`/api/integrations/cameras/escalations/${encodeURIComponent(state.selectedEscId)}/export?format=${fmt}`),
            { headers: headers(), credentials: "include" },
          );
          if (!res.ok) throw new Error("export_failed");
          const blob = await res.blob();
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = `escalation-${state.selectedEscId}.${fmt === "pdf" ? "pdf" : "zip"}`;
          a.click();
          URL.revokeObjectURL(a.href);
        } catch (err) {
          setMsg("cwDetailMsg", err.message || "Export fehlgeschlagen", false);
        }
      });
    });
  }

  bind();
  refresh();
})();
