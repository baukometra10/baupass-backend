"""Patch app.js:
1. Replace rejectLeaveRequest to use modal
2. Add modal wiring in DOMContentLoaded / init
3. Add leaveExportCsvBtn handler
4. Add renderHrStats() to populate hrStatsGrid on dashboard load
"""
import sys, re

path = "app.js"
content = open(path, "r", encoding="utf-8").read()
original = content

# ─── 1. Replace rejectLeaveRequest with modal version ───────────────────────
OLD_REJECT = '''/**
 * Reject a leave request with optional review note
 */
async function rejectLeaveRequest(requestId) {
  const reason = prompt("Enter rejection reason:");
  if (!reason || reason.trim().length < 3) {
    showAlert("alertApprovalRejectReasonRequired");
    return;
  }

  try {
    const sessionToken = loadStoredSessionToken();
    if (!sessionToken) {
      showAlert("alertSessionExpired");
      return;
    }

    const response = await fetch(`${API_BASE}/api/leave-requests/${requestId}`, {
      method: "PUT",
      headers: {
        "Authorization": `Bearer ${sessionToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ 
        status: "abgelehnt",
        review_note: reason.trim()
      }),
    });

    if (!response.ok) {
      showAlert("alertActionFailed", { error: `HTTP ${response.status}` });
      return;
    }

    showAlert("alertApprovalRejected");
    loadLeaveRequests();
  } catch (error) {
    showAlert("alertActionFailed", { error: String(error) });
  }
}'''

NEW_REJECT = '''function rejectLeaveRequest(requestId) {
  const modal = document.getElementById("leaveRejectModal");
  const note = document.getElementById("leaveRejectNote");
  const confirmBtn = document.getElementById("leaveRejectConfirmBtn");
  const cancelBtn = document.getElementById("leaveRejectCancelBtn");
  if (!modal) return;
  note.value = "";
  modal.classList.remove("hidden");
  note.focus();

  function cleanup() {
    modal.classList.add("hidden");
    confirmBtn.replaceWith(confirmBtn.cloneNode(true));
    cancelBtn.replaceWith(cancelBtn.cloneNode(true));
  }

  document.getElementById("leaveRejectCancelBtn").addEventListener("click", cleanup, { once: true });
  document.getElementById("leaveRejectConfirmBtn").addEventListener("click", async () => {
    cleanup();
    try {
      const sessionToken = loadStoredSessionToken();
      if (!sessionToken) { showAlert("alertSessionExpired"); return; }
      const response = await fetch(`${API_BASE}/api/leave-requests/${requestId}`, {
        method: "PUT",
        headers: { "Authorization": `Bearer ${sessionToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ status: "abgelehnt", review_note: (note.value || "").trim() }),
      });
      if (!response.ok) { showAlert("alertActionFailed", { error: `HTTP ${response.status}` }); return; }
      showToast("Antrag abgelehnt", "info");
      loadLeaveRequests();
    } catch (error) {
      showAlert("alertActionFailed", { error: String(error) });
    }
  }, { once: true });
}'''

if OLD_REJECT not in content:
    print("WARN: old rejectLeaveRequest not found")
else:
    content = content.replace(OLD_REJECT, NEW_REJECT, 1)
    print("✓ rejectLeaveRequest replaced with modal")

# ─── 2. Add modal overlay click-to-close + CSV export wiring ─────────────────
# Find where leaveExportCsvBtn could be wired — add after the section that sets up
# leaveRequestsTable or at the end of DOMContentLoaded init block.
# Find the showToast function and add wiring right before it.
INSERT_BEFORE = "\nfunction showToast(msg, type = 'info') {"

