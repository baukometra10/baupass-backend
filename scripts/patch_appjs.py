import sys

content = open('app.js', 'r', encoding='utf-8').read()

old = (
    'function createLeaveRequestsPanel() {\n'
    '  const panel = document.createElement("div");\n'
    '  panel.id = "leaveRequestsTable";\n'
    '  document.body.appendChild(panel);\n'
    '  return panel;\n'
    '}'
)
new = (
    'function createLeaveRequestsPanel() {\n'
    '  // Abwesenheitskalender und Besucher-Widget ebenfalls initialisieren\n'
    '  renderAbsenceCalendarSection();\n'
    '  renderCurrentVisitorsSection();\n'
    '  const panel = document.createElement("div");\n'
    '  panel.id = "leaveRequestsTable";\n'
    '  document.body.appendChild(panel);\n'
    '  return panel;\n'
    '}'
)

if old in content:
    content = content.replace(old, new, 1)
    open('app.js', 'w', encoding='utf-8', newline='').write(content)
    print('replaced OK')
else:
    print('NOT FOUND')
    idx = content.find('createLeaveRequestsPanel')
    print(repr(content[idx:idx+300]))


// ─────────────────────────────────────────────────────────────────────────────
// AKTUELLE BESUCHER (Live-Ansicht)
// ─────────────────────────────────────────────────────────────────────────────

let currentVisitorsRefreshTimer = null;

async function loadCurrentVisitors() {
  const container = document.getElementById("currentVisitorsPanel");
  if (!container) return;
  const sessionToken = loadStoredSessionToken();
  if (!sessionToken) return;
  try {
    const res = await fetch(`${API_BASE}/api/workers/current-visitors`, {
      headers: { Authorization: `Bearer ${sessionToken}` }
    });
    if (!res.ok) { container.innerHTML = `<p class="muted">Fehler beim Laden</p>`; return; }
    const visitors = await res.json();
    if (visitors.length === 0) {
      container.innerHTML = `<p class="muted" style="padding:16px;">Aktuell keine Besucher auf dem Gelände.</p>`;
      return;
    }
    container.innerHTML = visitors.map(v => {
      const mins = v.minutes_left;
      let timeLabel = "";
      if (mins !== null) {
        if (mins < 0) timeLabel = `<span class="visitor-time expired">Abgelaufen</span>`;
        else if (mins < 30) timeLabel = `<span class="visitor-time soon">${mins} Min verbleibend</span>`;
        else {
          const h = Math.floor(mins / 60), m = mins % 60;
          timeLabel = `<span class="visitor-time ok">${h > 0 ? h + "h " : ""}${m}m verbleibend</span>`;
        }
      }
      return `<div class="visitor-live-card">
        <div class="vlc-name">${escapeHtml(v.name)} <span class="vlc-badge">${escapeHtml(v.badge_id)}</span></div>
        <div class="vlc-meta">${escapeHtml(v.visitor_company || "")}${v.host_name ? " · Gastgeber: " + escapeHtml(v.host_name) : ""}</div>
        <div class="vlc-meta">${escapeHtml(v.visit_purpose || "")}</div>
        ${timeLabel}
      </div>`;
    }).join("");
  } catch(e) {
    container.innerHTML = `<p class="muted">Fehler: ${escapeHtml(String(e))}</p>`;
  }
}

function renderCurrentVisitorsSection() {
  const existing = document.getElementById("currentVisitorsSectionWrapper");
  if (existing) { loadCurrentVisitors(); return; }
  const section = document.createElement("div");
  section.id = "currentVisitorsSectionWrapper";
  section.className = "dashboard-card";
  section.innerHTML = `
    <div class="dashboard-card-header" style="display:flex;align-items:center;justify-content:space-between;">
      <h3 style="margin:0;">👥 Aktuelle Besucher</h3>
      <button class="btn-icon" onclick="loadCurrentVisitors()" title="Aktualisieren">↻</button>
    </div>
    <div id="currentVisitorsPanel"><p class="muted" style="padding:16px;">Lädt...</p></div>
  `;
  const target = document.getElementById("leaveRequestsTable")?.parentElement
    || document.querySelector(".main-content") || document.body;
  target.insertBefore(section, target.firstChild);
  loadCurrentVisitors();
  if (currentVisitorsRefreshTimer) clearInterval(currentVisitorsRefreshTimer);
  currentVisitorsRefreshTimer = setInterval(loadCurrentVisitors, 30000);
}

// ─────────────────────────────────────────────────────────────────────────────
// ABWESENHEITSKALENDER
// ─────────────────────────────────────────────────────────────────────────────

let calendarYear = new Date().getFullYear();
let calendarMonth = new Date().getMonth(); // 0-based

