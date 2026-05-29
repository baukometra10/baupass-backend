import { applyI18n, getLang, setLang, t } from "./i18n.js";
import { mountGeofenceMap } from "./geofence-map.js";
import { INTEGRATION_WIZARD, buildConnectPayload, renderWizardForm } from "./integrations-wizard.js";

const TOKEN_KEY = "baupass-admin-v2-token";
const USER_KEY = "baupass-admin-v2-user";
const COMPANY_KEY = "baupass-admin-v2-company";
let pendingIntegrationProvider = null;

function getUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "{}");
  } catch {
    return {};
  }
}

function companyQuery() {
  const user = getUser();
  if (user.role !== "superadmin") {
    return "";
  }
  const cid = localStorage.getItem(COMPANY_KEY) || "";
  return cid ? `?company_id=${encodeURIComponent(cid)}` : "";
}

function apiBase() {
  return "";
}

async function api(path, options = {}) {
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${apiBase()}${path}`, { ...options, headers });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { error: "invalid_json" };
  }
  if (!res.ok) {
    const err = new Error(data.message || data.error || res.statusText);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function $(id) {
  return document.getElementById(id);
}

function showLogin() {
  $("loginView").classList.remove("hidden");
  $("dashboardView").classList.add("hidden");
}

function showDashboard() {
  $("loginView").classList.add("hidden");
  $("dashboardView").classList.remove("hidden");
  const user = getUser();
  $("userLine").textContent = `${user.username || ""} · ${user.role || ""}`;
  setupCompanyPicker(user);
}

function setupCompanyPicker(user) {
  const wrap = $("companyPickerWrap");
  const select = $("companyPicker");
  if (user.role !== "superadmin") {
    wrap.classList.add("hidden");
    return;
  }
  wrap.classList.remove("hidden");
  select.onchange = () => {
    localStorage.setItem(COMPANY_KEY, select.value);
    syncEnterpriseFrame();
    startAdminRealtime().catch(() => {});
    refreshActiveTab().catch((e) => alert(e.message));
  };
}

async function loadCompanies() {
  const user = getUser();
  if (user.role !== "superadmin") {
    return;
  }
  const companies = await api("/api/companies");
  const select = $("companyPicker");
  const saved = localStorage.getItem(COMPANY_KEY) || "";
  select.innerHTML = companies
    .map((c) => `<option value="${c.id}">${c.name || c.id}</option>`)
    .join("");
  if (saved && companies.some((c) => c.id === saved)) {
    select.value = saved;
  } else if (companies.length) {
    select.value = companies[0].id;
    localStorage.setItem(COMPANY_KEY, companies[0].id);
  }
}

function statusBadge(ok) {
  return ok
    ? '<span class="badge badge-ok">جاهز</span>'
    : '<span class="badge badge-warn">يحتاج إعداد</span>';
}

function escapeHtml(text) {
  return String(text ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatPushDelivery(res) {
  const d = res?.pushDelivery || res;
  if (!d) return "";
  if (d.delivered || (d.pushSent ?? 0) > 0) {
    const ch = (d.channels || []).join(" + ") || "push";
    return `Push: ${d.pushSent} (${ch})`;
  }
  return d.hint || "Kein Push zugestellt — Token fehlt.";
}

function showActionToast(message, isError) {
  const el = document.getElementById("inboxToast");
  if (!el) {
    alert(message);
    return;
  }
  el.textContent = message;
  el.className = isError ? "inbox-toast err" : "inbox-toast ok";
  el.classList.remove("hidden");
  clearTimeout(showActionToast._t);
  showActionToast._t = setTimeout(() => el.classList.add("hidden"), 4500);
}

let adminRealtimeStop = null;

function companyIdFromQuery() {
  const q = companyQuery();
  return q ? q.replace(/^\?company_id=/, "") : "";
}

function shouldRefreshOnEvent(evt) {
  const t = String(evt?.type || evt?.event_type || "");
  return /inbox|security|leave|access|push|emergency|alert|document/i.test(t);
}

function updateInboxTabBadge(open, critical) {
  const b = $("inboxTabBadge");
  if (!b) return;
  const n = Number(open) || 0;
  const crit = Number(critical) || 0;
  if (n <= 0) {
    b.classList.add("hidden");
    b.classList.remove("critical");
    b.textContent = "";
    return;
  }
  b.classList.remove("hidden");
  const wasCritical = b.classList.contains("critical");
  b.classList.toggle("critical", crit > 0);
  b.textContent = crit > 0 ? `${n}!` : String(n);
  if (crit > 0 && !wasCritical) {
    b.classList.remove("badge-pulse-once");
    void b.offsetWidth;
    b.classList.add("badge-pulse-once");
  }
}

async function refreshInboxBadgeOnly() {
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    updateInboxTabBadge(0, 0);
    return;
  }
  try {
    const data = await api(`/api/inbox/counts${q}`);
    const c = data.counts || {};
    updateInboxTabBadge(c.open, c.critical);
  } catch {
    /* ignore */
  }
}

function scheduleInboxReload() {
  clearTimeout(scheduleInboxReload._t);
  scheduleInboxReload._t = setTimeout(() => {
    const tab = document.querySelector(".tab.active")?.dataset?.tab;
    if (tab === "inbox") loadInbox().catch(() => {});
    else refreshInboxBadgeOnly();
  }, 500);
}

async function startAdminRealtime() {
  if (!window.BauPassOpsRealtime) return;
  if (adminRealtimeStop) {
    adminRealtimeStop();
    adminRealtimeStop = null;
  }
  const cid = companyIdFromQuery();
  if (!cid && getUser().role === "superadmin") return;
  adminRealtimeStop = await window.BauPassOpsRealtime.start({
    companyId: cid,
    feedEl: null,
    onEvent: (evt) => {
      if (!shouldRefreshOnEvent(evt)) return;
      if (evt?.type === "inbox.changed") {
        scheduleInboxReload();
        return;
      }
      refreshInboxBadgeOnly();
      const tab = document.querySelector(".tab.active")?.dataset?.tab || "overview";
      if (tab === "inbox") scheduleInboxReload();
      else if (tab === "overview") {
        clearTimeout(scheduleInboxReload._overviewT);
        scheduleInboxReload._overviewT = setTimeout(() => loadOverview().catch(() => {}), 800);
      } else if (tab === "operations") {
        clearTimeout(scheduleInboxReload._opsT);
        scheduleInboxReload._opsT = setTimeout(() => loadOperations().catch(() => {}), 1200);
      }
    },
  });
}

function syncEnterpriseFrame() {
  const frame = $("enterpriseFrame");
  if (!frame) return;
  const q = companyQuery();
  const cid = q ? q.replace(/^\?company_id=/, "") : "";
  const base = "/enterprise-hub.html?embed=1";
  frame.src = cid ? `${base}&company_id=${encodeURIComponent(cid)}` : base;
}

function switchToTab(tabId) {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.id !== `tab-${tabId}`);
  });
  if (tabId === "enterprise") syncEnterpriseFrame();
}

function renderQuickLinks() {
  const items = [
    { tab: "enterprise", title: "مركز المؤسسة (16 طبقة)", desc: "خريطة كل ما بُني + مساعد AI" },
    { tab: "workers", title: "الموظفون + NFC", desc: "تعيين بطاقة وQR تفعيل التطبيق" },
    { tab: "access", title: "الحضور المباشر", desc: "دخول/خروج وتصدير CSV" },
    { tab: "mobile", title: "تطبيق الموظف", desc: "APK، TestFlight، join.html" },
    { tab: "inbox", title: "Posteingang", desc: "Alerts, Dokumente, Urlaub — handeln statt nur lesen" },
    { tab: "operations", title: "عمليات الموقع", desc: "12 طبقة Physical Operations OS" },
    { tab: "tools", title: "Geofence · أتمتة · تكامل", desc: "SAP، Oracle، M365، قواعد" },
    { tab: "platform", title: "جاهزية المنصة", desc: "Redis، AI، Wallet" },
    { tab: null, title: "لوحة كاملة (Legacy)", desc: "فواتير، أجهزة، إعدادات", href: "/index.html" },
  ];
  $("quickLinks").innerHTML = items
    .map((item) => {
      if (item.href) {
        return `<a class="feature-card" href="${item.href}"><h3>${item.title}</h3><p class="muted small">${item.desc}</p></a>`;
      }
      return `<button type="button" class="feature-card" data-goto-tab="${item.tab}"><h3>${item.title}</h3><p class="muted small">${item.desc}</p></button>`;
    })
    .join("");
  $("quickLinks").querySelectorAll("[data-goto-tab]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      switchToTab(btn.getAttribute("data-goto-tab"));
      await refreshActiveTab();
    });
  });
}

async function loadPlatformBanner() {
  const el = $("platformBanner");
  try {
    const [caps, ready] = await Promise.all([
      api("/api/platform/capabilities").catch(() => null),
      fetch("/api/health/ready").then((r) => r.json()).catch(() => null),
    ]);
    if (!caps && !ready) {
      el.classList.add("hidden");
      return;
    }
    const score = caps?.maturityScore ?? "—";
    const level = caps?.maturityLevel ?? "";
    const dbOk = ready?.checks?.database?.ok;
    const runtime = caps?.dataLayer?.runtime || ready?.checks?.database?.backend || "—";
    el.innerHTML = `
      <div>
        <span class="muted small">نضج المنصة</span>
        <strong>${score}/100</strong>
        <span class="muted small">${level}</span>
      </div>
      <div>قاعدة البيانات: <strong>${runtime}</strong> ${statusBadge(dbOk)}</div>
      <a href="/enterprise-hub.html?v=20260527e" class="btn-link" style="color:#fbbf24;font-weight:700">🏛 مركز المؤسسة (16 طبقة)</a>
      <button type="button" class="btn-link" data-goto-tab="platform">تفاصيل المنصة ←</button>
    `;
    el.classList.remove("hidden");
    el.querySelector("[data-goto-tab]")?.addEventListener("click", async () => {
      switchToTab("platform");
      await loadPlatform();
    });
  } catch {
    el.classList.add("hidden");
  }
}

async function loadPlatform() {
  const panel = $("platformPanel");
  panel.innerHTML = '<p class="muted">جاري التحميل…</p>';
  try {
    const [caps, ready, health, ent, aiSt, wallet, setup, pushSt, mobileDist] = await Promise.all([
      api("/api/platform/capabilities"),
      fetch("/api/health/ready").then((r) => r.json()),
      fetch("/api/health").then((r) => r.json()).catch(() => ({})),
      api("/api/platform/entitlements").catch(() => null),
      api("/api/ai/status").catch(() => ({ configured: false })),
      api("/api/admin/wallet/runtime-status").catch(() => null),
      fetch("/api/platform/setup-status").then((r) => r.json()).catch(() => null),
      api("/api/platform/push/status").catch(() => null),
      api("/api/v2/mobile/distribution").catch(() => null),
    ]);
    const setupLines = (setup?.readyScore?.missing || [])
      .map((m) => `<li class="miss">○ ${m}</li>`)
      .join("");
    const setupOk = setup
      ? `<p>Railway setup: <strong>${setup.readyScore?.percent ?? 0}%</strong></p><ul class="setup-checklist">${setupLines || '<li class="ok">✓ All core keys set</li>'}</ul>`
      : "";
    const steps = (caps.nextSteps || [])
      .map((s) => `<li>${s}</li>`)
      .join("");
    const attendance = caps.attendance || {};
    const attRows = Object.entries(attendance)
      .map(([k, v]) => `<tr><td>${k}</td><td>${statusBadge(!!v)}</td></tr>`)
      .join("");
    panel.innerHTML = `
      <div class="panel-block">${setupOk}</div>
      <div class="panel-block">
        <h3>نضج عالمي <span class="badge badge-ok">${caps.maturityScore}/100</span></h3>
        <p class="muted">${caps.maturityLevel || ""}</p>
        ${steps ? `<ul class="muted small">${steps}</ul>` : ""}
      </div>
      <div class="panel-block">
        <h3>البنية التحتية</h3>
        <p>Runtime: <strong>${caps.dataLayer?.runtime || "—"}</strong> · Redis: ${statusBadge(caps.dataLayer?.redisConfigured)} · Queues: ${statusBadge(caps.dataLayer?.taskQueuesReady)}</p>
        <p class="muted small">Path: ${caps.dataLayer?.sqlitePath || ready.checks?.database?.path || "—"}</p>
        <p>Readiness: ${statusBadge(ready.ready)} · Redis status: ${health.redis?.status || ready.checks?.redis?.status || "—"}</p>
      </div>
      <div class="panel-block">
        <h3>قدرات الحضور (مفعّلة في الكود)</h3>
        <div class="table-wrap"><table><tbody>${attRows}</tbody></table></div>
      </div>
      ${
        ent
          ? `<div class="panel-block">
        <h3>خطتك: ${ent.planMeta?.labelAr || ent.plan}</h3>
        <p>${ent.entitlements?.enabledCount || 0} قدرة مفعّلة · ${ent.entitlements?.lockedCount || 0} تحتاج ترقية · ${ent.entitlements?.coveragePercent || 0}% من المنصة</p>
        <a class="feature-card" href="/enterprise-hub.html" style="display:inline-block;margin-top:0.5rem">فتح مركز المؤسسة (16 طبقة)</a>
        <a class="feature-card" href="/ai-command-center.html" style="display:inline-block;margin-top:0.5rem">KI Command Center (Agents + Tools)</a>
      </div>`
          : ""
      }
      <div class="panel-block">
        <h3>مساعد AI ${aiSt?.configured ? statusBadge(true) : statusBadge(false)}</h3>
        <p class="muted small">يتطلب خطة Enterprise + OPENAI_API_KEY</p>
        <form id="aiQuickForm" class="tool-form">
          <input name="question" placeholder="اسأل: كم موظف على الموقع؟" required />
          <button type="submit">إرسال</button>
        </form>
        <pre id="aiQuickAnswer" class="ai-answer muted small"></pre>
      </div>
      <div class="panel-block">
        <h3>Mitarbeiter Hybrid-App (Flutter + FCM)</h3>
        <p>${pushSt?.fcmConfigured ? statusBadge(true) : statusBadge(false)} FCM · ${pushSt?.workersWithPush ?? 0} MA mit Token · ${pushSt?.registeredDevices ?? 0} Geräte</p>
        <p class="muted small">Kanal: ${pushSt?.primaryChannel || "fcm"} · ${pushSt?.workerAppKind || "hybrid_native"}</p>
        ${
          mobileDist?.install
            ? `<p class="muted small">APK: ${mobileDist.install.apkUrl ? `<a href="${mobileDist.install.apkUrl}" target="_blank" rel="noopener">Download</a>` : "BAUPASS_WORKER_APK_URL setzen (GitHub Actions Artifact)"}</p>`
            : ""
        }
        <button type="button" class="feature-card" data-goto-tab="mobile">Mobile-Tab →</button>
      </div>
      <div class="panel-block">
        <h3>Wallet (Apple / Google)</h3>
        <p class="muted small">${wallet ? JSON.stringify(wallet, null, 2) : "تحميل الحالة…"}</p>
      </div>
      <div class="link-row">
        <a href="/api/health/ready" target="_blank" rel="noopener">health/ready</a>
        <a href="/enterprise-hub.html?v=20260528a">مركز المؤسسة</a>
        <a href="/index.html">لوحة Legacy الكاملة</a>
      </div>
    `;
    panel.querySelector("[data-goto-tab]")?.addEventListener("click", () => {
      switchToTab("mobile");
      refreshActiveTab();
    });
    $("aiQuickForm")?.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const q = ev.target.question.value.trim();
      const out = $("aiQuickAnswer");
      out.textContent = "جاري الإرسال…";
      try {
        const aiBody = { question: q, use_agent: true, agent_id: "operations", lang: (localStorage.getItem("baupass-ui-lang") || "de").slice(0, 2) };
        const user = getUser();
        const cid =
          localStorage.getItem(COMPANY_KEY) ||
          user.preview_company_id ||
          user.company_id ||
          "";
        if (cid) aiBody.company_id = cid;
        const res = await api("/api/ai/query", {
          method: "POST",
          body: JSON.stringify(aiBody),
        });
        out.textContent = res.answer || res.hint || res.error || JSON.stringify(res, null, 2);
      } catch (e) {
        out.textContent = e.data?.error === "feature_not_available"
          ? `يتطلب ترقية: ${e.data.requiredPlan}`
          : e.message;
      }
    });
  } catch (e) {
    panel.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

async function loadMobile() {
  const panel = $("mobilePanel");
  panel.innerHTML = '<p class="muted">جاري التحميل…</p>';
  try {
    const data = await api("/api/v2/mobile/distribution");
    const install = data.install || {};
    const modes = (data.hybridModes || [])
      .map(
        (m) =>
          `<div class="layer-pill"><strong>${m.label || m.id}</strong><br/><span class="muted small">${m.api || ""}</span></div>`
      )
      .join("");
    const native = data.nativeInstall || {};
    const pwaLegacy = data.pwaInstall || {};
    panel.innerHTML = `
      <div class="panel-block">
        <h3>تطبيق الموظف الهجين (Flutter)</h3>
        <p class="muted small">${native.label || "Hybrid native — FCM push"} · API: <code>${native.apiPrefix || "/api/worker-app"}</code></p>
        <p><a href="${install.joinPage || "/join.html"}" target="_blank" rel="noopener">${install.joinPage || "/join.html"}</a> — QR التفعيل</p>
        <p>APK: ${install.apkUrl ? `<a href="${install.apkUrl}" target="_blank" rel="noopener">${install.apkUrl}</a>` : statusBadge(false) + " عيّن BAUPASS_WORKER_APK_URL"}</p>
        <p>TestFlight: ${install.testFlightUrl ? `<a href="${install.testFlightUrl}" target="_blank" rel="noopener">رابط</a>` : statusBadge(false)}</p>
        <p>Play Store: ${install.playStoreUrl ? `<a href="${install.playStoreUrl}" target="_blank" rel="noopener">رابط</a>` : statusBadge(false)}</p>
        <p>App Store: ${install.appStoreUrl ? `<a href="${install.appStoreUrl}" target="_blank" rel="noopener">رابط</a>` : statusBadge(false)}</p>
        <p class="muted small">Push: <code>${native.pushRegister || "/api/worker-app/push/register"}</code> (FCM) — ليس PWA.</p>
        <p class="muted small">PWA (قديم): ${pwaLegacy.deprecated ? statusBadge(false) + " " : ""}<a href="${install.pwaEntry || "#"}" target="_blank" rel="noopener">${pwaLegacy.label || "Legacy browser"}</a></p>
      </div>
      <div class="panel-block">
        <h3>أوضاع الحضور الثلاثة</h3>
        <div class="layer-grid">${modes}</div>
      </div>
      <p class="muted small">من تبويب الموظفين: زر «QR تفعيل» ينشئ رابط join لكل موظف.</p>
    `;
  } catch (e) {
    panel.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

const OPS_LAYER_ORDER = [
  ["1_digital_twin", "Digital Twin", "🗺"],
  ["2_ai_security", "AI Security", "🛡"],
  ["3_site_intelligence", "Site Intelligence", "📊"],
  ["4_reputation", "Reputation", "⭐"],
  ["5_emergency", "Emergency", "🚨"],
  ["6_camera_ai", "Camera AI", "📷"],
  ["7_iot", "IoT", "📡"],
  ["8_command_center", "Command Center", "🎛"],
  ["9_autonomous", "Autonomous", "⚙"],
  ["10_workforce_graph", "Workforce Graph", "🔗"],
  ["11_identity", "Identity", "🪪"],
  ["12_copilot", "Copilot", "🤖"],
];

function summarizeOpsLayer(key, val) {
  const v = val && typeof val === "object" ? val : {};
  const lines = [];
  let stat = "—";
  let tone = "ok";
  switch (key) {
    case "1_digital_twin":
      stat = `${v.summary?.workersOnSite ?? 0} MA vor Ort`;
      lines.push(`${v.summary?.gatesActive ?? 0} aktive Tore`, `${v.summary?.hazardZones ?? 0} Gefahrenzonen`);
      break;
    case "2_ai_security":
      stat = `${(v.openAlerts || []).length} offene Alerts`;
      lines.push(`${v.newFindings ?? 0} neue Findings`, (v.capabilities || []).slice(0, 2).join(", ") || "Analyse aktiv");
      tone = (v.openAlerts || []).length > 0 ? "warn" : "ok";
      break;
    case "3_site_intelligence":
      stat = `${(v.busiestGates || []).length} Top-Tore`;
      lines.push(`Datum ${v.date || "—"}`, `${v.totalEvents24h ?? v.events24h ?? "—"} Events/24h`);
      break;
    case "4_reputation":
      stat = `Ø ${Number(v.averageScore ?? 0).toFixed(1)} Punkte`;
      lines.push(`${(v.leaderboard || v.workers || []).length} MA im Ranking`);
      break;
    case "5_emergency":
      stat = v.active ? "Notfall aktiv" : "Kein Notfall";
      tone = v.active ? "danger" : "ok";
      if (v.active) lines.push(`ID ${v.emergencyId || v.id || "—"}`, `${v.insideCount ?? "—"} innen`);
      break;
    case "6_camera_ai":
      stat = `${v.events24h ?? 0} Events / 24h`;
      break;
    case "7_iot":
      stat = `${(v.devices || []).length} Geräte`;
      lines.push(v.status || "Registry");
      break;
    case "8_command_center":
      stat = `${v.totalOnSite ?? v.workersOnSite ?? 0} MA gesamt`;
      lines.push(`${v.openEmergencies ?? v.activeEmergencies ?? 0} Notfälle`, `${v.openSecurity ?? 0} Security`);
      break;
    case "9_autonomous":
      stat = `${v.enabledRules ?? v.ruleCount ?? 0} Regeln`;
      lines.push(v.api || "/api/automation/rules");
      break;
    case "10_workforce_graph":
      stat = `${(v.nodes || v.workers || []).length} Knoten`;
      lines.push(`${(v.edges || []).length} Verbindungen`);
      break;
    case "11_identity":
      stat = "Identity Hub";
      lines.push((v.apis?.gates || "Gates API").toString().slice(0, 40));
      break;
    case "12_copilot":
      stat = v.configured ? "KI bereit" : "Nicht konfiguriert";
      lines.push(v.endpoint || "POST /api/ops-os/copilot");
      tone = v.configured ? "ok" : "warn";
      break;
    default:
      stat = v.status || v.layer || "aktiv";
      break;
  }
  return { stat, lines: lines.filter(Boolean).slice(0, 3), tone };
}

function renderOpsLayerCard(key, title, icon, val) {
  const sum = summarizeOpsLayer(key, val);
  const num = String(key).replace(/\D/g, "").padStart(2, "0") || "—";
  const meta = sum.lines.map((l) => `<li>${l}</li>`).join("");
  return `
    <article class="ops-layer-card ops-tone-${sum.tone}" data-layer="${key}" role="button" tabindex="0" title="Details anzeigen">
      <div class="ops-layer-head">
        <span class="ops-layer-num">${num}</span>
        <span class="ops-layer-icon" aria-hidden="true">${icon}</span>
      </div>
      <h4 class="ops-layer-title">${title}</h4>
      <p class="ops-layer-stat">${escapeHtml(sum.stat)}</p>
      ${meta ? `<ul class="ops-layer-meta">${meta}</ul>` : ""}
      <span class="ops-layer-more muted small">Details ›</span>
    </article>
  `;
}

function formatOpsLayerDetailRows(val) {
  const rows = [];
  const push = (label, value) => {
    if (value === undefined || value === null || value === "") return;
    rows.push(`<tr><td>${escapeHtml(label)}</td><td>${escapeHtml(value)}</td></tr>`);
  };
  const v = val && typeof val === "object" ? val : {};
  if (v.layer) push("Layer", v.layer);
  if (v.status) push("Status", v.status);
  if (v.date) push("Datum", v.date);
  if (v.company_id || v.companyId) push("Firma", v.company_id || v.companyId);
  if (v.summary && typeof v.summary === "object") {
    for (const [sk, sv] of Object.entries(v.summary)) push(sk, sv);
  }
  if (Array.isArray(v.openAlerts)) push("Offene Security-Alerts", v.openAlerts.length);
  if (v.newFindings != null) push("Neue Findings", v.newFindings);
  if (v.averageScore != null) push("Reputation Ø", Number(v.averageScore).toFixed(1));
  if (v.active != null) push("Notfall aktiv", v.active ? "Ja" : "Nein");
  if (v.events24h != null) push("Kamera Events 24h", v.events24h);
  if (v.totalOnSite != null) push("MA on-site", v.totalOnSite);
  if (v.openEmergencies != null) push("Offene Notfälle", v.openEmergencies);
  if (v.openSecurity != null) push("Security offen", v.openSecurity);
  if (v.enabledRules != null) push("Automation Regeln", v.enabledRules);
  if (Array.isArray(v.devices)) push("IoT Geräte", v.devices.length);
  if (Array.isArray(v.busiestGates)) push("Top-Tore", v.busiestGates.length);
  if (v.configured != null) push("Copilot", v.configured ? "bereit" : "nicht konfiguriert");
  if (v.endpoint) push("API", v.endpoint);
  if (rows.length < 4) {
    for (const [k, raw] of Object.entries(v)) {
      if (["entities", "liveMovement", "findings", "leaderboard", "workers"].includes(k)) {
        push(k, Array.isArray(raw) ? `${raw.length} Einträge` : "Objekt");
        continue;
      }
      if (typeof raw === "object" && raw !== null) continue;
      push(k, raw);
      if (rows.length >= 14) break;
    }
  }
  return rows.join("") || '<tr><td colspan="2" class="muted">Keine Detaildaten</td></tr>';
}

function openOpsLayerModal(layerKey) {
  const layers = window.__opsLayersCache || {};
  const meta = OPS_LAYER_ORDER.find(([k]) => k === layerKey);
  const title = meta ? meta[1] : layerKey;
  const val = layers[layerKey];
  const sum = summarizeOpsLayer(layerKey, val);
  $("opsLayerModalTitle").textContent = title;
  $("opsLayerModalStat").textContent = sum.stat;
  $("opsLayerModalBody").innerHTML = formatOpsLayerDetailRows(val);
  $("opsLayerModal").classList.remove("hidden");
}

function initOpsLayerCards(root) {
  if (!root) return;
  root.querySelectorAll(".ops-layer-card").forEach((card) => {
    const open = () => openOpsLayerModal(card.dataset.layer || "");
    card.addEventListener("click", open);
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        open();
      }
    });
  });
}

function initOpsCarousel(root) {
  const track = root?.querySelector(".ops-carousel-track");
  const prev = root?.querySelector(".ops-carousel-prev");
  const next = root?.querySelector(".ops-carousel-next");
  const hint = root?.querySelector(".ops-carousel-hint");
  if (!track) return;

  const step = () => {
    const card = track.querySelector(".ops-layer-card");
    const gap = 14;
    return (card?.offsetWidth || 280) + gap;
  };

  if (hint) {
    hint.textContent = "Ebenen mit ‹ › wechseln — die Admin-Seite bleibt fix, nur die Kartenzeile scrollt.";
  }

  prev?.addEventListener("click", (e) => {
    e.stopPropagation();
    track.scrollBy({ left: -step(), behavior: "smooth" });
  });
  next?.addEventListener("click", (e) => {
    e.stopPropagation();
    track.scrollBy({ left: step(), behavior: "smooth" });
  });

  /* Scroll-Chaining zur Seite verhindern — nur die Kartenzeile bewegt sich */
  track.addEventListener(
    "wheel",
    (e) => {
      const dx = Math.abs(e.deltaX);
      const dy = Math.abs(e.deltaY);
      if (dx <= dy && !e.shiftKey) return;
      e.preventDefault();
      e.stopPropagation();
      track.scrollLeft += dx > dy ? e.deltaX : e.deltaY;
    },
    { passive: false }
  );

  track.addEventListener(
    "touchmove",
    (e) => {
      e.stopPropagation();
    },
    { passive: true }
  );
}

async function loadOperations() {
  const panel = $("operationsPanel");
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    panel.innerHTML = '<p class="muted">اختر شركة من القائمة أعلاه.</p>';
    return;
  }
  panel.innerHTML = '<p class="muted">جاري التحميل…</p>';
  try {
    const cid = q.replace("?company_id=", "");
    const data = await api(`/api/ops-os/overview?company_id=${encodeURIComponent(cid)}`);
    const layers = data.layers || {};
    const cards = OPS_LAYER_ORDER.map(([key, title, icon]) =>
      renderOpsLayerCard(key, title, icon, layers[key])
    ).join("");
    let rtLabel = "";
    try {
      const rt = await api("/api/v1/realtime/status");
      rtLabel = rt?.websocket?.enabled
        ? '<span class="badge badge-ok">WebSocket live</span>'
        : '<span class="badge badge-warn">SSE fallback</span>';
    } catch {
      rtLabel = "";
    }
    panel.innerHTML = `
      <div class="panel-block ops-panel">
        <div class="ops-panel-head">
          <h3>Physical Operations OS <span class="badge badge-ok">12 Ebenen</span> ${rtLabel}</h3>
          <p class="muted small">Firma ${data.companyId || cid}</p>
        </div>
        <div class="ops-carousel-shell" id="opsCarousel">
          <div class="ops-carousel-wrap">
            <button type="button" class="ops-carousel-btn ops-carousel-prev" aria-label="Vorherige Ebene">‹</button>
            <div class="ops-carousel-track">${cards}</div>
            <button type="button" class="ops-carousel-btn ops-carousel-next" aria-label="Nächste Ebene">›</button>
          </div>
        </div>
        <p class="ops-carousel-hint muted small"></p>
      </div>
      <div class="link-row">
        <a href="/ops-live-map.html${q ? q.replace("?", "?") : "?company_id=" + encodeURIComponent(cid)}" target="_blank" rel="noopener">🗺 Live Ops Karte</a>
        <a href="/ops-command-center.html" target="_blank" rel="noopener">Command Center</a>
        <a href="/ai-command-center.html${q}">KI Command Center</a>
        <a href="/enterprise-hub.html">مركز المؤسسة</a>
      </div>
      <iframe src="/ops-live-map.html${q ? q : "?company_id=" + encodeURIComponent(cid)}" title="Live Karte" class="ops-map-frame"></iframe>
    `;
    window.__opsLayersCache = layers;
    initOpsCarousel($("opsCarousel"));
    initOpsLayerCards($("opsCarousel"));
  } catch (e) {
    panel.innerHTML = `<p class="error">${e.message || "تعذّر تحميل العمليات — قد تحتاج جداول إضافية في DB"}</p>`;
  }
}

function requireCompany(panel) {
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    panel.innerHTML = '<p class="muted">اختر شركة من القائمة أعلاه.</p>';
    return null;
  }
  return q;
}

async function loadTools() {
  const panel = $("toolsPanel");
  const q = requireCompany(panel);
  if (q === null) return;
  panel.innerHTML = '<p class="muted">جاري التحميل…</p>';
  try {
    const [geofences, rules, integrations] = await Promise.all([
      api(`/api/geofences/admin${q}`),
      api(`/api/automation/rules${q}`),
      api(`/api/integrations${q}`),
    ]);
    const gfRows = geofences.geofences || [];
    const ruleRows = rules.rules || [];
    const intRows = integrations.integrations || [];
    const providers = [
      { id: "sap", label: "SAP" },
      { id: "oracle", label: "Oracle" },
      { id: "microsoft365", label: "Microsoft 365" },
      { id: "google_workspace", label: "Google Workspace" },
      { id: "payroll", label: "Payroll" },
    ];
    panel.innerHTML = `
      <div class="panel-block">
        <h3>${t("tools.geofence")}</h3>
        <p class="muted small">${t("tools.mapHint")}</p>
        <div id="geofenceMap"></div>
        <form id="geofenceForm" class="tool-form">
          <input name="site_name" placeholder="Site / Baustelle" required />
          <input name="latitude" type="number" step="any" placeholder="Latitude" required />
          <input name="longitude" type="number" step="any" placeholder="Longitude" required />
          <input name="radius_meters" type="number" value="50" placeholder="Radius (m)" />
          <button type="submit">${t("tools.addZone")}</button>
        </form>
        <div class="table-wrap" id="geofenceTable"></div>
      </div>
      <div class="panel-block">
        <h3>${t("tools.automation")}</h3>
        <form id="automationForm" class="tool-form">
          <input name="name" placeholder="Rule name" required />
          <select name="trigger_event">
            <option value="worker.checkin">Check-in</option>
            <option value="worker.checkout">Check-out</option>
            <option value="*">Any event</option>
          </select>
          <button type="submit">Create rule</button>
        </form>
        <div class="table-wrap" id="automationTable"></div>
      </div>
      <div class="panel-block">
        <h3>${t("tools.integrations")}</h3>
        <div class="layer-grid" id="integrationCards"></div>
      </div>`;
    renderTable($("geofenceTable"), gfRows, [
      { label: "الموقع", render: (r) => r.site_name || "-" },
      { label: "إحداثيات", render: (r) => `${r.latitude}, ${r.longitude}` },
      { label: "نصف القطر", render: (r) => `${r.radius_meters}m` },
      { label: "نشط", render: (r) => (r.active ? "نعم" : "لا") },
    ]);
    renderTable($("automationTable"), ruleRows, [
      { label: "الاسم", render: (r) => r.name || "-" },
      { label: "المحفّز", render: (r) => r.trigger_event || "-" },
      { label: "مفعّل", render: (r) => (r.enabled ? "نعم" : "لا") },
    ]);
    const intByProvider = Object.fromEntries(intRows.map((r) => [r.provider, r]));
    $("integrationCards").innerHTML = providers
      .map((p) => {
        const conn = intByProvider[p.id];
        const st = conn ? conn.status : "غير مربوط";
        return `<div class="layer-pill" data-provider="${p.id}">
          <strong>${p.label}</strong><br><span class="muted small">${st}</span>
          <button type="button" class="btn-link" data-connect="${p.id}">${t("tools.connect")}</button>
          <button type="button" class="btn-link" data-sync="${p.id}">${t("tools.sync")}</button>
        </div>`;
      })
      .join("");
    const gfForm = $("geofenceForm");
    const latIn = gfForm.querySelector('[name="latitude"]');
    const lngIn = gfForm.querySelector('[name="longitude"]');
    mountGeofenceMap($("geofenceMap"), latIn, lngIn, gfRows);
    $("geofenceForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const fd = new FormData(ev.target);
      await api(`/api/geofences/admin${q}`, {
        method: "POST",
        body: JSON.stringify({
          site_name: fd.get("site_name"),
          latitude: parseFloat(fd.get("latitude")),
          longitude: parseFloat(fd.get("longitude")),
          radius_meters: parseInt(fd.get("radius_meters") || "50", 10),
        }),
      });
      ev.target.reset();
      await loadTools();
    });
    $("automationForm").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const fd = new FormData(ev.target);
      await api(`/api/automation/rules${q}`, {
        method: "POST",
        body: JSON.stringify({
          name: fd.get("name"),
          trigger_event: fd.get("trigger_event"),
          conditions: [],
          actions: [{ type: "log", message: "automation_triggered" }],
          enabled: true,
        }),
      });
      ev.target.reset();
      await loadTools();
    });
    panel.querySelectorAll("[data-connect]").forEach((btn) => {
      btn.addEventListener("click", () => {
        pendingIntegrationProvider = btn.getAttribute("data-connect");
        const spec = INTEGRATION_WIZARD[pendingIntegrationProvider];
        if (!spec) return;
        $("integrationModalTitle").textContent = spec.title;
        renderWizardForm(pendingIntegrationProvider, $("integrationWizardForm"));
        $("integrationModal").classList.remove("hidden");
      });
    });
    panel.querySelectorAll("[data-sync]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const provider = btn.getAttribute("data-sync");
        try {
          const res = await api(`/api/integrations/${provider}/sync${q}`, { method: "POST", body: "{}" });
          alert(JSON.stringify(res, null, 2).slice(0, 800));
        } catch (e) {
          alert(e.message);
        }
      });
    });
  } catch (e) {
    panel.innerHTML = `<p class="error">${e.message}</p>`;
  }
}

function renderTable(container, rows, columns) {
  if (!rows.length) {
    container.innerHTML = '<p class="muted" style="padding:1rem">لا توجد بيانات.</p>';
    return;
  }
  const head = columns.map((c) => `<th>${c.label}</th>`).join("");
  const body = rows
    .map((row) => {
      const cells = columns.map((c) => `<td>${c.render(row)}</td>`).join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  container.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

async function loadInbox() {
  const el = $("inboxList");
  const countsEl = $("inboxCounts");
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    el.innerHTML = '<p class="muted">اختر شركة من القائمة أعلاه.</p>';
    countsEl.innerHTML = "";
    return;
  }
  el.innerHTML = '<p class="muted">جاري التحميل…</p>';
  const [data, pushSt] = await Promise.all([
    api(`/api/inbox${q}`),
    api("/api/platform/push/status").catch(() => null),
  ]);
  const liveHint = $("inboxLiveHint");
  if (liveHint) liveHint.classList.remove("hidden");
  const pushEl = $("inboxPushStatus");
  if (pushEl && pushSt) {
    const ready = pushSt.anyChannelReady;
    pushEl.classList.remove("hidden");
    pushEl.innerHTML = ready
      ? `Hybrid Push (FCM): ${pushSt.workersWithPush ?? 0} MA · ${pushSt.registeredDevices ?? 0} Geräte${
          pushSt.fcmConfigured ? "" : " · FCM_SERVER_KEY fehlt"
        }${pushSt.webPushSubscriptions ? ` · ${pushSt.webPushSubscriptions} Legacy-PWA` : ""}`
      : "FCM nicht konfiguriert — FCM_SERVER_KEY auf Railway setzen (Flutter Hybrid-App).";
  } else if (pushEl) {
    pushEl.classList.add("hidden");
  }
  const c = data.counts || {};
  updateInboxTabBadge(c.open, c.critical);
  countsEl.innerHTML = `
    <div class="card"><span class="muted">Offen</span><strong>${c.open ?? 0}</strong></div>
    <div class="card"><span class="muted">Kritisch</span><strong style="color:#f87171">${c.critical ?? 0}</strong></div>
    <div class="card"><span class="muted">Gesamt</span><strong>${c.total ?? 0}</strong></div>
    <button type="button" class="feature-card" data-goto-tab="operations">Ops Center →</button>
  `;
  countsEl.querySelector("[data-goto-tab]")?.addEventListener("click", () => {
    switchToTab("operations");
    refreshActiveTab();
  });
  const items = data.items || [];
  const bulkBar = $("inboxBulkBar");
  const docCount = items.filter((it) => String(it.id || "").startsWith("doc:")).length;
  const leaveCount = items.filter((it) => String(it.id || "").startsWith("leave:")).length;
  const sysCount = items.filter((it) => String(it.id || "").startsWith("sys:")).length;
  if (bulkBar) {
    if (!items.length) {
      bulkBar.classList.add("hidden");
      bulkBar.innerHTML = "";
    } else {
      bulkBar.classList.remove("hidden");
      bulkBar.innerHTML = `
        <span class="muted small">Sammelaktionen:</span>
        ${docCount ? `<button type="button" class="ghost" id="inboxBulkDocPush">FCM an ${docCount} MA (Dokumente)</button>` : ""}
        ${leaveCount ? `<button type="button" class="ghost" id="inboxBulkLeaveOk">Alle ${leaveCount} Urlaube genehmigen</button>` : ""}
        ${leaveCount ? `<button type="button" class="ghost" id="inboxBulkLeaveNo">Alle ablehnen</button>` : ""}
        ${sysCount ? `<button type="button" class="ghost" id="inboxBulkSysAck">${sysCount} System ack</button>` : ""}
      `;
    }
  }
  if (!items.length) {
    el.innerHTML = '<p class="muted">Keine offenen Punkte — alles im grünen Bereich.</p>';
    return;
  }
  el.innerHTML = `<table><thead><tr><th></th><th>Titel</th><th>Quelle</th><th>Aktionen</th></tr></thead><tbody>${items
    .map((it) => {
      const acts = (it.actions || [])
        .map((a) => {
          if (a.type === "resolve" || a.type === "ack")
            return `<button type="button" class="btn-link inbox-resolve" data-id="${it.id}">Erledigt</button>`;
          if (a.type === "execute" && a.action)
            return `<button type="button" class="btn-link inbox-exec" data-id="${it.id}" data-action="${a.action}" data-params="${encodeURIComponent(JSON.stringify(a.params || {}))}">${a.label || a.action}</button>`;
          if (a.type === "navigate")
            return `<a class="btn-link" href="${a.url}${q}">${a.label || "Öffnen"}</a>`;
          if (a.type === "prompt")
            return `<a class="btn-link" href="/ai-command-center.html${q}&autoprompt=${encodeURIComponent(a.prompt || "")}">KI</a>`;
          return "";
        })
        .join(" · ");
      return `<tr class="${it.severity === "critical" ? "row-critical" : ""}">
        <td><span class="badge badge-warn">${it.severity || ""}</span></td>
        <td><strong>${it.title || ""}</strong><br><span class="muted small">${it.message || ""}</span></td>
        <td>${it.source || ""}</td>
        <td>${acts}</td></tr>`;
    })
    .join("")}</tbody></table>`;
  el.querySelectorAll(".inbox-resolve").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        const res = await api(`/api/inbox/${encodeURIComponent(btn.dataset.id)}/resolve${q}`, {
          method: "POST",
          body: "{}",
        });
        showActionToast(res.ok ? "Erledigt." : (res.error || "Fehler"), !res.ok);
        await loadInbox();
      } catch (e) {
        showActionToast(e.message, true);
      }
    });
  });
  async function runInboxBulk(action, extra = {}) {
    const cid = q.replace("?company_id=", "");
    const res = await api(`/api/inbox/bulk${q}`, {
      method: "POST",
      body: JSON.stringify({ action, company_id: cid || undefined, ...extra }),
    });
    const msg =
      action === "push_document_reminders"
        ? `Push: ${res.pushSent ?? 0}/${res.processed ?? 0} Dokumente`
        : action === "approve_pending_leave"
          ? `${res.approvedOrRejected ?? 0} Urlaube · Push ${res.pushSent ?? 0}`
          : `${res.acknowledged ?? 0} System-Alerts bestätigt`;
    showActionToast(res.ok ? msg : res.error || "Fehler", !res.ok);
    await loadInbox();
  }

  $("inboxBulkDocPush")?.addEventListener("click", () => {
    if (!confirm("FCM-Push für alle ablaufenden Dokumente in der Liste senden?")) return;
    runInboxBulk("push_document_reminders").catch((e) => showActionToast(e.message, true));
  });
  $("inboxBulkLeaveOk")?.addEventListener("click", () => {
    if (!confirm("Alle offenen Urlaubsanträge in der Liste genehmigen?")) return;
    runInboxBulk("approve_pending_leave", { decision: "approve" }).catch((e) =>
      showActionToast(e.message, true),
    );
  });
  $("inboxBulkLeaveNo")?.addEventListener("click", () => {
    if (!confirm("Alle offenen Urlaubsanträge ablehnen?")) return;
    runInboxBulk("approve_pending_leave", { decision: "reject" }).catch((e) =>
      showActionToast(e.message, true),
    );
  });
  $("inboxBulkSysAck")?.addEventListener("click", () => {
    runInboxBulk("ack_system_alerts").catch((e) => showActionToast(e.message, true));
  });

  el.querySelectorAll(".inbox-exec").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id || "";
      const action = btn.dataset.action || "";
      if (id.startsWith("leave:") && (action === "approve_leave_request" || action === "reject_leave_request")) {
        const decision = action === "approve_leave_request" ? "approve" : "reject";
        try {
          const res = await api(`/api/inbox/${encodeURIComponent(id)}/resolve${q}`, {
            method: "POST",
            body: JSON.stringify({ decision }),
          });
          const msg = res.ok
            ? `${decision === "approve" ? "Genehmigt" : "Abgelehnt"}. ${formatPushDelivery(res)}`
            : res.error || "Fehler";
          showActionToast(msg, !res.ok);
          await loadInbox();
          return;
        } catch (e) {
          showActionToast(e.message, true);
          return;
        }
      }
      try {
        const params = JSON.parse(decodeURIComponent(btn.dataset.params || "%7B%7D"));
        const cid = q.replace("?company_id=", "");
        const res = await api("/api/ai/actions/execute", {
          method: "POST",
          body: JSON.stringify({ action, params, company_id: cid || undefined }),
        });
        const pushMsg = formatPushDelivery(res);
        showActionToast(
          res.ok ? `${action} ✓${pushMsg ? ` — ${pushMsg}` : ""}` : res.error || "Fehler",
          !res.ok,
        );
        await loadInbox();
      } catch (e) {
        showActionToast(e.message, true);
      }
    });
  });
}

async function loadOverview() {
  renderQuickLinks();
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    $("statCards").innerHTML = '<p class="muted">اختر شركة من القائمة أعلاه.</p>';
    return;
  }
  const cid = q.replace("?company_id=", "");
  const [overview, inbox, roleDash, opsBrief] = await Promise.all([
    api(`/api/v2/admin/overview${q}`),
    api(`/api/inbox${q}`).catch(() => ({ counts: {} })),
    api(`/api/dashboard/role${q}`).catch(() => null),
    cid
      ? api(`/api/ops-os/overview?company_id=${encodeURIComponent(cid)}`).catch(() => null)
      : Promise.resolve(null),
  ]);
  const wf = overview.workforce || {};
  const openInbox = inbox?.counts?.open ?? 0;
  const dashWidgets = (roleDash?.widgets || []).filter((w) => w.id !== "on_site");
  const extraCards = dashWidgets
    .map(
      (w) =>
        `<div class="card"><span class="muted">${w.label || w.id}</span><strong>${w.value ?? "—"}</strong>${w.detail ? `<small class="muted">${w.detail}</small>` : ""}</div>`,
    )
    .join("");
  $("statCards").innerHTML = `
    <div class="card"><span class="muted">على الموقع الآن</span><strong>${wf.onSite ?? 0}</strong></div>
    <div class="card"><span class="muted">موظفون نشطون</span><strong>${wf.totalActive ?? 0}</strong></div>
    <div class="card"><span class="muted">مناطق Geofence</span><strong>${overview.zonesCount ?? 0}</strong></div>
    <button type="button" class="card" data-goto-tab="inbox" style="cursor:pointer;text-align:start;border:1px solid var(--border)">
      <span class="muted">Posteingang</span><strong style="color:${openInbox > 0 ? "#fbbf24" : "inherit"}">${openInbox}</strong>
    </button>
    ${extraCards}
  `;
  $("statCards").querySelector('[data-goto-tab="inbox"]')?.addEventListener("click", async () => {
    switchToTab("inbox");
    await loadInbox();
  });
  const fc = overview.tomorrowForecast || {};
  const fp = $("forecastPanel");
  if (fp && fc.date) {
    fp.classList.remove("hidden");
    fp.innerHTML = `
      <div class="card forecast-card">
        <div class="forecast-head">
          <span class="muted">Prognose morgen · ${fc.weekdayLabel || ""} ${fc.date}</span>
          <span class="badge">${fc.confidence === "high" ? "hoch" : "mittel"}</span>
        </div>
        <p class="forecast-summary">${fc.summary || ""}</p>
        <div class="cards forecast-stats">
          <div><span class="muted">Erwartet on-site</span><strong>${fc.expectedOnSite ?? "—"}</strong></div>
          <div><span class="muted">Ausfallrisiko</span><strong>${fc.expectedAbsent ?? "—"}</strong></div>
          <div><span class="muted">Aktiv gesamt</span><strong>${fc.totalActive ?? "—"}</strong></div>
        </div>
        <p class="muted small"><a href="/ai-command-center.html${q}">KI Command Center</a> · <a href="/ops-command-center.html${q}">Ops OS</a></p>
      </div>`;
  } else if (fp) {
    fp.classList.add("hidden");
    fp.innerHTML = "";
  }
  const strip = $("opsCommandStrip");
  if (strip && q) {
    strip.classList.remove("hidden");
    const twin = opsBrief?.layers?.["1_digital_twin"]?.summary || {};
    const sec = opsBrief?.layers?.["2_ai_security"] || {};
    const emg = opsBrief?.layers?.["5_emergency"] || {};
    strip.innerHTML = `
      <span class="ops-strip-kpi"><strong>${twin.workersOnSite ?? wf.onSite ?? 0}</strong> on-site</span>
      <span class="ops-strip-kpi"><strong>${(sec.openAlerts || []).length}</strong> Security</span>
      <span class="ops-strip-kpi">${emg.active ? "🚨 Notfall" : "✓ ruhig"}</span>
      <a href="/ops-command-center.html${q}" target="_blank" rel="noopener">Ops Command Center</a>
      <a href="/ops-live-map.html${q}" target="_blank" rel="noopener">Live Karte</a>
      <a href="/ai-command-center.html${q}" target="_blank" rel="noopener">KI Command Center</a>
      <a href="/foreman.html" target="_blank" rel="noopener">Vorarbeiter</a>
      <button type="button" class="ghost ops-strip-tab" data-goto-tab="operations">12 Ebenen →</button>
    `;
    strip.querySelector(".ops-strip-tab")?.addEventListener("click", async () => {
      switchToTab("operations");
      await loadOperations();
    });
  } else if (strip) {
    strip.classList.add("hidden");
  }
  renderTable($("recentAccess"), overview.recentAccess || [], [
    { label: "الموظف", render: (r) => `${r.first_name || ""} ${r.last_name || ""}`.trim() },
    { label: "Badge", render: (r) => r.badge_id || "-" },
    { label: "الاتجاه", render: (r) => r.direction || "-" },
    { label: "البوابة", render: (r) => r.gate || "-" },
    { label: "الوقت", render: (r) => (r.timestamp || "").slice(0, 19) },
  ]);
}

async function loadQrImage(link) {
  const token = localStorage.getItem(TOKEN_KEY);
  const res = await fetch(`/api/qr.png?data=${encodeURIComponent(link)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    throw new Error("qr_failed");
  }
  return URL.createObjectURL(await res.blob());
}

