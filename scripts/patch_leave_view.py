"""Patch app.js to:
1. Add 'leave' to getAllowedViewsForRole
2. Call loadLeaveRequests when leave view is activated in setView
3. Replace renderLeaveRequestsTable with better German version
4. Add updateLeavePendingBadge function
"""
import sys, re

path = "app.js"
content = open(path, "r", encoding="utf-8").read()
original = content

# ─── 1. getAllowedViewsForRole: add 'leave' for superadmin + company-admin ───
old1 = '    return ["dashboard", "workers", "badge", "access", "documents", "invoices", "admin", "devices"];'
new1 = '    return ["dashboard", "workers", "badge", "access", "documents", "invoices", "admin", "devices", "leave"];'
if old1 not in content:
    print("WARN: superadmin views line not found, skipping")
else:
    content = content.replace(old1, new1, 1)
    print("✓ superadmin views patched")

old2 = '    return ["dashboard", "workers", "badge", "access", "documents"];'
new2 = '    return ["dashboard", "workers", "badge", "access", "documents", "leave"];'
if old2 not in content:
    print("WARN: company-admin views line not found, skipping")
else:
    content = content.replace(old2, new2, 1)
    print("✓ company-admin views patched")

# ─── 2. setView: call loadLeaveRequests when leave view activated ───
old3 = '  if (targetView === "devices") {\n    loadDevices();\n  }\n}'
new3 = '  if (targetView === "devices") {\n    loadDevices();\n  }\n  if (targetView === "leave") {\n    loadLeaveRequests();\n  }\n}'
if old3 not in content:
    print("WARN: setView devices block not found, skipping")
else:
    content = content.replace(old3, new3, 1)
    print("✓ setView patched")

# ─── 3. Replace renderLeaveRequestsTable with improved German version ───
old_render_start = 'function renderLeaveRequestsTable(requests, filterStatus = null) {'
old_render_end = '\nfunction createLeaveRequestsPanel() {'

idx_start = content.find(old_render_start)
idx_end = content.find(old_render_end)

if idx_start == -1 or idx_end == -1:
    print("WARN: renderLeaveRequestsTable not found, skipping")