async function renderAbsenceCalendar() {
  const container = document.getElementById("absenceCalendarPanel");
  if (!container) return;
  const sessionToken = loadStoredSessionToken();
  if (!sessionToken) return;
  try {
    const res = await fetch(`${API_BASE}/api/leave-requests`, {
      headers: { Authorization: `Bearer ${sessionToken}` }
    });
    if (!res.ok) return;
    const requests = await res.json();
    drawAbsenceCalendar(container, requests);
  } catch(e) { /* silent */ }
}

function drawAbsenceCalendar(container, requests) {
  const year = calendarYear, month = calendarMonth;
  const firstDay = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const startDow = (firstDay.getDay() + 6) % 7; // 0=Mo
  const monthName = firstDay.toLocaleDateString("de-DE", { month: "long", year: "numeric" });

  const pad = d => String(d).padStart(2, "0");
  const toISO = d => `${year}-${pad(month + 1)}-${pad(d)}`;

  // leave requests -> map day -> list of workers+type
  const dayMap = {};
  const typeColors = { urlaub: "#2563eb", krank: "#c53d2f", sonstiges: "#7c3aed" };
  requests.filter(r => r.status !== "abgelehnt").forEach(r => {
    const start = new Date(r.start_date), end = new Date(r.end_date);
    for (let d = 1; d <= daysInMonth; d++) {
      const iso = toISO(d);
      if (iso >= r.start_date && iso <= r.end_date) {
        if (!dayMap[d]) dayMap[d] = [];
        dayMap[d].push({ name: r.worker_name || r.worker_id, type: r.type, status: r.status });
      }
    }
  });

  const today = new Date().toISOString().slice(0, 10);

  let html = `<div class="absence-cal-header">
    <button class="btn-icon" onclick="calendarMonth--;if(calendarMonth<0){calendarMonth=11;calendarYear--;}renderAbsenceCalendar()">‹</button>
    <strong>${monthName}</strong>
    <button class="btn-icon" onclick="calendarMonth++;if(calendarMonth>11){calendarMonth=0;calendarYear++;}renderAbsenceCalendar()">›</button>
  </div>
  <div class="absence-cal-grid">
    <div class="cal-head">Mo</div><div class="cal-head">Di</div><div class="cal-head">Mi</div>
    <div class="cal-head">Do</div><div class="cal-head">Fr</div>
    <div class="cal-head weekend">Sa</div><div class="cal-head weekend">So</div>`;

  for (let i = 0; i < startDow; i++) html += `<div class="cal-cell empty"></div>`;

  for (let d = 1; d <= daysInMonth; d++) {
    const iso = toISO(d);
    const isToday = iso === today;
    const dow = (startDow + d - 1) % 7;
    const isWeekend = dow >= 5;
    const entries = dayMap[d] || [];
    const dots = entries.map(e => `<span class="cal-dot" style="background:${typeColors[e.type] || '#888'}" title="${escapeHtml(e.name)}: ${e.type}"></span>`).join("");
    const names = entries.length > 0
      ? `<div class="cal-names">${entries.slice(0, 3).map(e => `<span title="${e.type}">${escapeHtml((e.name || "").split(" ").pop() || e.name)}</span>`).join("") + (entries.length > 3 ? `<span>+${entries.length - 3}</span>` : "")}</div>`
      : "";
    html += `<div class="cal-cell${isWeekend ? " weekend" : ""}${isToday ? " today" : ""}${entries.length ? " has-entries" : ""}">
      <span class="cal-day">${d}</span>${dots}${names}
    </div>`;
  }
  html += `</div>
  <div class="cal-legend">
    <span><span class="cal-dot" style="background:#2563eb"></span> Urlaub</span>
    <span><span class="cal-dot" style="background:#c53d2f"></span> Krank</span>
    <span><span class="cal-dot" style="background:#7c3aed"></span> Sonstiges</span>
  </div>`;

  container.innerHTML = html;
}

function renderAbsenceCalendarSection() {
  const existing = document.getElementById("absenceCalendarPanel");
  if (existing) { renderAbsenceCalendar(); return; }
  const section = document.createElement("div");
  section.className = "dashboard-card absence-calendar-section";
  section.innerHTML = `
    <div class="dashboard-card-header">
      <h3 style="margin:0;">📅 Abwesenheitskalender</h3>
    </div>
    <div id="absenceCalendarPanel"><p class="muted" style="padding:16px;">Lädt...</p></div>
  `;
  const leaveSection = document.getElementById("leaveRequestsTable")?.parentElement;
  if (leaveSection) leaveSection.parentElement?.insertBefore(section, leaveSection);
  else (document.querySelector(".main-content") || document.body).appendChild(section);
  renderAbsenceCalendar();
}
"""

if "renderCurrentVisitorsSection" not in content:
    content += new_functions
    open('app.js', 'w', encoding='utf-8', newline='').write(content)
    print("appended OK")
else:
    print("already present")