function closeJoinModal() {
  const modal = $("joinModal");
  modal.classList.add("hidden");
  const img = $("joinQrImg");
  if (img.dataset.blobUrl) {
    URL.revokeObjectURL(img.dataset.blobUrl);
    delete img.dataset.blobUrl;
  }
  img.removeAttribute("src");
}

async function showWorkerJoin(workerId, workerName) {
  const payload = await api(`/api/workers/${encodeURIComponent(workerId)}/app-access`, {
    method: "POST",
  });
  const link = payload.link || payload.joinLink || "";
  if (!link) {
    alert("لم يُنشأ رابط التفعيل.");
    return;
  }
  $("joinModalName").textContent = workerName;
  $("joinLinkInput").value = link;
  const exp = payload.accessExpiresAt ? String(payload.accessExpiresAt).slice(0, 19) : "";
  $("joinExpires").textContent = exp
    ? `رابط لمرة واحدة — صالح حتى: ${exp} (UTC)`
    : "رابط لمرة واحدة — يُستخدم عند أول تسجيل دخول.";
  const blobUrl = await loadQrImage(link);
  const img = $("joinQrImg");
  img.src = blobUrl;
  img.dataset.blobUrl = blobUrl;
  $("joinModal").classList.remove("hidden");
}

$("joinCloseBtn").addEventListener("click", closeJoinModal);
$("joinModal").addEventListener("click", (e) => {
  if (e.target === $("joinModal")) closeJoinModal();
});
$("joinCopyBtn").addEventListener("click", async () => {
  const link = $("joinLinkInput").value;
  try {
    await navigator.clipboard.writeText(link);
    alert("تم نسخ الرابط.");
  } catch {
    $("joinLinkInput").select();
    document.execCommand("copy");
    alert("تم نسخ الرابط.");
  }
});