else:
    new_render = '''function renderLeaveRequestsTable(requests, filterStatus = null) {
  const container = document.getElementById("leaveRequestsTable") || createLeaveRequestsPanel();

  const filtered = filterStatus
    ? requests.filter(req => req.status === filterStatus)
    : requests;

  const pending = requests.filter(r => r.status === "ausstehend").length;
  updateLeavePendingBadge(pending);

  const typeLabel = (t) => ({ urlaub: "Urlaub", krank: "Krank", sonderurlaub: "Sonderurlaub", unbezahlt: "Unbezahlt" }[t] || t || "–");
  const statusLabel = (s) => ({ ausstehend: "Ausstehend", genehmigt: "Genehmigt", abgelehnt: "Abgelehnt" }[s] || s || "–");
  const statusIcon = (s) => ({ ausstehend: "⏳", genehmigt: "✓", abgelehnt: "✗" }[s] || "");

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="leave-filter-bar">
        <button class="btn-filter${!filterStatus ? " active" : ""}" onclick="loadLeaveRequests()">Alle</button>
        <button class="btn-filter${filterStatus === "ausstehend" ? " active" : ""}" onclick="loadLeaveRequests(\'ausstehend\')">Ausstehend${pending > 0 ? ` (${pending})` : ""}</button>
        <button class="btn-filter${filterStatus === "genehmigt" ? " active" : ""}" onclick="loadLeaveRequests(\'genehmigt\')">Genehmigt</button>
        <button class="btn-filter${filterStatus === "abgelehnt" ? " active" : ""}" onclick="loadLeaveRequests(\'abgelehnt\')">Abgelehnt</button>
      </div>
      <p class="muted-info" style="padding:16px;">Keine Anträge gefunden.</p>`;
    return;
  }

  container.innerHTML = `
    <div class="leave-filter-bar">
      <button class="btn-filter${!filterStatus ? " active" : ""}" onclick="loadLeaveRequests()">Alle (${requests.length})</button>
      <button class="btn-filter${filterStatus === "ausstehend" ? " active" : ""}" onclick="loadLeaveRequests(\'ausstehend\')">⏳ Ausstehend${pending > 0 ? ` (${pending})` : ""}</button>
      <button class="btn-filter${filterStatus === "genehmigt" ? " active" : ""}" onclick="loadLeaveRequests(\'genehmigt\')">✓ Genehmigt</button>
      <button class="btn-filter${filterStatus === "abgelehnt" ? " active" : ""}" onclick="loadLeaveRequests(\'abgelehnt\')">✗ Abgelehnt</button>
    </div>
    <div class="leave-cards-grid">
      ${filtered.map(req => `
        <div class="leave-card leave-card-${req.status || "ausstehend"}">
          <div class="leave-card-header">
            <span class="leave-card-worker">${escapeHtml(req.worker_name || (req.first_name ? req.first_name + " " + req.last_name : req.worker_id) || "–")}</span>
            <span class="leave-card-status leave-status-${req.status}">${statusIcon(req.status)} ${statusLabel(req.status)}</span>
          </div>
          <div class="leave-card-type">${typeLabel(req.type)}</div>
          <div class="leave-card-dates">
            ${req.start_date} → ${req.end_date}
            ${req.days_count ? `<span class="leave-card-days">${req.days_count} Arbeitstag${req.days_count !== 1 ? "e" : ""}</span>` : ""}
          </div>
          ${req.note ? `<div class="leave-card-note">Hinweis: ${escapeHtml(req.note)}</div>` : ""}
          ${req.review_note ? `<div class="leave-card-review-note">Entscheidung: ${escapeHtml(req.review_note)}</div>` : ""}
          ${req.email_forwarded_to ? `<div class="leave-card-forwarded">📧 ${escapeHtml(req.email_forwarded_to)}</div>` : ""}
          ${req.status === "ausstehend" ? `
            <div class="leave-card-actions">
              <button class="btn-small btn-approve" onclick="approveLeaveRequest(${req.id})">✓ Genehmigen</button>
              <button class="btn-small btn-danger" onclick="rejectLeaveRequest(${req.id})">✗ Ablehnen</button>
            </div>` : ""}
        </div>
      `).join("")}
    </div>
  `;
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
}
'''
    content = content[:idx_start] + new_render + content[idx_end:]
    print("✓ renderLeaveRequestsTable replaced with card layout")

# ─── 4. Fix approveLeaveRequest / rejectLeaveRequest to use German alerts ───
old_approve = "    alert('Request approved');\n    loadLeaveRequests();"
new_approve = "    showToast('Antrag genehmigt', 'success');\n    loadLeaveRequests();"
if old_approve in content:
    content = content.replace(old_approve, new_approve, 1)
    print("✓ approve alert replaced with toast")

old_reject = "    alert('Request rejected');\n    loadLeaveRequests();"
new_reject = "    showToast('Antrag abgelehnt', 'info');\n    loadLeaveRequests();"
if old_reject in content:
    content = content.replace(old_reject, new_reject, 1)
    print("✓ reject alert replaced with toast")

# Check if showToast exists, if not add a simple one near the end
if "function showToast" not in content:
    content += """
function showToast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = 'admin-toast admin-toast-' + type;
  el.textContent = msg;
  document.body.appendChild(el);
  requestAnimationFrame(() => el.classList.add('admin-toast-show'));
  setTimeout(() => {
    el.classList.remove('admin-toast-show');
    el.addEventListener('transitionend', () => el.remove(), { once: true });
    setTimeout(() => { if (el.parentNode) el.remove(); }, 500);
  }, 2800);
}
"""
    print("✓ showToast added")

if content == original:
    print("WARN: No changes made")
else:
    open(path, "w", encoding="utf-8").write(content)
    print("patched OK")
