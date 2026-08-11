/** Optional shell features — loaded idle after app.js (safe lazy chunk). */
// ── Manual Entry Modal ──────────────────────────────────────────────────────
(function initManualEntryModal() {
  const btn = document.getElementById("manualEntryBtn");
  const modal = document.getElementById("manualEntryModal");
  const closeBtn = document.getElementById("manualEntryClose");
  const searchInput = document.getElementById("manualEntrySearch");
  const listEl = document.getElementById("manualEntryList");
  const feedbackEl = document.getElementById("manualEntryFeedback");
  const workTimePanel = document.getElementById("manualEntryWorkTimePanel");
  const workStartInput = document.getElementById("manualEntryWorkStart");
  const workEndInput = document.getElementById("manualEntryWorkEnd");
  const workTimeSaveBtn = document.getElementById("manualEntryWorkTimeSave");
  const workTimesTitle = document.getElementById("manualEntryWorkTimeTitle");
  const workStartLabel = document.getElementById("manualEntryWorkStartLabel");
  const workEndLabel = document.getElementById("manualEntryWorkEndLabel");
  const workTimeStatus = document.getElementById("manualEntryWorkTimeStatus");
  const accessModeInput = document.getElementById("manualEntryAccessMode");
  const siteRadiusInput = document.getElementById("manualEntrySiteRadius");
  const siteAutoProximityInput = document.getElementById("manualEntrySiteAutoProximity");
  const contextHint = document.getElementById("manualEntryContextHint");

  if (!btn || !modal) return;

  // ── helpers ──────────────────────────────────────────────────────────────

  function getEffectiveWorkTimes() {
    const companyId = getEffectiveUiCompanyId();
    const company = companyId ? state.companies.find((c) => c.id === companyId) : null;
    const start = String(company?.workStartTime || company?.work_start_time || state.settings?.workStartTime || "").trim();
    const end   = String(company?.workEndTime   || company?.work_end_time   || state.settings?.workEndTime   || "").trim();
    return { start, end, companyId, company };
  }

  if (accessModeInput) {
    accessModeInput.addEventListener("change", () => {
      if (siteRadiusInput) siteRadiusInput.disabled = accessModeInput.value !== "site_app";
      if (siteAutoProximityInput) siteAutoProximityInput.disabled = accessModeInput.value !== "site_app";
    });
  }

  function isWorkerLate(w) {
    const { start } = getEffectiveWorkTimes();
    if (!start) return false;
    const latest = getLatestAccessForWorker(w.id);
    if (isWorkerPresentOnSite(latest?.direction)) return false; // already in
    const [hh, mm] = start.split(":").map(Number);
    const now = new Date();
    return (now.getHours() * 60 + now.getMinutes()) > (hh * 60 + mm);
  }

  function syncWorkTimePanel() {
    if (!workTimePanel) return;
    const role = String(getCurrentUser()?.role || "").toLowerCase();
    const canEdit = ["company-admin", "company_admin"].includes(role);
    if (!canEdit) { workTimePanel.classList.add("hidden"); return; }

    const { start, end, companyId, company } = getEffectiveWorkTimes();
    workTimePanel.classList.toggle("hidden", !companyId);
    if (!companyId) return;

    if (workTimesTitle) workTimesTitle.textContent = runtimeText("manualEntryWorkTimesTitle");
    if (workStartLabel) workStartLabel.textContent = runtimeText("workStartTimeLabel");
    if (workEndLabel)   workEndLabel.textContent   = runtimeText("workEndTimeLabel");
    if (workTimeSaveBtn) workTimeSaveBtn.textContent = runtimeText("manualEntryWorkTimesSaveBtn");
    if (workStartInput) workStartInput.value = start;
    if (workEndInput)   workEndInput.value   = end;
    const accessMode = String(company?.access_mode || company?.accessMode || "gate").trim().toLowerCase();
    if (accessModeInput) accessModeInput.value = accessMode === "site_app" ? "site_app" : "gate";
    if (siteRadiusInput) {
      siteRadiusInput.value = String(company?.site_geofence_radius_meters || company?.siteGeofenceRadiusMeters || 10);
      siteRadiusInput.disabled = accessModeInput?.value !== "site_app";
    }
    if (siteAutoProximityInput) {
      const enabled = company?.site_auto_proximity_login ?? company?.siteAutoProximityLogin;
      siteAutoProximityInput.checked = enabled !== false && enabled !== 0 && enabled !== "0";
      siteAutoProximityInput.disabled = accessModeInput?.value !== "site_app";
    }

    if (workTimeStatus) {
      const now = new Date();
      const timeStr = now.toTimeString().slice(0, 5);
      if (start && end) {
        const active = timeStr >= start && timeStr <= end;
        workTimeStatus.textContent = active ? `✅ ${start}–${end}` : `⏸ ${start}–${end}`;
        workTimeStatus.className = `manual-entry-worktime-status ${active ? "active" : "inactive"}`;
      } else {
        workTimeStatus.textContent = "";
      }
    }
  }

  // ── work time save ────────────────────────────────────────────────────────
  if (workTimeSaveBtn) {
    workTimeSaveBtn.addEventListener("click", async () => {
      const { companyId } = getEffectiveWorkTimes();
      if (!companyId) {
        if (feedbackEl) {
          feedbackEl.textContent = runtimeText("manualEntryWorkTimesMissingCompany");
          feedbackEl.className = "manual-entry-feedback error";
          feedbackEl.classList.remove("hidden");
        }
        return;
      }
      workTimeSaveBtn.disabled = true;
      try {
        const toHm = (v) => String(v || "").trim().slice(0, 5);
        await apiRequest(`${API_BASE}/api/companies/${companyId}/work-times`, {
          method: "PUT",
          body: {
            workStartTime: toHm(workStartInput?.value),
            workEndTime: toHm(workEndInput?.value),
            accessMode: accessModeInput?.value || "gate",
            siteGeofenceRadiusMeters: Number(siteRadiusInput?.value || 10),
            siteAutoCheckin: true,
            siteAutoLogoutOnLeave: true,
            siteAutoProximityLogin: Boolean(siteAutoProximityInput?.checked),
          },
        });
        // Update local state so UI reflects immediately
        const comp = state.companies.find((c) => c.id === companyId);
        if (comp) {
          comp.workStartTime = workStartInput?.value || "";
          comp.work_start_time = comp.workStartTime;
          comp.workEndTime   = workEndInput?.value   || "";
          comp.work_end_time = comp.workEndTime;
          comp.access_mode = accessModeInput?.value || "gate";
          comp.accessMode = comp.access_mode;
          comp.site_geofence_radius_meters = Number(siteRadiusInput?.value || 10);
          comp.siteGeofenceRadiusMeters = comp.site_geofence_radius_meters;
          comp.site_auto_proximity_login = siteAutoProximityInput?.checked ? 1 : 0;
          comp.siteAutoProximityLogin = Boolean(siteAutoProximityInput?.checked);
        }
        if (feedbackEl) {
          feedbackEl.textContent = runtimeText("manualEntryWorkTimesSaved");
          feedbackEl.className = "manual-entry-feedback success";
          feedbackEl.classList.remove("hidden");
          setTimeout(() => feedbackEl.classList.add("hidden"), 2500);
        }
        syncWorkTimePanel();
        renderList(searchInput.value);
      } catch (e) {
        if (feedbackEl) {
          feedbackEl.textContent = runtimeText("manualEntryWorkTimesSaveFailed").replace("{error}", e.message || "?");
          feedbackEl.className = "manual-entry-feedback error";
          feedbackEl.classList.remove("hidden");
        }
      } finally {
        workTimeSaveBtn.disabled = false;
      }
    });
  }

  // ── open / close ──────────────────────────────────────────────────────────

  function openModal() {
    modal.classList.remove("hidden");
    searchInput.value = "";
    searchInput.placeholder = runtimeText("manualEntrySearch");
    feedbackEl.classList.add("hidden");
    syncWorkTimePanel();

    // Context hint: "Aktiv auf der Baustelle" or "im Gebäude"
    if (contextHint) {
      const companyId = getEffectiveUiCompanyId();
      const company = companyId ? state.companies.find((c) => c.id === companyId) : null;
      const preset = String(company?.brandingPreset || company?.branding_preset || "construction").trim().toLowerCase();
      const key = preset === "construction" ? "manualEntryContextSite" : "manualEntryContextBuilding";
      contextHint.textContent = runtimeText(key);
      contextHint.className = `manual-entry-context-hint${companyId ? "" : " hidden"}`;
    }

    renderList("");
    searchInput.focus();
  }

  function closeModal() {
    modal.classList.add("hidden");
  }

  // ── list rendering ────────────────────────────────────────────────────────

  function renderList(query) {
    const q = query.trim().toLowerCase();
    const workers = getUiVisibleWorkers().filter((w) => {
      const status = String(w.status || "").trim().toLowerCase();
      if (status === "gesperrt" || status === "abgelaufen") return false;
      if (q.length < 1) return true;
      const full = `${w.firstName} ${w.lastName} ${w.badgeId}`.toLowerCase();
      return full.includes(q);
    }).sort((a, b) => {
      const aIn = isWorkerPresentOnSite(getLatestAccessForWorker(a.id)?.direction);
      const bIn = isWorkerPresentOnSite(getLatestAccessForWorker(b.id)?.direction);
      if (aIn !== bIn) return aIn ? 1 : -1;
      const aLate = isWorkerLate(a);
      const bLate = isWorkerLate(b);
      if (aLate !== bLate) return aLate ? -1 : 1; // late workers first
      return `${a.firstName} ${a.lastName}`.localeCompare(`${b.firstName} ${b.lastName}`, "de");
    });

    if (!workers.length) {
      listEl.innerHTML = `<p class="manual-entry-empty">${runtimeText("manualEntryNoResults")}</p>`;
      return;
    }

    listEl.innerHTML = workers.slice(0, 40).map((w) => {
      const company = state.companies.find((c) => c.id === w.companyId);
      const photo = sanitizeImageSrc(w.photoData, createAvatar(w));
      const name = escapeHtml(`${w.firstName} ${w.lastName}`);
      const companyName = escapeHtml(company?.name || "");
      const badgeId = escapeHtml(w.badgeId);
      const latest = getLatestAccessForWorker(w.id);
      const isCheckedIn = isWorkerPresentOnSite(latest?.direction);
      const late = isWorkerLate(w);
      const statusPill = latest
        ? `<span class="status-pill manual-entry-status ${isCheckedIn ? "status-active" : "status-inactive"}">${isCheckedIn ? runtimeText("dashboardDirectionCheckin") : runtimeText("dashboardDirectionCheckout")}</span>`
        : "";
      const latePill = late
        ? `<span class="status-pill status-late manual-entry-late-pill">${runtimeText("checkedInLate")}</span>`
        : "";
      const checkinClass = isCheckedIn ? "ghost-button" : "primary-button";
      const checkoutClass = isCheckedIn ? "primary-button" : "ghost-button";
      return `
        <div class="manual-entry-row${late ? " manual-entry-row-late" : ""}" data-worker-id="${escapeHtml(w.id)}">
          <img class="manual-entry-photo" src="${photo}" alt="${name}" />
          <div class="manual-entry-info">
            <strong>${name}</strong>
            <span>${companyName}</span>
            <span class="manual-entry-badge">${badgeId}</span>
            <div class="manual-entry-pills">${statusPill}${latePill}</div>
          </div>
          <div class="manual-entry-actions">
            <button type="button" class="${checkinClass} manual-entry-checkin" data-worker-id="${escapeHtml(w.id)}" data-direction="check-in">${runtimeText("manualEntryCheckin")}</button>
            <button type="button" class="${checkoutClass} manual-entry-checkout" data-worker-id="${escapeHtml(w.id)}" data-direction="check-out">${runtimeText("manualEntryCheckout")}</button>
          </div>
        </div>`;
    }).join("");

    listEl.querySelectorAll("[data-worker-id][data-direction]").forEach((actionBtn) => {
      actionBtn.addEventListener("click", async () => {
        const worker = state.workers.find((wr) => wr.id === actionBtn.dataset.workerId);
        if (!worker) return;
        const direction = actionBtn.dataset.direction;
        const gate = document.getElementById("accessGate")?.value || "Pforte";
        const note = direction === "check-in"
          ? runtimeText("manualEntryNoteCheckin") || "Manueller Einlass – Ausweis/Telefon vergessen"
          : runtimeText("manualEntryNoteCheckout") || "Manueller Auslass – Ausweis/Telefon vergessen";
        const result = await bookAccess(worker.id, direction, gate, note, { skipFeedbackOverlay: true });
        const workerName = `${worker.firstName} ${worker.lastName}`;
        if (result && result.ok === false && result.reason === "duplicate_direction") {
          feedbackEl.textContent = result.message;
          feedbackEl.className = "manual-entry-feedback error";
          feedbackEl.classList.remove("hidden");
          renderList(searchInput.value);
        } else if (result === undefined || (result && result.ok !== false)) {
          const successKey = direction === "check-in" ? "manualEntrySuccess" : "manualEntryCheckoutSuccess";
          feedbackEl.textContent = runtimeText(successKey).replace("{name}", workerName);
          feedbackEl.className = "manual-entry-feedback success";
          feedbackEl.classList.remove("hidden");
          renderList(searchInput.value);
          setTimeout(closeModal, 2200);
        } else {
          feedbackEl.textContent = runtimeText("manualEntryError") || "Fehler beim Buchen.";
          feedbackEl.className = "manual-entry-feedback error";
          feedbackEl.classList.remove("hidden");
        }
      });
    });
  }

  // ── event listeners ───────────────────────────────────────────────────────
  btn.addEventListener("click", openModal);
  closeBtn.addEventListener("click", closeModal);
  modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });
  searchInput.addEventListener("input", () => renderList(searchInput.value));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.classList.contains("hidden")) closeModal();
  });

  // Hide button for turnstile role (they have NFC-scan flow)
  function syncManualEntryBtnVisibility() {
    const role = getCurrentUser()?.role || "";
    btn.style.display = role === "turnstile" ? "none" : "";
  }
  syncManualEntryBtnVisibility();
  window._syncManualEntryBtnVisibility = syncManualEntryBtnVisibility;
  btn.dataset.secondaryReady = "1";

  // Refresh list + work-time panel if modal is open when refreshAll() runs
  window._refreshManualEntryListIfOpen = function () {
    if (!modal.classList.contains("hidden")) {
      syncWorkTimePanel();
      renderList(searchInput.value);
    }
  };
})();