async function assignNfc(workerId, inputEl) {
  const uid = (inputEl.value || "").trim();
  if (!uid) {
    alert("أدخل UID البطاقة (مثال: 04A1B2C3 أو 04:A1:B2:C3)");
    return;
  }
  await api(`/api/v2/workers/${encodeURIComponent(workerId)}/physical-card${companyQuery()}`, {
    method: "PATCH",
    body: JSON.stringify({ physicalCardId: uid }),
  });
  alert("تم حفظ بطاقة NFC.");
  await loadWorkers();
}

async function loadWorkers() {
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    $("workersTable").innerHTML = '<p class="muted" style="padding:1rem">اختر شركة.</p>';
    return;
  }
  const data = await api(`/api/v2/workers${q}`);
  const rows = data.workers || [];
  const container = $("workersTable");
  if (!rows.length) {
    container.innerHTML = '<p class="muted" style="padding:1rem">لا يوجد موظفون.</p>';
    return;
  }
  const head = `
    <tr>
      <th>الاسم</th>
      <th>Badge</th>
      <th>بطاقة NFC</th>
      <th>تعيين UID</th>
      <th>التطبيق</th>
    </tr>`;
  const body = rows
    .map((r) => {
      const id = r.id;
      const name = `${r.first_name || ""} ${r.last_name || ""}`.trim();
      const current = r.physical_card_id || "";
      return `<tr>
        <td>${name}</td>
        <td>${r.badge_id || "-"}</td>
        <td><code>${current || "—"}</code></td>
        <td>
          <input class="nfc-input" type="text" placeholder="UID" value="${current}" data-worker-id="${id}" />
          <button type="button" class="btn-link" data-save-nfc="${id}">حفظ</button>
        </td>
        <td>
          <button type="button" class="btn-link" data-join-app="${id}" data-worker-name="${name.replace(/"/g, "&quot;")}">QR تفعيل</button>
        </td>
      </tr>`;
    })
    .join("");
  container.innerHTML = `<table><thead>${head}</thead><tbody>${body}</tbody></table>`;
  container.querySelectorAll("[data-save-nfc]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wid = btn.getAttribute("data-save-nfc");
      const input = container.querySelector(`input[data-worker-id="${wid}"]`);
      assignNfc(wid, input).catch((e) => alert(e.message));
    });
  });
  container.querySelectorAll("[data-join-app]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const wid = btn.getAttribute("data-join-app");
      const wname = btn.getAttribute("data-worker-name") || wid;
      showWorkerJoin(wid, wname).catch((e) => alert(e.message || e));
    });
  });
}

