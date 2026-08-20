/**
 * Lohn-Zentrale — standalone accounting hub (Betrieb).
 * Keeps external SSO launch separate; hosts requests + studio entry.
 */
const WP = window.WorkPassStorage;
const TOKEN_KEY = WP?.KEYS?.ADMIN_TOKEN || "workpass-admin-token";
const USER_KEY = WP?.KEYS?.ADMIN_USER || "workpass-admin-user";
const COMPANY_KEY = WP?.KEYS?.ADMIN_COMPANY || "workpass-admin-company";
const CONTROL_TOKEN_KEY = WP?.KEYS?.SESSION_TOKEN || "workpass-session-token";

const qs = new URLSearchParams(location.search);
const state = {
  companyId: String(qs.get("company_id") || "").trim(),
  focus: String(qs.get("focus") || "").trim().toLowerCase(),
  messages: [],
  alerts: [],
  periodRequests: [],
  payslipBatches: [],
  payslipCount: 0,
  busy: false,
};

function $(id) {
  return document.getElementById(id);
}

function wpGet(key) {
  try {
    return WP?.get?.(key) ?? localStorage.getItem(key) ?? sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function wpSet(key, value) {
  try {
    if (WP?.set) WP.set(key, value);
    else localStorage.setItem(key, String(value ?? ""));
  } catch {
    /* ignore */
  }
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/'/g, "&#39;");
}

function getToken() {
  return String(WP?.readSessionToken?.() || wpGet(TOKEN_KEY) || wpGet(CONTROL_TOKEN_KEY) || "").trim();
}

function getUser() {
  try {
    return JSON.parse(wpGet(USER_KEY) || "{}") || {};
  } catch {
    return {};
  }
}

function companyQuery() {
  const cid = state.companyId || wpGet(COMPANY_KEY) || "";
  return cid ? `?company_id=${encodeURIComponent(cid)}` : "";
}

function setStatus(msg, kind = "") {
  const el = $("accStatus");
  if (!el) return;
  el.textContent = msg || "";
  el.classList.toggle("is-error", kind === "error");
  el.classList.toggle("is-ok", kind === "ok");
}

function apiBase() {
  return "";
}

async function api(path, options = {}) {
  const token = getToken();
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const res = await fetch(`${apiBase()}${path}`, { ...options, headers, cache: "no-store" });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = {};
  }
  if (!res.ok) {
    const err = new Error(data.message || data.error || res.statusText || "request_failed");
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function withTimeout(promise, timeoutMs, fallback) {
  let timer;
  const timed = new Promise((resolve) => {
    timer = setTimeout(() => resolve(fallback), Math.max(500, Number(timeoutMs) || 8000));
  });
  return Promise.race([Promise.resolve(promise).finally(() => clearTimeout(timer)), timed]);
}

function apiSoft(path, fallback = null, timeoutMs = 8000, options = {}) {
  return withTimeout(api(path, options).catch(() => fallback), timeoutMs, fallback);
}

function canAccessLohn() {
  const role = String(getUser()?.role || "").toLowerCase();
  if (role === "office" || role === "turnstile") return false;
  if (!role) return Boolean(getToken());
  return role === "superadmin" || role === "company-admin";
}

function lohnContractsUrl(companyId, workerId, fields, hint) {
  const params = new URLSearchParams();
  params.set("focus", "payroll");
  if (companyId) params.set("company_id", companyId);
  if (workerId) params.set("worker_id", String(workerId));
  if (Array.isArray(fields) && fields.length) params.set("missing", fields.join(","));
  if (hint) params.set("hint", String(hint).slice(0, 180));
  return `/admin-v2/contracts.html?${params.toString()}`;
}

function renderChips(fields) {
  const list = Array.isArray(fields) ? fields.filter(Boolean) : [];
  if (!list.length) return "";
  return `<div class="acc-chips">${list
    .slice(0, 8)
    .map((f) => `<span class="acc-chip">${escapeHtml(f)}</span>`)
    .join("")}</div>`;
}

function setBadge(id, n) {
  const el = $(id);
  if (!el) return;
  const count = Number(n) || 0;
  el.textContent = String(count);
  el.classList.toggle("is-zero", count <= 0);
}

function paintProcess() {
  const host = $("accProcessBody");
  if (!host) return;
  const parts = [];
  const cid = state.companyId;

  if (state.payslipBatches.length) {
    parts.push(`
      <article class="acc-card is-alert">
        <div class="acc-card-title">Lohnabrechnungen zur Prüfung</div>
        <div class="acc-card-body">${escapeHtml(`${state.payslipCount} PDF(s) warten auf Prüfung und Versand an die Mitarbeiter-App.`)}</div>
        <div class="acc-card-actions">
          <button type="button" class="primary" data-acc-action="open-studio">Jetzt prüfen &amp; senden</button>
        </div>
      </article>`);
  }

  for (const a of state.alerts.slice(0, 40)) {
    const id = String(a.id || "");
    const wid = String(a.workerId || a.employeeId || "").trim();
    const fields = a.missingFields || a.missing_fields || [];
    const name =
      String(a.workerDisplayName || "").trim()
      || [a.workerFirstName, a.workerLastName].filter(Boolean).join(" ").trim()
      || a.workerName
      || wid
      || "—";
    const href = lohnContractsUrl(a.companyId || cid, wid, fields, a.message || "");
    parts.push(`
      <article class="acc-card is-alert" data-acc-alert="${escapeAttr(id)}">
        <div class="acc-card-title"><strong>${escapeHtml(name)}</strong>${wid && name !== wid ? ` <span class="muted">(${escapeHtml(wid)})</span>` : ""}</div>
        <div class="acc-card-body">${escapeHtml(a.message || "Fehlende Stammdaten")}</div>
        ${renderChips(fields)}
        <div class="acc-card-actions">
          <a class="primary" href="${escapeAttr(href)}" target="_blank" rel="noopener">Stammdaten öffnen</a>
          <button type="button" data-acc-action="dismiss-alert" data-id="${escapeAttr(id)}">Erledigt</button>
        </div>
      </article>`);
  }

  for (const m of state.messages.slice(0, 40)) {
    const id = String(m.id || "");
    const fields = m.missingFields || m.missing_fields || [];
    const subject = m.subject || m.kind || "WorkPass Lohn";
    const bodyText = String(m.body || "").trim();
    const wid = String(m.workerId || "").trim();
    const name =
      String(m.workerDisplayName || "").trim()
      || [m.workerFirstName, m.workerLastName].filter(Boolean).join(" ").trim();
    const href = lohnContractsUrl(m.companyId || cid, m.workerId, fields, `${subject} ${bodyText}`);
    parts.push(`
      <article class="acc-card" data-acc-msg="${escapeAttr(id)}">
        <div class="acc-card-title">${escapeHtml(subject)}</div>
        ${name || wid ? `<div class="acc-card-body"><strong>${escapeHtml(name || "—")}</strong>${wid ? ` <span class="muted">(${escapeHtml(wid)})</span>` : ""}</div>` : ""}
        ${bodyText ? `<div class="acc-card-body">${escapeHtml(bodyText.slice(0, 280))}</div>` : ""}
        ${renderChips(fields)}
        <div class="acc-card-meta">${escapeHtml([m.period, name || wid].filter(Boolean).join(" · ") || "—")}</div>
        <div class="acc-card-actions">
          <a class="primary" href="${escapeAttr(href)}" target="_blank" rel="noopener" data-acc-action="open-msg" data-id="${escapeAttr(id)}">Bearbeiten</a>
          <button type="button" data-acc-action="ack-msg" data-id="${escapeAttr(id)}">Erledigt</button>
        </div>
      </article>`);
  }

  if (!parts.length) {
    host.innerHTML = `<div class="acc-empty"><strong>Alles erledigt</strong>Keine offenen Anfragen aus der Buchhaltung.</div>`;
  } else {
    host.innerHTML = `<div class="acc-cards">${parts.join("")}</div>`;
  }

  const processCount = state.messages.length + state.alerts.length + (state.payslipCount ? 1 : 0);
  setBadge("badgeProcess", processCount);
}

function paintConfirm() {
  const host = $("accConfirmBody");
  if (!host) return;
  const parts = [];
  for (const req of state.periodRequests.slice(0, 40)) {
    const id = String(req.id || "");
    const period = String(req.period || "—");
    parts.push(`
      <article class="acc-card is-alert" data-acc-period="${escapeAttr(id)}">
        <div class="acc-card-title">Perioden-Übergabe</div>
        <div class="acc-card-body">Buchhaltung bittet um Daten für <strong>${escapeHtml(period)}</strong>.</div>
        <div class="acc-card-meta">${escapeHtml(period)}</div>
        <div class="acc-card-actions">
          <button type="button" class="primary" data-acc-action="period-confirm" data-id="${escapeAttr(id)}">Freigeben</button>
          <button type="button" class="danger" data-acc-action="period-reject" data-id="${escapeAttr(id)}">Ablehnen</button>
        </div>
      </article>`);
  }
  if (!parts.length) {
    host.innerHTML = `<div class="acc-empty"><strong>Keine Bestätigungen offen</strong>Perioden-Anfragen erscheinen hier, sobald die Buchhaltung sie anfordert.</div>`;
  } else {
    host.innerHTML = `<div class="acc-cards">${parts.join("")}</div>`;
  }
  setBadge("badgeConfirm", state.periodRequests.length);
}

function paintStudioHint() {
  setBadge("badgeStudio", state.payslipCount);
  const hint = $("accStudioHint");
  if (!hint || !$("accStudioFrameWrap")?.classList.contains("hidden")) return;
  if (state.payslipCount > 0) {
    hint.innerHTML = `<strong>${escapeHtml(String(state.payslipCount))} Abrechnung(en) offen</strong>Öffne das Studio, um zu prüfen und an die Mitarbeiter-App zu senden.`;
  } else {
    hint.innerHTML = `<strong>Studio bereit</strong>Keine offenen Abrechnungen. Du kannst das Studio trotzdem öffnen, um das Archiv zu prüfen.`;
  }
}

async function loadHub() {
  const cid = state.companyId;
  if (!cid && String(getUser()?.role || "").toLowerCase() === "superadmin") {
    setStatus("Bitte zuerst eine Firma in Betrieb wählen.", "error");
    $("accProcessBody").innerHTML = `<div class="acc-empty"><strong>Firma wählen</strong>Öffne Betrieb, wähle eine Firma, dann kehre zur Lohn-Zentrale zurück.</div>`;
    $("accConfirmBody").innerHTML = "";
    return;
  }
  setStatus("Lade Anfragen…");
  const cq = cid ? `?company_id=${encodeURIComponent(cid)}` : "";
  const sync = "1";
  const msgUrl = `/api/payroll/accounting/messages?sync=${sync}${cid ? `&company_id=${encodeURIComponent(cid)}` : ""}`;
  const [msgRes, alertRes, periodRes, payslipRes] = await Promise.all([
    apiSoft(msgUrl, { messages: [] }, 8000),
    apiSoft(`/api/payroll/accounting/data-alerts${cq}`, { alerts: [] }, 5000),
    apiSoft(
      `/api/payroll/accounting/period-requests?status=pending_confirmation${cid ? `&company_id=${encodeURIComponent(cid)}` : ""}`,
      { requests: [] },
      5000,
    ),
    apiSoft(`/api/payroll/statements/pending${cq}`, { batches: [] }, 6000),
  ]);
  state.messages = Array.isArray(msgRes?.messages) ? msgRes.messages : [];
  state.alerts = Array.isArray(alertRes?.alerts) ? alertRes.alerts : [];
  state.periodRequests = Array.isArray(periodRes?.requests) ? periodRes.requests : [];
  state.payslipBatches = Array.isArray(payslipRes?.batches) ? payslipRes.batches : [];
  state.payslipCount = state.payslipBatches.reduce(
    (n, b) => n + (Array.isArray(b.statements) ? b.statements.length : Number(b.statement_count || 0)),
    0,
  );
  paintProcess();
  paintConfirm();
  paintStudioHint();
  setStatus(`Aktualisiert · ${new Date().toLocaleTimeString()}`, "ok");
}

function studioFrameUrl() {
  const params = new URLSearchParams();
  params.set("embed", "1");
  params.set("autostudio", "1");
  params.set("v", "20260820accHub1");
  if (state.companyId) params.set("company_id", state.companyId);
  const lang = qs.get("lang");
  if (lang) params.set("lang", lang);
  const batchId = qs.get("batch_id") || qs.get("batchId");
  const statementId = qs.get("statement_id") || qs.get("statementId");
  if (batchId) params.set("batch_id", batchId);
  if (statementId) params.set("statement_id", statementId);
  return `/admin-v2/index.html?${params.toString()}`;
}

function openStudio(fullscreen = true) {
  const wrap = $("accStudioFrameWrap");
  const frame = $("accStudioFrame");
  const hint = $("accStudioHint");
  const exitBtn = $("accExitStudioBtn");
  if (!wrap || !frame) return;
  hint?.classList.add("hidden");
  wrap.classList.remove("hidden");
  exitBtn?.classList.remove("hidden");
  if (fullscreen) document.body.classList.add("acc-studio-focus");
  const next = studioFrameUrl();
  if (frame.getAttribute("src") !== next) {
    frame.src = next;
  }
  location.hash = "accStudio";
  $("jumpStudio")?.classList.add("is-active");
}

function exitStudio() {
  document.body.classList.remove("acc-studio-focus");
  $("accExitStudioBtn")?.classList.add("hidden");
  $("accStudioFrameWrap")?.classList.add("hidden");
  $("accStudioHint")?.classList.remove("hidden");
  const frame = $("accStudioFrame");
  if (frame) frame.src = "about:blank";
  paintStudioHint();
  if (state.focus === "studio") {
    const u = new URL(location.href);
    u.searchParams.delete("focus");
    history.replaceState({}, "", u.pathname + u.search + "#accStudio");
  }
}

async function openExternalAccounting() {
  if (!canAccessLohn()) {
    setStatus("Keine Berechtigung.", "error");
    return;
  }
  const cid = state.companyId;
  if (!cid) {
    setStatus("Bitte Firma wählen.", "error");
    return;
  }
  try {
    const res = await api(`/api/payroll/accounting/launch?company_id=${encodeURIComponent(cid)}`);
    if (!res?.ok || !res.url) {
      setStatus(res?.message || "Buchhaltung nicht erreichbar", "error");
      return;
    }
    const win = window.open(String(res.url), "_blank");
    if (!win) window.location.assign(String(res.url));
  } catch (e) {
    setStatus(e?.message || "Buchhaltung nicht erreichbar", "error");
  }
}

async function handleAction(ev) {
  const el = ev.target?.closest?.("[data-acc-action]");
  if (!el || state.busy) return;
  const action = el.getAttribute("data-acc-action");
  const id = String(el.getAttribute("data-id") || "").trim();

  if (action === "open-studio") {
    openStudio(true);
    return;
  }

  if (action === "open-msg" && id) {
    ev.preventDefault();
    const href = el.getAttribute("href");
    document.querySelector(`[data-acc-msg="${CSS.escape(id)}"]`)?.remove();
    try {
      await api(`/api/payroll/accounting/messages/${encodeURIComponent(id)}/open`, {
        method: "POST",
        body: "{}",
      });
    } catch {
      /* still open */
    }
    if (href) window.open(href, "_blank", "noopener");
    void loadHub();
    return;
  }

  if (action === "ack-msg" && id) {
    state.busy = true;
    el.disabled = true;
    try {
      await api(`/api/payroll/accounting/messages/${encodeURIComponent(id)}/open`, {
        method: "POST",
        body: "{}",
      });
      document.querySelector(`[data-acc-msg="${CSS.escape(id)}"]`)?.remove();
    } catch (e) {
      setStatus(e?.message || "Fehler", "error");
    } finally {
      state.busy = false;
      void loadHub();
    }
    return;
  }

  if (action === "dismiss-alert" && id) {
    state.busy = true;
    el.disabled = true;
    try {
      await api(`/api/payroll/accounting/data-alerts/${encodeURIComponent(id)}/dismiss`, {
        method: "POST",
        body: "{}",
      });
      document.querySelector(`[data-acc-alert="${CSS.escape(id)}"]`)?.remove();
    } catch (e) {
      setStatus(e?.message || "Fehler", "error");
    } finally {
      state.busy = false;
      void loadHub();
    }
    return;
  }

  if ((action === "period-confirm" || action === "period-reject") && id) {
    state.busy = true;
    el.disabled = true;
    const path =
      action === "period-confirm"
        ? `/api/payroll/accounting/period-requests/${encodeURIComponent(id)}/confirm`
        : `/api/payroll/accounting/period-requests/${encodeURIComponent(id)}/reject`;
    try {
      await api(path, {
        method: "POST",
        body: action === "period-reject" ? JSON.stringify({ reason: "" }) : "{}",
      });
      document.querySelector(`[data-acc-period="${CSS.escape(id)}"]`)?.remove();
      setStatus(action === "period-confirm" ? "Freigegeben." : "Abgelehnt.", "ok");
    } catch (e) {
      setStatus(e?.message || "Fehler", "error");
    } finally {
      state.busy = false;
      void loadHub();
    }
  }
}

async function adoptSession() {
  let token = getToken();
  if (!token) {
    // Wait briefly for parent postMessage in embed contexts
    token = await new Promise((resolve) => {
      const timer = window.setTimeout(() => {
        window.removeEventListener("message", onMsg);
        resolve(getToken());
      }, 900);
      function onMsg(event) {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type !== "baupass-sync-token" || !event.data.token) return;
        window.clearTimeout(timer);
        window.removeEventListener("message", onMsg);
        wpSet(TOKEN_KEY, event.data.token);
        if (WP?.persistSessionToken) WP.persistSessionToken(event.data.token);
        if (event.data.companyId) {
          state.companyId = String(event.data.companyId);
          wpSet(COMPANY_KEY, state.companyId);
        }
        resolve(String(event.data.token));
      }
      window.addEventListener("message", onMsg);
    });
  }
  if (!token) throw new Error("Bitte über Betrieb anmelden.");

  try {
    const data = await api("/api/v2/auth/session");
    if (data?.user) wpSet(USER_KEY, JSON.stringify(data.user));
    if (!state.companyId) {
      const u = data?.user || getUser();
      state.companyId = String(
        u.preview_company_id || u.company_id || wpGet(COMPANY_KEY) || "",
      ).trim();
    }
    if (state.companyId) wpSet(COMPANY_KEY, state.companyId);
  } catch (e) {
    if (e?.status === 401 || e?.status === 403) throw new Error("Sitzung abgelaufen — bitte neu anmelden.");
    throw e;
  }
}

function wireUi() {
  $("accRefreshBtn")?.addEventListener("click", () => loadHub().catch((e) => setStatus(e.message, "error")));
  $("accOpenExternalBtn")?.addEventListener("click", () => openExternalAccounting());
  $("accOpenStudioBtn")?.addEventListener("click", () => openStudio(true));
  $("accExitStudioBtn")?.addEventListener("click", () => exitStudio());
  document.addEventListener("click", (ev) => {
    handleAction(ev).catch((e) => setStatus(e?.message || "Fehler", "error"));
  });

  const back = $("accBackBetrieb");
  if (back && state.companyId) {
    back.href = `/admin-v2/index.html?company_id=${encodeURIComponent(state.companyId)}`;
  }

  window.addEventListener("message", (ev) => {
    if (ev.origin !== window.location.origin) return;
    if (ev.data?.type === "workpass-accounting-studio-close") {
      try {
        exitStudio();
      } catch {
        /* ignore */
      }
    }
  });

  const jumps = [
    ["jumpProcess", "accProcess"],
    ["jumpConfirm", "accConfirm"],
    ["jumpStudio", "accStudio"],
  ];
  jumps.forEach(([jid, sid]) => {
    $(jid)?.addEventListener("click", (ev) => {
      document.querySelectorAll(".acc-jump a").forEach((a) => a.classList.remove("is-active"));
      ev.currentTarget.classList.add("is-active");
      if (sid === "accStudio" && (ev.metaKey || ev.ctrlKey || state.focus === "studio")) {
        /* keep default hash nav */
      }
    });
  });
}

async function boot() {
  const bootEl = $("accBoot");
  const appEl = $("accApp");
  try {
    await adoptSession();
    if (!canAccessLohn()) {
      throw new Error("Keine Berechtigung für die Lohn-Zentrale.");
    }
    bootEl?.classList.add("hidden");
    appEl?.classList.remove("hidden");
    wireUi();
    await loadHub();
    if (state.focus === "studio" || location.hash === "#accStudio") {
      openStudio(true);
    } else if (state.focus === "confirm" || location.hash === "#accConfirm") {
      $("accConfirm")?.scrollIntoView({ behavior: "smooth", block: "start" });
      $("jumpConfirm")?.classList.add("is-active");
    } else if (state.focus === "process" || location.hash === "#accProcess") {
      $("accProcess")?.scrollIntoView({ behavior: "smooth", block: "start" });
      $("jumpProcess")?.classList.add("is-active");
    }
  } catch (e) {
    const msg = e?.message || "Laden fehlgeschlagen";
    if ($("accBootMsg")) $("accBootMsg").textContent = msg;
    setStatus(msg, "error");
    bootEl?.classList.remove("hidden");
    appEl?.classList.add("hidden");
  }
}

boot();
