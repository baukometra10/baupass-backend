const TOKEN_KEY = "baupass-admin-v2-token";
const USER_KEY = "baupass-admin-v2-user";
const COMPANY_KEY = "baupass-admin-v2-company";

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

function switchToTab(tabId) {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("hidden", panel.id !== `tab-${tabId}`);
  });
}

function renderQuickLinks() {
  const items = [
    { tab: "enterprise", title: "مركز المؤسسة (16 طبقة)", desc: "خريطة كل ما بُني + مساعد AI" },
    { tab: "workers", title: "الموظفون + NFC", desc: "تعيين بطاقة وQR تفعيل التطبيق" },
    { tab: "access", title: "الحضور المباشر", desc: "دخول/خروج وتصدير CSV" },
    { tab: "mobile", title: "تطبيق الموظف", desc: "APK، TestFlight، join.html" },
    { tab: "operations", title: "عمليات الموقع", desc: "12 طبقة Physical Operations OS" },
    { tab: "platform", title: "جاهزية المنصة", desc: "Redis، DB، نضج عالمي" },
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
    const [caps, ready, health, ent] = await Promise.all([
      api("/api/platform/capabilities"),
      fetch("/api/health/ready").then((r) => r.json()),
      fetch("/api/health").then((r) => r.json()).catch(() => ({})),
      api("/api/platform/entitlements").catch(() => null),
    ]);
    const steps = (caps.nextSteps || [])
      .map((s) => `<li>${s}</li>`)
      .join("");
    const attendance = caps.attendance || {};
    const attRows = Object.entries(attendance)
      .map(([k, v]) => `<tr><td>${k}</td><td>${statusBadge(!!v)}</td></tr>`)
      .join("");
    panel.innerHTML = `
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
      </div>`
          : ""
      }
      <div class="link-row">
        <a href="/api/health/ready" target="_blank" rel="noopener">health/ready</a>
        <a href="/enterprise-hub.html">مركز المؤسسة</a>
        <a href="/index.html">لوحة Legacy الكاملة</a>
      </div>
    `;
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
    panel.innerHTML = `
      <div class="panel-block">
        <h3>تثبيت الموظف (ظاهر في join.html)</h3>
        <p><a href="${install.joinPage || "/join.html"}" target="_blank" rel="noopener">${install.joinPage || "/join.html"}</a></p>
        <p>APK: ${install.apkUrl ? `<a href="${install.apkUrl}" target="_blank" rel="noopener">${install.apkUrl}</a>` : statusBadge(false) + " عيّن BAUPASS_WORKER_APK_URL"}</p>
        <p>TestFlight: ${install.testFlightUrl ? `<a href="${install.testFlightUrl}" target="_blank" rel="noopener">رابط</a>` : statusBadge(false)}</p>
        <p>PWA: <a href="${install.pwaEntry || "#"}" target="_blank" rel="noopener">فتح PWA</a></p>
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
    const pills = Object.entries(layers)
      .map(([key, val]) => {
        const label = key.replace(/_/g, " ");
        const summary =
          typeof val === "object" && val !== null
            ? JSON.stringify(val).slice(0, 80) + "…"
            : String(val);
        return `<div class="layer-pill"><strong>${label}</strong><br/><span class="muted small">${summary}</span></div>`;
      })
      .join("");
    panel.innerHTML = `
      <div class="panel-block">
        <h3>Physical Operations OS <span class="badge badge-ok">12 طبقة</span></h3>
        <p class="muted small">Company ${data.companyId || cid}</p>
        <div class="layer-grid">${pills}</div>
      </div>
      <div class="link-row">
        <a href="/index.html#access">إدارة Zutritt (Legacy)</a>
        <a href="/index.html#devices">الأجهزة (Legacy)</a>
      </div>
    `;
  } catch (e) {
    panel.innerHTML = `<p class="error">${e.message || "تعذّر تحميل العمليات — قد تحتاج جداول إضافية في DB"}</p>`;
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

async function loadOverview() {
  renderQuickLinks();
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    $("statCards").innerHTML = '<p class="muted">اختر شركة من القائمة أعلاه.</p>';
    return;
  }
  const overview = await api(`/api/v2/admin/overview${q}`);
  const wf = overview.workforce || {};
  $("statCards").innerHTML = `
    <div class="card"><span class="muted">على الموقع الآن</span><strong>${wf.onSite ?? 0}</strong></div>
    <div class="card"><span class="muted">موظفون نشطون</span><strong>${wf.totalActive ?? 0}</strong></div>
    <div class="card"><span class="muted">مناطق Geofence</span><strong>${overview.zonesCount ?? 0}</strong></div>
  `;
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
  if (tab === "workers") await loadWorkers();
  else if (tab === "access") await loadAccess();
  else if (tab === "mobile") await loadMobile();
  else if (tab === "operations") await loadOperations();
  else if (tab === "platform") await loadPlatform();
  else if (tab === "enterprise") { /* iframe */ }
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

bootSession();