async function loadAccess() {
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    $("accessTable").innerHTML = '<p class="muted" style="padding:1rem">اختر شركة.</p>';
    $("accessSummary").innerHTML = "";
    return;
  }
  try {
    const summary = await api(`/api/access-logs/summary${q}`);
    const open = Array.isArray(summary.openEntries) ? summary.openEntries.length : 0;
    const hourly = Array.isArray(summary.hourly) ? summary.hourly : [];
    const checkIns = hourly.reduce((n, h) => n + (h.checkIn || 0), 0);
    const checkOuts = hourly.reduce((n, h) => n + (h.checkOut || 0), 0);
    $("accessSummary").innerHTML = `
      <div class="card"><span class="muted">دخول اليوم</span><strong>${checkIns}</strong></div>
      <div class="card"><span class="muted">خروج اليوم</span><strong>${checkOuts}</strong></div>
      <div class="card"><span class="muted">جلسات مفتوحة</span><strong>${open}</strong></div>
    `;
  } catch {
    $("accessSummary").innerHTML = "";
  }
  const exportLink = $("exportCsvLink");
  if (exportLink) {
    exportLink.href = `/api/access-logs/export.csv${q}`;
    exportLink.onclick = (e) => {
      const token = localStorage.getItem(TOKEN_KEY);
      if (!token) return;
      e.preventDefault();
      fetch(exportLink.href, { headers: { Authorization: `Bearer ${token}` } })
        .then((r) => r.blob())
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "access-logs.csv";
          a.click();
          URL.revokeObjectURL(url);
        })
        .catch((err) => alert(err.message || "export_failed"));
    };
  }
  const data = await api(`/api/v2/access/live${q}`);
  renderTable($("accessTable"), data.access_logs || [], [
    { label: "الموظف", render: (r) => `${r.first_name || ""} ${r.last_name || ""}`.trim() },
    { label: "الاتجاه", render: (r) => r.direction || "-" },
    { label: "البوابة", render: (r) => r.gate || "-" },
    { label: "الوقت", render: (r) => (r.timestamp || "").slice(0, 19) },
  ]);
}

