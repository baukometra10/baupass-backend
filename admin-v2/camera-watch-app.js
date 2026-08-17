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
    selectedCamId: "",
    escFilter: "open",
    activeTab: "lage",
  };
  let map = null;
  let mapLayer = null;
  let refreshTimer = null;

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

  async function openCameraSnapshot(reveal) {
    if (!state.selectedCamId) return;
    const path = `/api/integrations/cameras/${encodeURIComponent(state.selectedCamId)}/snapshot?format=jpeg${
      reveal ? "&reveal=1" : ""
    }`;
    try {
      const res = await fetch(qs(path), { headers: headers(), credentials: "include" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const code = data.error || res.statusText;
        setMsg(
          "cwCamMsg",
          code === "face_reveal_forbidden"
            ? "Nur die Geschäftsführung darf Gesichter anzeigen."
            : data.message || code || "Kein Snapshot",
          false,
        );
        return;
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      setMsg(
        "cwCamMsg",
        reveal ? "Unverpixeltes Bild geöffnet (auditiert)." : "Unscharfes Live-Bild geöffnet.",
        true,
      );
    } catch (err) {
      setMsg("cwCamMsg", err.message || "Snapshot fehlgeschlagen", false);
    }
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
    if (form.elements.namedItem("faceBlurEnabled")) {
      payload.faceBlurEnabled = get("faceBlurEnabled") !== "0";
      payload.faceBlurLegalAck =
        get("faceBlurLegalAck") === "1" ||
        get("faceBlurLegalAck") === "true" ||
        get("faceBlurLegalAck") === "on";
    }
    if (form.elements.namedItem("faceMatchEnabled")) {
      payload.faceMatchEnabled = get("faceMatchEnabled") === "1";
      payload.faceMatchLegalAck =
        get("faceMatchLegalAck") === "1" ||
        get("faceMatchLegalAck") === "true" ||
        get("faceMatchLegalAck") === "on";
    }
    if (form.elements.namedItem("locationTrackingEnabled")) {
      payload.locationTrackingEnabled = get("locationTrackingEnabled") !== "0";
      payload.locationTrackingLegalAck =
        get("locationTrackingLegalAck") === "1" ||
        get("locationTrackingLegalAck") === "true" ||
        get("locationTrackingLegalAck") === "on";
    }
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
    set("faceBlurEnabled", data.faceBlurEnabled === false || data.faceBlurEnabled === 0 ? "0" : "1");
    set("faceMatchEnabled", data.faceMatchEnabled === true || data.faceMatchEnabled === 1 ? "1" : "0");
    set(
      "locationTrackingEnabled",
      data.locationTrackingEnabled === false || data.locationTrackingEnabled === 0 ? "0" : "1"
    );
    const ack = form.elements.namedItem("faceBlurLegalAck");
    if (ack && "checked" in ack) ack.checked = false;
    const matchAck = form.elements.namedItem("faceMatchLegalAck");
    if (matchAck && "checked" in matchAck) matchAck.checked = false;
    const gpsAck = form.elements.namedItem("locationTrackingLegalAck");
    if (gpsAck && "checked" in gpsAck) gpsAck.checked = Boolean(data.locationTrackingLegalAck);
    syncFaceBlurAck();
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
    set("name", data.name || "");
    set("location", data.location || "");
    set("zoneName", data.zoneName || "");
    set("minConfidence", data.minConfidence ?? 0);
    set(
      "zoneCriticalOnlyAfterHours",
      data.zoneCriticalOnlyAfterHours === true || data.zoneCriticalOnlyAfterHours === 1 ? "1" : "0",
    );
    set("rtspUrl", data.rtspUrl || "");
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

  function switchTab(tab) {
    state.activeTab = tab;
    document.querySelectorAll(".cw-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-tab") === tab);
    });
    document.querySelectorAll(".cw-pane").forEach((pane) => {
      pane.classList.toggle("active", pane.id === `pane-${tab}`);
    });
    if (tab === "lage") setTimeout(() => map?.invalidateSize(), 80);
  }

  function openEscalations() {
    switchTab("esc");
  }

  function setKpi(id, value, { warn = false, ok = false, pulse = false } = {}) {
    const el = $(id);
    if (!el) return;
    const strong = el.querySelector("strong");
    if (strong) strong.textContent = value;
    el.classList.toggle("warn", !!warn);
    el.classList.toggle("ok", !!ok);
    el.classList.toggle("pulse", !!pulse);
  }

  function renderKpis() {
    const w = state.watch || {};
    const cams = state.cameras || [];
    const online = cams.filter((c) => c.online).length;
    const openEsc = (state.escalations || []).filter((e) =>
      ["open", "pending_second_ack"].includes(String(e.status || "")),
    );
    const maxStage = openEsc.reduce((m, e) => Math.max(m, Number(e.chainStage || 0)), 0);
    const quiet = w.quietHours?.enabled ? `${w.quietHours.start || "22:00"}–${w.quietHours.end || "06:00"}` : "Aus";
    const mode = w.afterHours ? "Nachtschicht" : w.enabled === false ? "Aus" : "Bereit";
    setKpi("kpiWatch", mode, { warn: !!w.afterHours, ok: !w.afterHours && w.enabled !== false, pulse: !!w.afterHours });
    setKpi("kpiCams", `${online}/${cams.length}`, { ok: online > 0, warn: cams.length > 0 && online === 0 });
    setKpi("kpiEsc", String(openEsc.length), { warn: openEsc.length > 0 });
    setKpi("kpiChain", String(maxStage), { warn: maxStage >= 1 });
    setKpi("kpiQuiet", quiet);
    setKpi("kpiSites", String((state.sites || []).length));

    const badge = $("cwWatchBadge");
    if (badge) {
      badge.textContent = w.afterHours ? "Nachtschicht aktiv" : w.enabled === false ? "Watch aus" : "Watch bereit";
      badge.className = `cw-badge${w.afterHours ? "" : w.enabled === false ? " off" : " ok"}`;
    }
    const summary = $("cwLageSummary");
    if (summary) {
      summary.textContent = [
        `${w.workStart || "06:00"}–${w.workEnd || "18:00"} (${w.timezone || "Europe/Berlin"})`,
        `Kette nach ${w.escalateAfterMinutes || 15} Min`,
        openEsc.length ? `${openEsc.length} offen` : "keine offenen Escalations",
        w.faceBlurEnabled === false ? "Gesichter klar" : "Gesichter unscharf",
        w.faceMatchEnabled ? "Gesichtsabgleich an" : "kein Gesichtsabgleich",
        w.locationTrackingBlocked ? "GPS gesperrt (Betriebsrat)" : w.locationTrackingEnabled === false ? "GPS aus" : "GPS mit Einwilligung",
        "kein Auto-Notruf",
      ].join(" · ");
    }
  }

  function syncFaceBlurAck() {
    const form = $("cwCompanyForm");
    const sel = form?.elements?.namedItem("faceBlurEnabled");
    const wrap = $("cwFaceBlurAckWrap");
    const off = sel && String(sel.value) === "0";
    if (wrap) wrap.hidden = !off;
    const matchSel = form?.elements?.namedItem("faceMatchEnabled");
    const matchWrap = $("cwFaceMatchAckWrap");
    const matchOn = matchSel && String(matchSel.value) === "1";
    if (matchWrap) matchWrap.hidden = !matchOn;
    if (matchSel && !off && matchOn) matchSel.value = "0";
    if (matchWrap && (!off || !matchOn)) matchWrap.hidden = !(off && matchOn);
  }

  function renderPrivacyAndWebhookHelp() {
    const notice = String(state.watch?.privacyNotice || "").trim();
    const banner = $("cwPrivacyBanner");
    const text = $("cwPrivacyText");
    if (banner && text) {
      banner.hidden = !notice;
      text.textContent = notice || "";
    }
    const blurOn = state.watch?.faceBlurEnabled !== false;
    const fb = $("cwFaceBlurBanner");
    const title = $("cwFaceBlurTitle");
    const body = $("cwFaceBlurText");
    if (fb) {
      fb.classList.toggle("off", !blurOn);
      if (title) title.textContent = blurOn ? "Gesichtsunschärfe aktiv" : "Gesichtsunschärfe aus";
      if (body) {
        body.textContent = blurOn
          ? "Live-Bilder und Eskalationen zeigen Gesichter unscharf. Nur die Geschäftsführung kann die Unschärfe vorübergehend aufheben."
          : "Unverpixelte Gesichter sind für diese Firma eingeschaltet. Jede Anzeige und Abschaltung wird auditiert.";
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
      "  -H 'X-WorkPass-Signature: sha256=<hmac-hex>' \\",
      `  -d '{"type":"camera.test_webhook","test":true,"autoDial":false,"companyId":"${companyId}"}'`,
    ].join("\n");
  }

  function filteredEscalations() {
    const all = state.escalations || [];
    if (state.escFilter === "all") return all;
    if (state.escFilter === "test") return all.filter((e) => e.test);
    return all.filter((e) => ["open", "pending_second_ack"].includes(String(e.status || "")));
  }

  function escListHtml(items, emptyText) {
    if (!items.length) return `<li class="muted">${escapeHtml(emptyText)}</li>`;
    return items
      .map((e) => {
        const active = e.id === state.selectedEscId ? " active" : "";
        const urgent =
          ["open", "pending_second_ack"].includes(String(e.status || "")) && Number(e.chainStage || 0) >= 1
            ? " urgent"
            : "";
        const dual = e.dualAckRequired ? ` · Ack ${e.ackCount || 0}/2` : "";
        const sla = e.slaLabel ? escapeHtml(e.slaLabel) : `Stufe ${escapeHtml(String(e.chainStage ?? 0))}`;
        const testTag = e.test ? " · TEST" : "";
        return `<li class="${active}${urgent}" data-esc="${escapeAttr(e.id)}">
          <strong>${escapeHtml(e.cameraName || e.cameraId || "Kamera")}</strong>
          <span class="muted"> · ${escapeHtml(e.status || "")}${dual}${testTag}</span><br/>
          <span class="muted">${sla}</span><br/>
          <span class="muted">${escapeHtml(e.policeName || e.policePhone || "Polizei-Vorschlag")}</span>
        </li>`;
      })
      .join("");
  }

  function wireEscClicks(listEl) {
    listEl?.querySelectorAll("[data-esc]").forEach((li) => {
      li.addEventListener("click", () => {
        openEscalations();
        loadEscalationDetail(li.getAttribute("data-esc"));
      });
    });
  }

  function renderEscalations() {
    const items = filteredEscalations();
    const list = $("cwEscList");
    if (list) {
      list.innerHTML = escListHtml(items, "Keine Escalations für diesen Filter.");
      wireEscClicks(list);
    }
    const lage = $("cwLageEscList");
    if (lage) {
      const open = (state.escalations || [])
        .filter((e) => ["open", "pending_second_ack"].includes(String(e.status || "")))
        .slice(0, 5);
      lage.innerHTML = escListHtml(open, "Keine offenen Escalations — Lage ruhig.");
      wireEscClicks(lage);
    }
  }

  function renderCameras() {
    const list = $("cwCamList");
    if (!list) return;
    const cams = state.cameras || [];
    if (!cams.length) {
      list.innerHTML = `<li class="muted">Keine Kameras registriert — unter Geräte / Bridge importieren.</li>`;
      return;
    }
    list.innerHTML = cams
      .map((c) => {
        const active = c.id === state.selectedCamId ? " active" : "";
        const openForCam = (state.escalations || []).filter(
          (e) =>
            e.cameraId === c.id && ["open", "pending_second_ack"].includes(String(e.status || "")),
        ).length;
        return `<li class="${active}" data-cam="${escapeAttr(c.id)}">
          <div class="cw-cam-row">
            <div><span class="cw-dot ${c.online ? "on" : ""}"></span><strong>${escapeHtml(c.name || c.id)}</strong>
              <div class="muted" style="font-size:0.72rem">${escapeHtml(c.location || "—")} · ${escapeHtml(c.zoneName || "keine Zone")}</div>
            </div>
            <div class="muted" style="font-size:0.75rem">${c.online ? "online" : "offline"}</div>
            <div class="muted" style="font-size:0.75rem">${c.latitude != null ? Number(c.latitude).toFixed(4) : "—"}</div>
            <div class="muted" style="font-size:0.75rem">${openForCam ? `${openForCam} Esc` : "—"}</div>
            <div class="muted" style="font-size:0.75rem">${c.hasSnapshot ? "Snapshot" : ""}</div>
          </div>
        </li>`;
      })
      .join("");
    list.querySelectorAll("[data-cam]").forEach((li) => {
      li.addEventListener("click", () => selectCamera(li.getAttribute("data-cam")));
    });
  }

  function selectCamera(id) {
    state.selectedCamId = id;
    const cam = (state.cameras || []).find((c) => c.id === id);
    const edit = $("cwCamEdit");
    if (edit) edit.hidden = !cam;
    if (cam) fillForm($("cwCamForm"), cam);
    renderCameras();
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

  function ensureMap() {
    if (!window.L || map) return map;
    const el = $("cwMap");
    if (!el) return null;
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
      }).bindPopup(
        `<strong>${escapeHtml(cam.name || cam.id)}</strong><br/>${escapeHtml(cam.zoneName || cam.location || "")}`,
      );
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
          openEscalations();
          loadEscalationDetail(e.id);
        });
      });
      mapLayer.addLayer(m);
      points.push([Number(lat), Number(lng)]);
    }

    if (points.length) map.fitBounds(points, { padding: [24, 24], maxZoom: 14 });
    setTimeout(() => map?.invalidateSize(), 80);
  }

  async function loadEscalationDetail(id) {
    state.selectedEscId = id;
    renderEscalations();
    const detail = $("cwDetail");
    const empty = $("cwDetailEmpty");
    if (!detail) return;
    detail.hidden = false;
    if (empty) empty.hidden = true;
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
      if (slaEl) slaEl.textContent = e.slaLabel || `offen · Stufe ${e.chainStage ?? 0}`;
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
      if (e.hasClearSnapshot && !e.facesRevealed) {
        parts.push(`<p class="muted">Gesichter unscharf — Geschäftsführung kann sie anzeigen.</p>`);
      }
      if (e.facesRevealed) {
        parts.push(`<p class="muted">Gesichter angezeigt — Vorgang auditiert.</p>`);
      }
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
      }
      setMsg("cwDetailMsg", "", true);
    } catch (err) {
      setMsg("cwDetailMsg", err.message || "Fehler", false);
    }
  }

  async function refresh({ silent = false } = {}) {
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
    const devices = $("cwDevicesLink");
    if (devices) {
      // camera-watch runs inside the admin-v2 iframe. /index.html forbids framing
      // (X-Frame-Options DENY), so Chrome shows "Verbindung abgelehnt" unless we
      // break out of the iframe.
      devices.href = `/index.html?company_id=${encodeURIComponent(companyId)}#devices`;
      devices.target = "_top";
      devices.rel = "noopener";
    }
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
      renderKpis();
      $("cwStatusLine").textContent = `Aktualisiert ${new Date().toLocaleTimeString()} · ${state.escalations.length} Esc · ${state.cameras.length} Kameras`;
      renderSites();
      renderOverrides();
      renderEscalations();
      renderCameras();
      renderMap();
      if (!silent) {
        const deepEsc = params.get("escalation") || "";
        const prefer = state.selectedEscId || deepEsc;
        if (prefer) {
          if (deepEsc) openEscalations();
          await loadEscalationDetail(prefer);
        }
      } else if (state.selectedEscId) {
        await loadEscalationDetail(state.selectedEscId);
      }
    } catch (err) {
      $("cwStatusLine").textContent = err.message || "Laden fehlgeschlagen";
    }
  }

  function setupAutoRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = null;
    const box = $("cwAutoRefresh");
    if (!box?.checked) return;
    refreshTimer = setInterval(() => refresh({ silent: true }), 30000);
  }

  function bind() {
    document.querySelectorAll(".cw-tab").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.getAttribute("data-tab") || "lage"));
    });
    document.querySelectorAll(".cw-esc-filter").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.escFilter = btn.getAttribute("data-filter") || "open";
        document.querySelectorAll(".cw-esc-filter").forEach((b) => b.classList.toggle("active", b === btn));
        renderEscalations();
      });
    });
    $("cwRefresh")?.addEventListener("click", () => refresh());
    $("cwAutoRefresh")?.addEventListener("change", setupAutoRefresh);

    $("cwSaveCompany")?.addEventListener("click", async () => {
      try {
        const payload = formToPayload($("cwCompanyForm"));
        delete payload.siteKey;
        delete payload.siteName;
        await api("/api/integrations/cameras/watch", { method: "PUT", body: JSON.stringify(payload) });
        setMsg("cwSettingsMsg", "Gespeichert.", true);
        setMsg("cwCompanyMsg", "Gespeichert.", true);
        await refresh();
      } catch (err) {
        const code = err.data?.error || err.message || "";
        const msg =
          code === "face_blur_legal_ack_required"
            ? "Zum Abschalten der Gesichtsunschärfe muss die Geschäftsführung die rechtliche Bestätigung setzen."
            : err.data?.message || err.message || "Fehler";
        setMsg("cwSettingsMsg", msg, false);
        setMsg("cwCompanyMsg", msg, false);
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

    $("cwSaveCam")?.addEventListener("click", async () => {
      if (!state.selectedCamId) return;
      const form = $("cwCamForm");
      const fd = new FormData(form);
      const get = (k) => String(fd.get(k) || "").trim();
      try {
        await api(`/api/integrations/cameras/${encodeURIComponent(state.selectedCamId)}`, {
          method: "PUT",
          body: JSON.stringify({
            name: get("name"),
            location: get("location"),
            zoneName: get("zoneName"),
            minConfidence: Number(get("minConfidence") || 0),
            zoneCriticalOnlyAfterHours: get("zoneCriticalOnlyAfterHours") === "1",
            latitude: get("latitude") === "" ? null : Number(get("latitude")),
            longitude: get("longitude") === "" ? null : Number(get("longitude")),
            rtspUrl: get("rtspUrl"),
          }),
        });
        setMsg("cwCamMsg", "Kamera gespeichert.", true);
        await refresh({ silent: true });
        selectCamera(state.selectedCamId);
      } catch (err) {
        setMsg("cwCamMsg", err.message || "Fehler", false);
      }
    });

    $("cwOnvifProbe")?.addEventListener("click", async () => {
      const form = $("cwCamForm");
      if (!form) return;
      const fd = new FormData(form);
      const get = (k) => String(fd.get(k) || "").trim();
      const host = get("onvifHost");
      if (!host) {
        setMsg("cwCamMsg", "ONVIF-Host fehlt.", false);
        return;
      }
      setMsg("cwCamMsg", "ONVIF-Probe…", true);
      try {
        const data = await api("/api/integrations/cameras/onvif-probe", {
          method: "POST",
          body: JSON.stringify({
            host,
            username: get("onvifUser"),
            password: get("onvifPassword"),
          }),
        });
        if (data.rtspUrl) {
          const rtsp = form.elements.namedItem("rtspUrl");
          if (rtsp) rtsp.value = data.rtspUrl;
          setMsg("cwCamMsg", "RTSP-URL aus ONVIF übernommen. Speichern nicht vergessen.", true);
        } else {
          setMsg(
            "cwCamMsg",
            data.manufacturer
              ? `ONVIF erreichbar (${data.manufacturer}), aber keine RTSP-URI.`
              : "ONVIF erreichbar, keine Stream-URI.",
            true,
          );
        }
      } catch (err) {
        setMsg("cwCamMsg", err.message || "ONVIF-Probe fehlgeschlagen", false);
      }
    });

    $("cwCamSnapshot")?.addEventListener("click", () => {
      void openCameraSnapshot(false);
    });
    $("cwCamReveal")?.addEventListener("click", () => {
      void openCameraSnapshot(true);
    });
    $("cwRevealFaces")?.addEventListener("click", async () => {
      if (!state.selectedEscId) return;
      setMsg("cwDetailMsg", "Lade unverpixeltes Bild…", true);
      try {
        const data = await api(
          `/api/integrations/cameras/escalations/${encodeURIComponent(state.selectedEscId)}?media=1&reveal=1`,
        );
        const e = data.escalation || {};
        const media = $("cwMedia");
        const parts = [];
        const snap = mediaSrc(e.snapshotBase64, "image/jpeg");
        if (snap) parts.push(`<img alt="Snapshot" src="${snap}" />`);
        const clip = mediaSrc(e.clipBase64, "video/mp4");
        if (clip) parts.push(`<video controls src="${clip}"></video>`);
        if (!parts.length) parts.push(`<p class="muted">Kein Snapshot/Clip gespeichert.</p>`);
        if (e.facesRevealed) parts.push(`<p class="muted">Gesichter angezeigt — Vorgang auditiert.</p>`);
        if (media) media.innerHTML = parts.join("");
        setMsg("cwDetailMsg", "Gesichter angezeigt (auditiert).", true);
      } catch (err) {
        const code = err.data?.error || err.message || "";
        setMsg(
          "cwDetailMsg",
          code === "face_reveal_forbidden"
            ? "Nur die Geschäftsführung darf Gesichter anzeigen."
            : err.message || "Fehler",
          false,
        );
      }
    });
    $("cwFaceBlurEnabled")?.addEventListener("change", () => syncFaceBlurAck());
    $("cwFaceMatchEnabled")?.addEventListener("change", () => syncFaceBlurAck());

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
        await refresh({ silent: true });
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
        await refresh({ silent: true });
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
        if (data.id) {
          openEscalations();
          await loadEscalationDetail(data.id);
        }
      } catch (err) {
        setMsg("cwCompanyMsg", err.message || "Test-Alarm fehlgeschlagen", false);
      }
    });

    async function runTestWebhook() {
      try {
        const payload = formToPayload($("cwCompanyForm"));
        if (!String(payload.securityWebhookUrl || "").startsWith("http")) {
          setMsg(
            "cwCompanyMsg",
            "Bitte zuerst Security-Webhook (Firma) mit https://… unter Einstellungen speichern.",
            false,
          );
          switchTab("settings");
          return;
        }
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
            : data.message || data.error || "Webhook fehlgeschlagen",
          !!data.ok,
        );
      } catch (err) {
        setMsg("cwCompanyMsg", err.message || "Test-Webhook fehlgeschlagen", false);
      }
    }
    $("cwTestWebhook")?.addEventListener("click", () => {
      void runTestWebhook();
    });
    $("cwTestWebhookInline")?.addEventListener("click", () => {
      void runTestWebhook();
    });
    $("cwWebhookPresetTeams")?.addEventListener("click", () => {
      const hint = $("cwWebhookWizardHint");
      if (hint) {
        hint.textContent =
          "Teams: Kanal → … → Connectoren → Incoming Webhook → URL hier einfügen → Speichern → Test.";
      }
      $("cwCompanyForm")?.querySelector('[name="securityWebhookUrl"]')?.focus();
    });
    $("cwWebhookPresetSlack")?.addEventListener("click", () => {
      const hint = $("cwWebhookWizardHint");
      if (hint) {
        hint.textContent =
          "Slack: Apps → Incoming Webhooks → Add to Slack → URL hier einfügen → Speichern → Test.";
      }
      $("cwCompanyForm")?.querySelector('[name="securityWebhookUrl"]')?.focus();
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

  if (navigator.serviceWorker) {
    navigator.serviceWorker.addEventListener("message", (event) => {
      if (event?.data?.type !== "NAVIGATE_ADMIN_CAMERA" || !event.data.url) return;
      try {
        const target = new URL(event.data.url, location.origin);
        const esc = target.searchParams.get("escalation") || "";
        if (esc) {
          state.selectedEscId = esc;
          switchTab("esc");
          openEscalations?.();
        }
        refresh();
      } catch (_e) {
        /* ignore */
      }
    });
  }

  bind();
  setupAutoRefresh();
  if (params.get("escalation")) switchTab("esc");
  else if ((location.hash || "").replace("#", "") === "settings") switchTab("settings");
  refresh();
})();
