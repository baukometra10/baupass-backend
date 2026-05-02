"""Replace the full loadLeaveRequests function with a clean card-based version
that targets the #leaveRequestsTable container in the new leave view."""
import sys

path = "app.js"
content = open(path, "r", encoding="utf-8").read()

OLD = """async function loadLeaveRequests(filterStatus = null) {
  try {
    const sessionToken = loadStoredSessionToken();
    if (!sessionToken) {
      alert('Session expired. Please sign in again.');
      return;
    }

    const response = await fetch(`${API_BASE}/api/leave-requests`, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${sessionToken}`,
        "Content-Type": "application/json",
      },
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const requests = await response.json();
    
    const filtered = filterStatus ? requests.filter(r => r.status === filterStatus) : requests;
    const html = `
      <div class="leave-requests-section">
        <h3>Leave Requests</h3>
        <table>
          <tr><th>Mitarbeiter</th><th>Art</th><th>Von</th><th>Bis</th><th>Tage</th><th>Status</th><th>Aktion</th></tr>
          ${filtered.map(req => `
            <tr>
              <td>${req.worker_name || req.first_name + ' ' + req.last_name || 'N/A'}</td>
              <td>${req.type === 'urlaub' ? 'Urlaub' : req.type === 'krank' ? 'Krank' : req.type || 'N/A'}</td>
              <td>${req.start_date}</td>
              <td>${req.end_date}</td>
              <td>${req.days_count > 0 ? req.days_count : '-'}</td>
              <td>${req.status}${req.email_forwarded_to ? `<br><span class="leave-forwarded-badge" title="An ${escapeHtml(req.email_forwarded_to)} weitergeleitet">📧 ${escapeHtml(req.email_forwarded_to)}</span>` : ""}</td>
              <td>${req.status === 'ausstehend' ? `<button onclick="approveLeaveRequest(${req.id})">Approve</button><button onclick="rejectLeaveRequest(${req.id})">Reject</button>` : '-'}</td>
            </tr>
          `).join('')}
        </table>
      </div>
    `;
    const container = document.getElementById('adminPanel') || document.body;
    container.innerHTML += html;
    renderAbsenceCalendarSection();
    renderCurrentVisitorsSection();
  } catch (error) {
    alert('Error loading leave requests: ' + error.message);
  }
}"""

NEW = """async function loadLeaveRequests(filterStatus = null) {
  const container = document.getElementById("leaveRequestsTable");
  if (container) container.innerHTML = '<p class="muted-info" style="padding:16px;">Lade Daten…</p>';
  try {
    const sessionToken = loadStoredSessionToken();
    if (!sessionToken) { showAlert("alertSessionExpired"); return; }

    const response = await fetch(`${API_BASE}/api/leave-requests`, {
      method: "GET",
      headers: { "Authorization": `Bearer ${sessionToken}`, "Content-Type": "application/json" },
    });
    if (!response.ok) {
      if (response.status === 401) { showAlert("alertSessionExpired"); return; }
      throw new Error(`HTTP ${response.status}`);
    }
    const requests = await response.json();
    renderLeaveRequestsTable(requests, filterStatus);
  } catch (error) {
    if (container) container.innerHTML = '<p class="muted-info" style="padding:16px;">Fehler beim Laden.</p>';
    console.warn("loadLeaveRequests:", error);
  }
}

function renderLeaveRequestsTable(requests, filterStatus = null) {
  const container = document.getElementById("leaveRequestsTable");
  if (!container) return;

  const filtered = filterStatus ? requests.filter(r => r.status === filterStatus) : requests;
  const pending = requests.filter(r => r.status === "ausstehend").length;
  updateLeavePendingBadge(pending);

  const typeLabel = (t) => ({ urlaub: "Urlaub", krank: "Krank", sonderurlaub: "Sonderurlaub", unbezahlt: "Unbezahlt" }[t] || t || "–");
  const statusLabel = (s) => ({ ausstehend: "Ausstehend", genehmigt: "Genehmigt", abgelehnt: "Abgelehnt" }[s] || s || "–");
  const statusIcon = (s) => ({ ausstehend: "⏳", genehmigt: "✓", abgelehnt: "✗" }[s] || "");

  const filterBar = `
    <div class="leave-filter-bar">
      <button class="btn-filter${!filterStatus ? " active" : ""}" onclick="loadLeaveRequests()">Alle (${requests.length})</button>
      <button class="btn-filter${filterStatus === "ausstehend" ? " active" : ""}" onclick="loadLeaveRequests('ausstehend')">⏳ Ausstehend${pending > 0 ? ` (${pending})` : ""}</button>
      <button class="btn-filter${filterStatus === "genehmigt" ? " active" : ""}" onclick="loadLeaveRequests('genehmigt')">✓ Genehmigt</button>
      <button class="btn-filter${filterStatus === "abgelehnt" ? " active" : ""}" onclick="loadLeaveRequests('abgelehnt')">✗ Abgelehnt</button>
    </div>`;

  if (filtered.length === 0) {
    container.innerHTML = filterBar + '<p class="muted-info" style="padding:16px;">Keine Anträge gefunden.</p>';
    return;
  }

  container.innerHTML = filterBar + `
    <div class="leave-cards-grid">
      ${filtered.map(req => `
        <div class="leave-card leave-card-${req.status || "ausstehend"}">
          <div class="leave-card-header">
            <span class="leave-card-worker">${escapeHtml(req.worker_name || (req.first_name ? req.first_name + " " + req.last_name : String(req.worker_id || "–")))}</span>
            <span class="leave-card-status leave-status-${req.status}">${statusIcon(req.status)} ${statusLabel(req.status)}</span>
          </div>
          <div class="leave-card-type">${typeLabel(req.type)}</div>
          <div class="leave-card-dates">
            ${req.start_date} → ${req.end_date}
            ${req.days_count > 0 ? `<span class="leave-card-days">${req.days_count} AT</span>` : ""}
          </div>
          ${req.note ? `<div class="leave-card-note">${escapeHtml(req.note)}</div>` : ""}
          ${req.review_note ? `<div class="leave-card-review-note">📋 ${escapeHtml(req.review_note)}</div>` : ""}
          ${req.email_forwarded_to ? `<div class="leave-card-forwarded">📧 ${escapeHtml(req.email_forwarded_to)}</div>` : ""}
          ${req.status === "ausstehend" ? `
            <div class="leave-card-actions">
              <button class="btn-small btn-approve" onclick="approveLeaveRequest(${req.id})">✓ Genehmigen</button>
              <button class="btn-small btn-danger" onclick="rejectLeaveRequest(${req.id})">✗ Ablehnen</button>
            </div>` : ""}
        </div>
      `).join("")}
    </div>`;
}

function updateLeavePendingBadge(count) {
  const badge = document.getElementById("leavePendingBadge");
  if (!badge) return;
  if (count > 0) {
    badge.textContent = count;
    badge.classList.remove("hidden");
  } else {
    badge.classList.add("hidden");
  }
}"""

if OLD not in content:
    print("ERROR: old loadLeaveRequests not found exactly")
    # Try partial match to debug
    first_line = OLD.split('\n')[0]
    idx = content.find(first_line)
    print(f"First line found at: {idx}")
    if idx != -1:
        print("Context:", repr(content[idx:idx+200]))
    sys.exit(1)

content = content.replace(OLD, NEW, 1)
open(path, "w", encoding="utf-8").write(content)
print("patched OK")