async function refreshActiveTab() {
  const active = document.querySelector(".tab.active");
  const tab = active?.dataset?.tab || "overview";
  if (tab === "inbox") {
    await loadInbox();
    await startAdminRealtime();
  }
  else if (tab === "workers") await loadWorkers();
  else if (tab === "access") await loadAccess();
  else if (tab === "mobile") await loadMobile();
  else if (tab === "operations") await loadOperations();
  else if (tab === "platform") await loadPlatform();
  else if (tab === "tools") await loadTools();
  else if (tab === "enterprise") syncEnterpriseFrame();
  else await loadOverview();
}

async function bootSession() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    showLogin();
    return;
  }
  try {
    await api("/api/v2/auth/session");
    showDashboard();
    await loadCompanies();
    await loadPlatformBanner();
    await refreshActiveTab();
    startAdminRealtime().catch(() => {});
    refreshInboxBadgeOnly().catch(() => {});
  } catch {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    showLogin();
  }
}

$("loginBtn").addEventListener("click", async () => {
  $("loginError").classList.add("hidden");
  try {
    const payload = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("username").value.trim(),
        password: $("password").value,
        loginScope: $("loginScope").value,
      }),
    });
    if (!payload.ok || !payload.token) {
      throw new Error(payload.error || "login_failed");
    }
    localStorage.setItem(TOKEN_KEY, payload.token);
    localStorage.setItem(USER_KEY, JSON.stringify(payload.user || {}));
    if (payload.user?.company_id) {
      localStorage.setItem(COMPANY_KEY, payload.user.company_id);
    }
    showDashboard();
    await loadCompanies();
    await loadPlatformBanner();
    await refreshActiveTab();
    startAdminRealtime().catch(() => {});
    refreshInboxBadgeOnly().catch(() => {});
  } catch (e) {
    $("loginError").textContent = e.message || "فشل تسجيل الدخول";
    $("loginError").classList.remove("hidden");
  }
});

