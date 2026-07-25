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

  let state = { watch: null, sites: [], escalations: [], selectedEscId: "", selectedSiteKey: "" };

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
      headers: { ...headers(options.headers || {}), ...(options.body ? { "Content-Type": "application/json" } : {}) },
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
    return {
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
      siteName: get("siteName") || "",
      siteKey: get("siteKey") || "",
    };
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
    set("siteKey", data.siteKey || "");
    set("siteName", data.siteName || "");
  }

  function setMsg(id, text, ok = true) {
    const el = $(id);
    if (!el) return;
    el.textContent = text || "";
    el.className = ok ? "ok" : "err";
  }

  function renderSites() {
    const list = $("cwSiteList");
    if (!list) return;
    if (!state.sites.length) {
      list.innerHTML = `<li class="muted">Noch keine Standorte — Firmen-Defaults gelten für alle Kameras.</li>`;
      return;
    }
    list.innerHTML = state.sites
      .map((s) => {
        const active = s.siteKey === state.selectedSiteKey ? " active" : "";
        return `<li class="${active}" data-site="${escapeAttr(s.siteKey)}">
          <strong>${escapeHtml(s.siteName || s.siteKey)}</strong>
          <span class="muted"> · ${escapeHtml(s.workStart || "")}–${escapeHtml(s.workEnd || "")}
          · ${escapeHtml(s.city || s.country || "")}</span>
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
        return `<li class="${active}" data-esc="${escapeAttr(e.id)}">
          <strong>${escapeHtml(e.cameraName || e.cameraId || "Kamera")}</strong>
          <span class="muted"> · ${escapeHtml(e.status || "")} · ${escapeHtml(e.createdAt || "")}</span><br/>
          <span class="muted">${escapeHtml(e.policeName || e.policePhone || "Polizei-Vorschlag")}</span>
        </li>`;
      })
      .join("");
    list.querySelectorAll("[data-esc]").forEach((li) => {
      li.addEventListener("click", () => loadEscalationDetail(li.getAttribute("data-esc")));
    });
  }

  function mediaSrc(b64, mime) {
    const raw = String(b64 || "").trim();
    if (!raw) return "";
    if (raw.startsWith("data:")) return raw;
    return `data:${mime};base64,${raw}`;
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
        e.falsePositive ? "Fehlalarm" : "",
      ]
        .filter(Boolean)
        .join(" · ");
      const media = $("cwMedia");
      const parts = [];
      const snap = mediaSrc(e.snapshotBase64, "image/jpeg");
      if (snap) parts.push(`<img alt="Snapshot" src="${snap}" />`);
      const clip = mediaSrc(e.clipBase64, "video/mp4");
      if (clip) parts.push(`<video controls src="${clip}"></video>`);
      if (!parts.length) parts.push(`<p class="muted">Kein Snapshot/Clip gespeichert.</p>`);
      media.innerHTML = parts.join("");
      const policeBits = [
        e.policeName,
        e.policeAddress,
        e.policePhone,
        e.policeCity,
        e.policeCountry,
      ].filter(Boolean);
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
      $("cwStatusLine").textContent = "company_id fehlt (Firma wählen).";
      return;
    }
    const back = $("cwBack");
    if (back) back.href = `/admin-v2/index.html${companyId ? `?company_id=${encodeURIComponent(companyId)}` : ""}`;
    try {
      const data = await api("/api/integrations/cameras/watch");
      state.watch = data.watch || {};
      state.sites = Array.isArray(data.sites) ? data.sites : [];
      state.escalations = Array.isArray(data.escalations) ? data.escalations : [];
      fillForm($("cwCompanyForm"), state.watch);
      const badge = $("cwWatchBadge");
      if (badge) {
        badge.textContent = state.watch.afterHours
          ? "Nachtschicht aktiv"
          : state.watch.enabled === false
            ? "Watch aus"
            : "Watch bereit";
      }
      $("cwStatusLine").textContent = `${state.watch.workStart || "06:00"}–${state.watch.workEnd || "18:00"} · ${state.watch.timezone || "Europe/Berlin"} · ${state.escalations.length} Eskalation(en)`;
      renderSites();
      renderEscalations();
      const deepEsc = params.get("escalation") || "";
      const prefer = state.selectedEscId || deepEsc;
      if (prefer) {
        await loadEscalationDetail(prefer);
      } else if (state.escalations[0]?.id) {
        await loadEscalationDetail(state.escalations[0].id);
      }
    } catch (err) {
      $("cwStatusLine").textContent = err.message || "Laden fehlgeschlagen";
    }
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

  function bind() {
    $("cwSaveCompany")?.addEventListener("click", async () => {
      try {
        const payload = formToPayload($("cwCompanyForm"));
        delete payload.siteKey;
        delete payload.siteName;
        const data = await api("/api/integrations/cameras/watch", {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        state.watch = data.watch || state.watch;
        state.sites = Array.isArray(data.sites) ? data.sites : state.sites;
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
      if (!key) return;
      if (!confirm(`Standort „${key}“ löschen?`)) return;
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

    $("cwAck")?.addEventListener("click", async () => {
      if (!state.selectedEscId) return;
      try {
        await api(`/api/integrations/cameras/escalations/${encodeURIComponent(state.selectedEscId)}/ack`, {
          method: "POST",
          body: JSON.stringify({ securityNotified: true }),
        });
        setMsg("cwDetailMsg", "Als bearbeitet markiert.", true);
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
          {
            method: "POST",
            body: JSON.stringify({ note }),
          },
        );
        setMsg("cwDetailMsg", "Als Fehlalarm markiert — Schwellen werden angepasst.", true);
        await refresh();
      } catch (err) {
        setMsg("cwDetailMsg", err.message || "Fehler", false);
      }
    });
  }

  bind();
  refresh();
})();