MODAL_AND_CSV_WIRE = """
// ── Leave Reject Modal: close on backdrop click ──
(function() {
  const overlay = document.getElementById("leaveRejectModal");
  if (overlay) {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) overlay.classList.add("hidden");
    });
  }
})();

// ── Leave CSV export button ──
(function() {
  const btn = document.getElementById("leaveExportCsvBtn");
  if (!btn) return;
  btn.addEventListener("click", exportLeaveCsv);
})();

async function exportLeaveCsv() {
  try {
    const sessionToken = loadStoredSessionToken();
    if (!sessionToken) { showAlert("alertSessionExpired"); return; }
    const res = await fetch(`${API_BASE}/api/leave-requests`, {
      headers: { "Authorization": `Bearer ${sessionToken}` }
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const rows = await res.json();
    const cols = ["id","worker_name","first_name","last_name","type","start_date","end_date","days_count","status","review_note","created_at"];
    const header = ["ID","Mitarbeiter","Vorname","Nachname","Art","Von","Bis","Arbeitstage","Status","Entscheidungs-Notiz","Erstellt"];
    const csv = [header.join(";"), ...rows.map(r =>
      cols.map(k => `"${String(r[k] ?? "").replace(/"/g, '""')}"`).join(";")
    )].join("\\r\\n");
    const blob = new Blob(["\\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `urlaubsantraege_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    showAlert("alertActionFailed", { error: String(e) });
  }
}
"""

if INSERT_BEFORE not in content:
    print("WARN: showToast anchor not found, appending modal/csv wiring")
    content += MODAL_AND_CSV_WIRE
else:
    content = content.replace(INSERT_BEFORE, MODAL_AND_CSV_WIRE + INSERT_BEFORE, 1)
    print("✓ modal close + CSV export wired")

# ─── 3. Add renderHrStats function ───────────────────────────────────────────
HR_STATS_FN = """
async function renderHrStats() {
  const container = document.getElementById("hrStatsGrid");
  if (!container) return;
  try {
    const sessionToken = loadStoredSessionToken();
    if (!sessionToken) return;
    const res = await fetch(`${API_BASE}/api/leave-requests?status=ausstehend`, {
      headers: { "Authorization": `Bearer ${sessionToken}` }
    });
    if (!res.ok) return;
    const pending = await res.json();
    const pendingCount = Array.isArray(pending) ? pending.length : 0;
    updateLeavePendingBadge(pendingCount);
    container.innerHTML = `
      <article class="stat-card${pendingCount > 0 ? " stat-card-critical" : ""}" style="cursor:pointer;" onclick="setView('leave')" title="Zu den Urlaubsanträgen">
        <p>Offene Urlaubsanträge</p>
        <strong>${pendingCount}</strong>
      </article>`;
  } catch (_) { /* silent */ }
}
"""

# Insert before renderStats
insert_anchor = "\nfunction renderStats() {"
if insert_anchor not in content:
    print("WARN: renderStats anchor not found, appending renderHrStats")
    content += HR_STATS_FN
else:
    content = content.replace(insert_anchor, HR_STATS_FN + insert_anchor, 1)
    print("✓ renderHrStats added before renderStats")

# ─── 4. Call renderHrStats() when setView("dashboard") is called ─────────────
# Existing setView has targetView === "devices" → add "dashboard" block
OLD_SETVIEW_END = '  if (targetView === "leave") {\n    loadLeaveRequests();\n  }\n}'
NEW_SETVIEW_END = '  if (targetView === "leave") {\n    loadLeaveRequests();\n  }\n  if (targetView === "dashboard") {\n    void renderHrStats();\n  }\n}'

if OLD_SETVIEW_END not in content:
    print("WARN: setView leave block not found")
else:
    content = content.replace(OLD_SETVIEW_END, NEW_SETVIEW_END, 1)
    print("✓ setView dashboard calls renderHrStats")

# Also call on initial load — find where renderStats() is called after login
# Find renderStats(); and add renderHrStats() after it (first occurrence after DOMContentLoaded)
import re
pattern = r'(renderStats\(\);)'
matches = list(re.finditer(pattern, content))
if matches:
    m = matches[0]
    pos = m.end()
    content = content[:pos] + "\n  void renderHrStats();" + content[pos:]
    print("✓ renderHrStats() called after initial renderStats()")
else:
    print("WARN: renderStats() call not found")

if content == original:
    print("WARN: No changes made")
    sys.exit(1)

open(path, "w", encoding="utf-8").write(content)
print("patched OK")