$("logoutBtn").addEventListener("click", async () => {
  try {
    await api("/api/v2/auth/revoke", { method: "POST" });
  } catch {
    // ignore
  }
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  showLogin();
});

$("refreshBtn").addEventListener("click", () => refreshActiveTab().catch((e) => alert(e.message)));

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
    $(`tab-${btn.dataset.tab}`).classList.remove("hidden");
    refreshActiveTab().catch((e) => alert(e.message));
  });
});

$("integrationWizardForm")?.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (!pendingIntegrationProvider) return;
  const q = companyQuery();
  try {
    const fd = new FormData(ev.target);
    const body = buildConnectPayload(pendingIntegrationProvider, fd);
    await api(`/api/integrations/${pendingIntegrationProvider}/connect${q}`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    $("integrationModal").classList.add("hidden");
    pendingIntegrationProvider = null;
    alert("OK");
    if (document.querySelector(".tab.active")?.dataset?.tab === "tools") await loadTools();
  } catch (e) {
    alert(e.message);
  }
});

$("integrationModalClose")?.addEventListener("click", () => {
  $("integrationModal").classList.add("hidden");
  pendingIntegrationProvider = null;
});

$("opsLayerModalClose")?.addEventListener("click", () => {
  $("opsLayerModal")?.classList.add("hidden");
});

$("opsLayerModal")?.addEventListener("click", (e) => {
  if (e.target?.id === "opsLayerModal") $("opsLayerModal").classList.add("hidden");
});

const langSel = $("langSelect");
if (langSel) {
  langSel.value = getLang();
  langSel.addEventListener("change", () => setLang(langSel.value));
}
applyI18n();

bootSession();
