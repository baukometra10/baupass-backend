path = "app.js"
c = open(path,"r",encoding="utf-8").read()

OLD = """async function rejectLeaveRequest(id) {
  const reason = prompt('Enter rejection reason:');
  if (!reason) return;
  
  try {
    const sessionToken = loadStoredSessionToken();
    const response = await fetch(`${API_BASE}/api/leave-requests/${id}`, {
      method: "PUT",
      headers: {
        "Authorization": `Bearer ${sessionToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ status: "abgelehnt", review_note: reason }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    showToast('Antrag abgelehnt', 'info');
    loadLeaveRequests();
  } catch (error) {
    alert('Error: ' + error.message);
  }
}

/**
 * Export timesheets CSV
 */"""

NEW = """function rejectLeaveRequest(requestId) {
  const modal = document.getElementById("leaveRejectModal");
  const noteEl = document.getElementById("leaveRejectNote");
  if (!modal) return;
  noteEl.value = "";
  modal.classList.remove("hidden");
  noteEl.focus();

  function cleanup() {
    modal.classList.add("hidden");
    const c = document.getElementById("leaveRejectConfirmBtn");
    const x = document.getElementById("leaveRejectCancelBtn");
    if (c) { const nc = c.cloneNode(true); c.replaceWith(nc); }
    if (x) { const nx = x.cloneNode(true); x.replaceWith(nx); }
  }

  document.getElementById("leaveRejectCancelBtn").addEventListener("click", cleanup, { once: true });
  document.getElementById("leaveRejectConfirmBtn").addEventListener("click", async () => {
    const note = (noteEl.value || "").trim();
    cleanup();
    try {
      const sessionToken = loadStoredSessionToken();
      if (!sessionToken) { showAlert("alertSessionExpired"); return; }
      const response = await fetch(`${API_BASE}/api/leave-requests/${requestId}`, {
        method: "PUT",
        headers: { "Authorization": `Bearer ${sessionToken}`, "Content-Type": "application/json" },
        body: JSON.stringify({ status: "abgelehnt", review_note: note }),
      });
      if (!response.ok) { showAlert("alertActionFailed", { error: `HTTP ${response.status}` }); return; }
      showToast("Antrag abgelehnt", "info");
      loadLeaveRequests();
    } catch (error) {
      showAlert("alertActionFailed", { error: String(error) });
    }
  }, { once: true });
}

/**
 * Export timesheets CSV
 */"""

if OLD not in c:
    print("ERROR: not found")
else:
    c = c.replace(OLD, NEW, 1)
    open(path,"w",encoding="utf-8").write(c)
    print("patched OK")
