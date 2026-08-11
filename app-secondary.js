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

// ── Dunning manuell auslösen ────────────────────────────────────────────────
const triggerDunningBtn = document.querySelector("#triggerDunningBtn");
if (triggerDunningBtn) {
  triggerDunningBtn.addEventListener("click", async () => {
    if (!(await showConfirmDialog(runtimeText("dunningRunConfirm")))) return;
    triggerDunningBtn.disabled = true;
    try {
      const result = await apiRequest(`${API_BASE}/api/invoices/trigger-dunning`, { method: "POST", body: {} });
      showToast(runtimeTextTemplate("dunningRunResult", { count: result.result?.remindersSent || 0 }), "success");
      await loadAndRenderInvoices();
      refreshAll();
    } catch (error) {
      showToast(runtimeTextTemplate("genericErrorPrefix", { message: error.message }), "error", 3600);
    } finally {
      triggerDunningBtn.disabled = false;
    }
  });
}

const triggerMonthlyInvoiceBtn = document.querySelector("#triggerMonthlyInvoiceBtn");
if (triggerMonthlyInvoiceBtn) {
  triggerMonthlyInvoiceBtn.addEventListener("click", async () => {
    if (!(await showConfirmDialog(runtimeText("monthlyInvoiceRunConfirm")))) return;
    triggerMonthlyInvoiceBtn.disabled = true;
    try {
      const result = await apiRequest(`${API_BASE}/api/invoices/trigger-monthly-cycle`, { method: "POST", body: {} });
      showToast(runtimeTextTemplate("monthlyInvoiceRunResult", {
        created: String(result.result?.created || 0),
        sent: String(result.result?.sent || 0),
        skipped: String(result.result?.skipped || 0),
        failed: String(result.result?.failed || 0),
      }), "success", 3800);
      await loadAndRenderInvoices();
      refreshAll();
    } catch (error) {
      showToast(runtimeTextTemplate("genericErrorPrefix", { message: error.message }), "error", 3600);
    } finally {
      triggerMonthlyInvoiceBtn.disabled = false;
    }
  });
}

const simulateCurrentMonthBtn = document.querySelector("#simulateCurrentMonthBtn");
if (simulateCurrentMonthBtn) {
  simulateCurrentMonthBtn.addEventListener("click", async () => {
    if (!(await showConfirmDialog(runtimeText("simulateMonthlyRunConfirm")))) return;
    simulateCurrentMonthBtn.disabled = true;
    try {
      const result = await apiRequest(`${API_BASE}/api/invoices/simulate-monthly-cycle`, { method: "POST", body: {} });
      showToast(runtimeTextTemplate("simulateMonthlyRunResult", {
        created: String(result.result?.created || 0),
        sent: String(result.result?.sent || 0),
        skipped: String(result.result?.skipped || 0),
        failed: String(result.result?.failed || 0),
      }), "success", 3800);
      await loadAndRenderInvoices();
      refreshAll();
    } catch (error) {
      showToast(runtimeTextTemplate("genericErrorPrefix", { message: error.message }), "error", 3600);
    } finally {
      simulateCurrentMonthBtn.disabled = false;
    }
  });
}

