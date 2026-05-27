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
    </tr>`;
  const body = rows
    .map((r) => {
      const id = r.id;
      const current = r.physical_card_id || "";
      return `<tr>
        <td>${(r.first_name || "")} ${(r.last_name || "")}</td>
        <td>${r.badge_id || "-"}</td>
        <td><code>${current || "—"}</code></td>
        <td>
          <input class="nfc-input" type="text" placeholder="UID" value="${current}" data-worker-id="${id}" />
          <button type="button" class="btn-link" data-save-nfc="${id}">حفظ</button>
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
}

async function loadAccess() {
  const q = companyQuery();
  if (getUser().role === "superadmin" && !q) {
    $("accessTable").innerHTML = '<p class="muted" style="padding:1rem">اختر شركة.</p>';
    return;
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