const exportCompanyDocEmailsBtn = document.querySelector("#exportCompanyDocEmailsBtn");
if (exportCompanyDocEmailsBtn) {
  exportCompanyDocEmailsBtn.addEventListener("click", async () => {
    if (!token) {
      handleExpiredControlSession();
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/api/companies/document-emails/export`, {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (!response.ok) {
        let payload = {};
        try {
          payload = await response.json();
        } catch {
          payload = {};
        }
        throw new Error(payload?.error || `http_${response.status}`);
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `company-document-emails-${new Date().toISOString().slice(0, 10)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      showToast(uiT("alertExportFailed").replace("{error}", error.message));
    }
  });
}

const collectionsFilter = document.querySelector("#collectionsFilter");
if (collectionsFilter) {
  collectionsFilter.addEventListener("change", () => renderCollectionsList());
}

const printDailyReportButton = document.querySelector("#printDailyReportButton");
if (printDailyReportButton) {
  printDailyReportButton.addEventListener("click", printDailyReport);
}

const printVisitorWeeklyReportButton = document.querySelector("#printVisitorWeeklyReportButton");
if (printVisitorWeeklyReportButton) {
  printVisitorWeeklyReportButton.addEventListener("click", printVisitorWeeklyReport);
}

const refreshSystemStatusButton = document.querySelector("#refreshSystemStatusButton");
if (refreshSystemStatusButton) {
  refreshSystemStatusButton.addEventListener("click", refreshSystemStatus);
}

const repairSystemButton = document.querySelector("#repairSystemButton");
if (repairSystemButton) {
  repairSystemButton.addEventListener("click", handleSystemRepair);
}

const databaseBackupButton = document.querySelector("#databaseBackupButton");
if (databaseBackupButton) {
  databaseBackupButton.addEventListener("click", async () => {
    if (getEffectiveUiRole() !== "superadmin") return;
    const resultNode = document.querySelector("#databaseBackupResult");
    databaseBackupButton.disabled = true;
    try {
      const payload = await apiRequest(`${API_BASE}/api/admin/database/backup`, { method: "POST", body: {} });
      if (resultNode) {
        resultNode.textContent = `${uiT("opsBackupDone")} ${payload?.backupPath || payload?.path || ""}`;
      }
      showToast(uiT("opsBackupDone"), "success");
    } catch (error) {
      const msg = uiT("opsBackupFailed").replace("{error}", error.message || String(error));
      if (resultNode) resultNode.textContent = msg;
      showToast(msg, "error", 5000);
    } finally {
      databaseBackupButton.disabled = false;
    }
  });
}

const operationsSnapshotRefreshBtn = document.querySelector("#operationsSnapshotRefreshBtn");
if (operationsSnapshotRefreshBtn) {
  operationsSnapshotRefreshBtn.addEventListener("click", async () => {
    operationsSnapshotRefreshBtn.disabled = true;
    await loadOperationsSnapshot();
    operationsSnapshotRefreshBtn.disabled = false;
  });
}

const platformHealthRefreshBtn = document.querySelector("#platformHealthRefreshBtn");
if (platformHealthRefreshBtn) {
  platformHealthRefreshBtn.addEventListener("click", async () => {
    platformHealthRefreshBtn.disabled = true;
    await refreshPlatformHealth();
    platformHealthRefreshBtn.disabled = false;
  });
}

const dashExpiringDocsBtn = document.querySelector("#dashExpiringDocsBtn");
if (dashExpiringDocsBtn) {
  dashExpiringDocsBtn.addEventListener("click", () => setView("documents"));
}

if (elements.dayCloseAcknowledgeForm) {
  elements.dayCloseAcknowledgeForm.addEventListener("submit", handleDayCloseAcknowledge);
}

const settingsForm = document.querySelector("#settingsForm");
if (settingsForm) {
  settingsForm.addEventListener("submit", handleSettingsSubmit);

  const fillDatenschutzBtn = document.getElementById("fillDatenschutzTemplateBtn");
  if (fillDatenschutzBtn) {
    fillDatenschutzBtn.addEventListener("click", () => {
      const ta = document.getElementById("datenschutzText");
      if (!ta) return;
      const name = String(document.querySelector("#operatorName")?.value || document.querySelector("#platformName")?.value || "").trim();
      const email = String(document.querySelector("#invoiceOperatorEmail")?.value || "").trim();
      const phone = String(document.querySelector("#invoiceOperatorPhone")?.value || "").trim();
      const street = String(document.querySelector("#invoiceOperatorStreet")?.value || "").trim();
      const zipCity = String(document.querySelector("#invoiceOperatorZipCity")?.value || "").trim();
      const website = String(document.querySelector("#invoiceOperatorWebsite")?.value || "").trim();
      ta.value = buildGdprPrivacyTemplate({ name, email, phone, street, zipCity, website });
      showToast(uiT("toastSaved") || "Vorlage eingefügt", "success");
    });
  }

  wireWorkpassLohnLinkForm();
  loadWorkpassLohnLinkForm().catch(() => {});

  // Live rot/grün Feedback für wichtige Felder
  const SETTINGS_REQUIRED_FIELDS = [
    "#invoiceOperatorStreet",
    "#invoiceOperatorZipCity",
    "#invoiceOperatorEmail",
    "#invoiceOperatorPhone",
    "#invoiceIban",
    "#invoiceBic",
    "#invoiceBankName",
    "#invoiceTaxId",
    "#smtpHost",
    "#smtpSenderEmail",
    "#smtpSenderName",
    "#operatorName",
    "#platformName",
  ];

  function applySettingsFieldColors() {
    for (const sel of SETTINGS_REQUIRED_FIELDS) {
      const el = settingsForm.querySelector(sel);
      if (!el) continue;
      const filled = String(el.value || "").trim().length > 0;
      el.classList.toggle("invoice-field-valid", filled);
      el.classList.toggle("invoice-field-invalid", !filled);
    }
  }

  settingsForm.addEventListener("input", applySettingsFieldColors);
  settingsForm.addEventListener("change", applySettingsFieldColors);
  settingsForm.addEventListener("input", (event) => {
    const target = event.target;
    if (target instanceof Element && target.id === "imapUsername") {
      renderImapPlusAliasWarning();
    }
  });
  // Sofort beim Laden anwenden (nach kurzem Timeout damit renderAdminSettingsForm die Werte gesetzt hat)
  setTimeout(applySettingsFieldColors, 200);
}

const useCurrentAdminIpBtn = document.querySelector("#useCurrentAdminIpBtn");
if (useCurrentAdminIpBtn) {
  useCurrentAdminIpBtn.addEventListener("click", async () => {
    const hint = document.querySelector("#currentAdminIpHint");
    try {
      const res = await apiRequest(API_BASE + "/api/settings/admin-ip-status");
      const ip = String(res?.clientIp || "").trim();
      if (!ip || ip === "local") {
        if (hint) hint.textContent = "Aktuelle IP konnte nicht ermittelt werden.";
        return;
      }
      const input = document.querySelector("#adminIpWhitelist");
      if (input) {
        const existing = String(input.value || "")
          .split(/[,;]/)
          .map((part) => part.trim())
          .filter(Boolean);
        if (!existing.includes(ip)) existing.push(ip);
        input.value = existing.join(", ");
      }
      if (hint) hint.textContent = `Übernommen: ${ip}`;
    } catch (error) {
      if (hint) hint.textContent = `IP-Status nicht verfügbar: ${error?.message || error}`;
    }
  });
}

const companyForm = document.querySelector("#companyForm");
if (companyForm) {
  companyForm.addEventListener("submit", handleCompanySubmit);

  const SECTOR_TERM_PREVIEW = {
    construction: { de: ["Mitarbeiter", "Baustelle", "Drehkreuz / Tor"], en: ["Workers", "Site", "Turnstile / gate"], ar: ["عمال", "موقع بناء", "بوابة"] },
    manufacturing: { de: ["Mitarbeiter", "Werk", "Werktor"], en: ["Employees", "Plant", "Plant gate"], ar: ["موظفون", "منشأة", "بوابة المصنع"] },
    logistics: { de: ["Personal", "Hub / Depot", "Tor / Rampe"], en: ["Staff", "Hub / depot", "Gate / dock"], ar: ["طاقم", "مركز / مستودع", "بوابة / رصيف"] },
    aviation: { de: ["Berechtigte", "Terminal", "Kontrollpunkt"], en: ["Authorized staff", "Terminal", "Checkpoint"], ar: ["مصرّح لهم", "مبنى المطار", "نقطة تفتيش"] },
    security: { de: ["Einsatzkräfte", "Objekt", "Kontrollpunkt"], en: ["Officers", "Site", "Checkpoint"], ar: ["عناصر", "منشأة محروسة", "نقطة تفتيش"] },
    public_sector: { de: ["Mitarbeitende", "Standort", "Eingang"], en: ["Staff", "Facility", "Entrance"], ar: ["موظفون", "منشأة", "مدخل"] },
    government: { de: ["Berechtigte", "Dienststelle", "Zugangskontrolle"], en: ["Authorizees", "Office", "Access point"], ar: ["مصرّح لهم", "دائرة", "نقطة دخول"] },
  };
  function renderCompanySectorPreview() {
    const sel = document.querySelector("#companyOperatingSector");
    const host = document.querySelector("#companySectorPreview");
    if (!sel || !host) return;
    const sector = String(sel.value || "construction");
    const lang = (typeof getUiLang === "function" ? getUiLang() : (localStorage.getItem("baupass-ui-lang") || "de")).slice(0, 2);
    const pack = SECTOR_TERM_PREVIEW[sector] || SECTOR_TERM_PREVIEW.construction;
    const terms = pack[lang] || pack.de || [];
    const title = (typeof uiT === "function" ? uiT("sectorPreviewTitle") : null) || "Vorschau der Fachbegriffe";
    host.innerHTML = `<strong>${title}</strong><div class="sector-preview-chips">${terms
      .map((term) => `<span class="sector-preview-chip">${String(term)}</span>`)
      .join("")}</div>`;
  }
  document.querySelector("#companyOperatingSector")?.addEventListener("change", renderCompanySectorPreview);
  renderCompanySectorPreview();

  const companyStatusSelect = document.querySelector("#companyStatus");
  if (companyStatusSelect) {
    companyStatusSelect.addEventListener("change", updateCompanyTrialEndsAtVisibility);
    updateCompanyTrialEndsAtVisibility();
  }

  const companyNameInput = document.querySelector("#companyName");
  const companyDocumentEmailInput = document.querySelector("#companyDocumentEmail");
  if (companyNameInput && companyDocumentEmailInput) {
    let lastSuggestedValue = "";
    companyNameInput.addEventListener("input", () => {
      const nextSuggestion = suggestCompanyDocumentEmail(companyNameInput.value);
      const currentValue = companyDocumentEmailInput.value.trim();
      if (!currentValue || currentValue === lastSuggestedValue) {
        companyDocumentEmailInput.value = nextSuggestion;
        lastSuggestedValue = nextSuggestion;
      }
      updateCompanyAdminPasswordHint();
    });
  }
  updateCompanyAdminPasswordHint();
}

if (elements.desktopInstallButton) {
  elements.desktopInstallButton.addEventListener("click", () => {
    triggerDesktopInstall().catch(() => {
      showToast(uiT("alertDesktopInstallFailed"));
    });
  });
}

document.addEventListener("click", (event) => {
  const resolveBtn = event.target.closest?.("[data-gdpr-resolve]");
  if (resolveBtn) {
    const id = resolveBtn.getAttribute("data-gdpr-resolve");
    const status = resolveBtn.getAttribute("data-gdpr-status");
    if (id && status) {
      resolveGdprRequest(id, status);
    }
    return;
  }
  if (event.target.closest?.("#gdprRequestsRefreshBtn") || event.target.closest?.("#dashGdprRefreshBtn")) {
    apiRequest(`${API_BASE}/api/gdpr-requests?status=pending&limit=80`)
      .then((gdpr) => {
        state.gdprRequests = Array.isArray(gdpr?.requests) ? gdpr.requests : [];
        renderGdprRequestsPanel();
      })
      .catch((error) => showToast(error?.message || "Laden fehlgeschlagen", "error"));
  }
});

// ── Legal-Modal (Impressum / Datenschutz) ─────────────────────────────────
(function () {
  const legalModal    = document.getElementById("legalModal");
  const legalTitle    = document.getElementById("legalModalTitle");
  const legalBody     = document.getElementById("legalModalBody");
  const legalClose    = document.getElementById("legalModalClose");
  const impressumBtn  = document.getElementById("showImpressumBtn");
  const datenschutzBtn = document.getElementById("showDatenschutzBtn");

  if (!legalModal) return;

  function openLegalModal(type) {
    const settings = (typeof state !== "undefined" && state.settings) ? state.settings : {};
    if (type === "impressum") {
      legalTitle.textContent = uiT("legalImpressum") || "Impressum";
      legalBody.textContent  = settings.impressumText || window._publicImpressumText || "";
    } else {
      legalTitle.textContent = uiT("legalPrivacy") || "Datenschutz";
      legalBody.textContent  = settings.datenschutzText || window._publicDatenschutzText || "";
    }
    legalModal.classList.remove("hidden");
    legalModal.setAttribute("aria-hidden", "false");
    if (legalClose) legalClose.focus();
  }

  function closeLegalModal() {
    legalModal.classList.add("hidden");
    legalModal.setAttribute("aria-hidden", "true");
  }

  if (impressumBtn)   impressumBtn.addEventListener("click",  () => openLegalModal("impressum"));
  if (datenschutzBtn) datenschutzBtn.addEventListener("click", () => openLegalModal("datenschutz"));
  if (legalClose)     legalClose.addEventListener("click", closeLegalModal);
  legalModal.addEventListener("click", (e) => { if (e.target === legalModal) closeLegalModal(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !legalModal.classList.contains("hidden")) closeLegalModal();
  });
})();

// Bulk-Aktionen für Worker
if (elements.bulkSelectAll) {
  elements.bulkSelectAll.addEventListener("change", () => {
    const checkboxes = elements.workerList.querySelectorAll(".bulk-checkbox");
    checkboxes.forEach((cb) => { cb.checked = elements.bulkSelectAll.checked; });
    updateBulkActionBar();
  });
}

if (elements.bulkCancelButton) {
  elements.bulkCancelButton.addEventListener("click", () => {
    elements.workerList.querySelectorAll(".bulk-checkbox").forEach((cb) => { cb.checked = false; });
    if (elements.bulkSelectAll) { elements.bulkSelectAll.checked = false; elements.bulkSelectAll.indeterminate = false; }
    updateBulkActionBar();
  });
}

async function executeBulkStatus(status) {
  const ids = getCheckedWorkerIds();
  if (!ids.length) return;
  try {
    await apiRequest(`${API_BASE}/api/workers/bulk-status`, { method: "PATCH", body: { ids, status } });
    elements.workerList.querySelectorAll(".bulk-checkbox").forEach((cb) => { cb.checked = false; });
    if (elements.bulkSelectAll) { elements.bulkSelectAll.checked = false; elements.bulkSelectAll.indeterminate = false; }
    updateBulkActionBar();
    await loadAllData();
    refreshAll();
  } catch (err) {
    showToast(uiT("alertGenericError").replace("{error}", err.message || String(err)));
  }
}

if (elements.bulkSetActiveButton) {
  elements.bulkSetActiveButton.addEventListener("click", () => executeBulkStatus("aktiv"));
}
if (elements.bulkSetInactiveButton) {
  elements.bulkSetInactiveButton.addEventListener("click", () => executeBulkStatus("inaktiv"));
}

if (elements.bulkDeleteButton) {
  elements.bulkDeleteButton.addEventListener("click", async () => {
    const ids = getCheckedWorkerIds();
    if (!ids.length) return;
    const msg = runtimeText("confirmDeleteWorkerBulk").replace("{count}", ids.length);
    if (!(await showConfirmDialog(msg))) return;
    try {
      await apiRequest(`${API_BASE}/api/workers/bulk-delete`, { method: "POST", body: { ids } });
      elements.workerList.querySelectorAll(".bulk-checkbox").forEach((cb) => { cb.checked = false; });
      if (elements.bulkSelectAll) { elements.bulkSelectAll.checked = false; elements.bulkSelectAll.indeterminate = false; }
      updateBulkActionBar();
      await loadAllData();
      refreshAll();
    } catch (err) {
      showToast(uiT("alertDeleteWorkerFailed").replace("{error}", err.message || String(err)));
    }
  });
}

initAccountSettingsUi();

const imapTestBtn = document.querySelector("#imapTestBtn");
if (imapTestBtn) {
  imapTestBtn.addEventListener("click", sendImapTest);
}

const invoiceForm = document.querySelector("#invoiceForm");
if (invoiceForm) {
  invoiceForm.addEventListener("submit", handleInvoicePrint);
}

const invoiceSendButton = document.querySelector("#invoiceSendButton");
if (invoiceSendButton) {
  invoiceSendButton.addEventListener("click", handleInvoiceSend);
}

const invoicePreviewButton = document.querySelector("#invoicePreviewButton");
if (invoicePreviewButton) {
  invoicePreviewButton.addEventListener("click", () => refreshInvoicePreview({ silent: false }));
}

const invoiceCompanySelect = document.querySelector("#invoiceCompanySelect");
if (invoiceCompanySelect) {
  invoiceCompanySelect.addEventListener("change", () => {
    syncInvoiceRecipientFromCompany();
    refreshInvoicePreview({ silent: true });
  });
}

// ── Auto-fill invoice number ──────────────────────────────────────────────
const invoiceNumberAutoBtn = document.querySelector("#invoiceNumberAutoBtn");
if (invoiceNumberAutoBtn) {
  invoiceNumberAutoBtn.addEventListener("click", async () => {
    try {
      const companyId = document.querySelector("#invoiceCompanySelect")?.value || "";
      const query = companyId ? `?companyId=${encodeURIComponent(companyId)}` : "";
      const data = await apiRequest(API_BASE + "/api/invoices/next-number" + query);
      const field = document.querySelector("#invoiceNumber");
      if (field) field.value = data.nextNumber || "";
    } catch (e) {
      showToast(runtimeTextTemplate("invoiceNumberAutoFailed", { error: e.message }));
    }
  });
}

// ── Dynamic invoice positions ─────────────────────────────────────────────
function createPositionRow(pos = {}) {
  const row = document.createElement("div");
  row.className = "invoice-position-row";
  row.style.cssText = "display:grid;grid-template-columns:1fr 70px 90px 90px 34px;gap:4px;margin-bottom:4px;align-items:center;";
  const desc = pos.description || "";
  const qty = pos.qty != null ? pos.qty : 1;
  const unit = pos.unit || runtimeText("invoicePositionUnitFlat");
  const unitPrice = pos.unitPrice != null ? pos.unitPrice : 0;
  row.innerHTML = `
    <input type="text" class="pos-desc" placeholder="${escapeAttr(runtimeText("invoicePositionDescriptionPlaceholder"))}" value="${escapeAttr(desc)}" style="padding:5px 7px;border:1px solid #cbd5e0;border-radius:4px;font-size:13px;" required />
    <input type="number" class="pos-qty" placeholder="${escapeAttr(runtimeText("invoicePositionQtyPlaceholder"))}" value="${qty}" min="0" step="any" style="padding:5px 7px;border:1px solid #cbd5e0;border-radius:4px;font-size:13px;text-align:right;" />
    <select class="pos-unit" style="padding:5px 4px;border:1px solid #cbd5e0;border-radius:4px;font-size:13px;">
      <option${unit===runtimeText("invoicePositionUnitFlat")?" selected":""}>${escapeHtml(runtimeText("invoicePositionUnitFlat"))}</option>
      <option${unit===runtimeText("invoicePositionUnitHours")?" selected":""}>${escapeHtml(runtimeText("invoicePositionUnitHours"))}</option>
      <option${unit===runtimeText("invoicePositionUnitPiece")?" selected":""}>${escapeHtml(runtimeText("invoicePositionUnitPiece"))}</option>
      <option${unit===runtimeText("invoicePositionUnitMonth")?" selected":""}>${escapeHtml(runtimeText("invoicePositionUnitMonth"))}</option>
      <option${unit===runtimeText("invoicePositionUnitDay")?" selected":""}>${escapeHtml(runtimeText("invoicePositionUnitDay"))}</option>
    </select>
    <input type="number" class="pos-unit-price" placeholder="${escapeAttr(runtimeText("invoicePositionUnitPricePlaceholder"))}" value="${unitPrice}" min="0" step="0.01" style="padding:5px 7px;border:1px solid #cbd5e0;border-radius:4px;font-size:13px;text-align:right;" />
    <button type="button" class="remove-pos-btn" style="background:none;border:none;cursor:pointer;color:#e53e3e;font-size:18px;line-height:1;padding:2px;">×</button>
  `;
  row.querySelector(".remove-pos-btn").addEventListener("click", () => {
    row.remove();
    updatePositionNetTotal();
  });
  ["pos-qty", "pos-unit-price"].forEach((cls) => {
    row.querySelector("." + cls).addEventListener("input", updatePositionNetTotal);
  });
  return row;
}

function escapeAttr(str) {
  return String(str || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function updatePositionNetTotal() {
  const rows = document.querySelectorAll("#invoicePositionRows .invoice-position-row");
  let total = 0;
  rows.forEach((r) => {
    const qty = parseFloat(r.querySelector(".pos-qty")?.value || "1") || 0;
    const price = parseFloat(r.querySelector(".pos-unit-price")?.value || "0") || 0;
    total += qty * price;
  });
  total = Math.round(total * 100) / 100;
  const el = document.querySelector("#invoicePositionNetTotal");
  if (el) el.textContent = formatCurrency(total);
  refreshInvoicePreview({ silent: true });
}

function getInvoicePositions() {
  const rows = document.querySelectorAll("#invoicePositionRows .invoice-position-row");
  if (!rows.length) return [];
  return Array.from(rows).map((r) => {
    const qty = parseFloat(r.querySelector(".pos-qty")?.value || "1") || 1;
    const unitPrice = parseFloat(r.querySelector(".pos-unit-price")?.value || "0") || 0;
    return {
      description: (r.querySelector(".pos-desc")?.value || "").trim(),
      qty,
      unit: r.querySelector(".pos-unit")?.value || runtimeText("invoicePositionUnitFlat"),
      unitPrice,
      total: Math.round(qty * unitPrice * 100) / 100,
    };
  }).filter((item) => {
    const hasDescription = item.description.length > 0;
    const hasValue = Number(item.total || 0) > 0;
    return hasDescription || hasValue;
  });
}

function initInvoicePositions() {
  const container = document.querySelector("#invoicePositionRows");
  const addBtn = document.querySelector("#addInvoicePositionBtn");
  if (!container || !addBtn) return;
  if (!container.children.length) {
    container.appendChild(createPositionRow({ description: "", qty: 1, unit: runtimeText("invoicePositionUnitFlat"), unitPrice: 0 }));
  }
  addBtn.addEventListener("click", () => {
    container.appendChild(createPositionRow());
    updatePositionNetTotal();
  });
  const discountToggle = document.querySelector("#invoiceDiscountToggle");
  const discountRow = document.querySelector("#invoiceDiscountRow");
  if (discountToggle && discountRow) {
    discountToggle.addEventListener("change", () => {
      discountRow.style.display = discountToggle.checked ? "block" : "none";
    });
    const discountInput = document.querySelector("#invoiceDiscountAmount");
    if (discountInput) discountInput.addEventListener("input", updatePositionNetTotal);
  }
}
initInvoicePositions();

// ── CSV Worker Import ─────────────────────────────────────────────────────
const workerCsvImportButton = document.querySelector("#workerCsvImportButton");
const workerCsvImportInput = document.querySelector("#workerCsvImportInput");
if (workerCsvImportButton && workerCsvImportInput) {
  workerCsvImportButton.addEventListener("click", () => workerCsvImportInput.click());
  workerCsvImportInput.addEventListener("change", async () => {
    const file = workerCsvImportInput.files?.[0];
    if (!file) return;
    const resultEl = document.querySelector("#workerCsvImportResult");
    if (resultEl) { resultEl.style.display = "block"; resultEl.textContent = runtimeText("workerCsvImportLoading"); resultEl.style.background = "#ebf4ff"; }
    try {
      const formData = new FormData();
      formData.append("file", file);
      const resp = await fetch(API_BASE + "/api/workers/import-csv", {
        method: "POST",
        credentials: "include",
        body: formData,
      });
      if (!resp.ok) { const e = await resp.json().catch(() => ({})); throw new Error(e.message || resp.statusText); }
      const data = await resp.json();
      if (resultEl) {
        resultEl.style.background = data.errors === 0 ? "#f0fff4" : "#fffbeb";
        resultEl.innerHTML = `<strong>${escapeHtml(runtimeTextTemplate("workerCsvImportSummary", { created: data.created, skipped: data.skipped, errors: data.errors }))}</strong>` +
          (data.details?.errors?.length ? `<br><small style="color:#c05621">${data.details.errors.map(e => escapeHtml(runtimeTextTemplate("workerCsvImportRowError", { row: e.row, reason: e.reason }))).join("; ")}</small>` : "");
      }
      workerCsvImportInput.value = "";
      refreshAll();
    } catch (err) {
      if (resultEl) { resultEl.style.background = "#fff5f5"; resultEl.textContent = runtimeTextTemplate("workerCsvImportErrorPrefix", { error: err.message }); }
    }
  });
}

let _invoicePreviewDebounceTimer = null;
function debouncedRefreshInvoicePreview() {
  clearTimeout(_invoicePreviewDebounceTimer);
  _invoicePreviewDebounceTimer = setTimeout(() => refreshInvoicePreview({ silent: true }), 400);
}

["#invoiceNumber", "#invoiceRecipientEmail", "#invoiceDate", "#invoiceDueDate", "#invoicePeriod", "#invoiceDescription", "#invoiceNetAmount", "#invoiceVatRate"].forEach((selector) => {
  const field = document.querySelector(selector);
  if (field) {
    field.addEventListener("input", debouncedRefreshInvoicePreview);
  }
});

const invoiceLogoFile = document.querySelector("#invoiceLogoFile");
if (invoiceLogoFile) {
  invoiceLogoFile.addEventListener("change", handleInvoiceLogoUpload);
}

const loadCustomBrandButton = document.querySelector("#loadCustomBrandButton");
if (loadCustomBrandButton) {
  loadCustomBrandButton.addEventListener("click", loadCustomBrandingPreset);
}
const loadCustomBrandAltButton = document.querySelector("#loadCustomBrandAltButton");
if (loadCustomBrandAltButton) {
  loadCustomBrandAltButton.addEventListener("click", loadCustomBrandingPresetAlt);
}

