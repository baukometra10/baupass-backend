/**
 * Einsatzplan direkt in WorkPass (ohne iframe).
 */
(function initBaupassDeploymentPlan(global) {
  let modalWorkerId = null;
  let modalDays = [];
  let monthState = null;
  let bound = false;
  let autoRefreshTimer = null;

  function stopAutoRefresh() {
    if (autoRefreshTimer) {
      window.clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }
  }

  function startAutoRefresh() {
    stopAutoRefresh();
    autoRefreshTimer = window.setInterval(() => {
      const view = document.querySelector('.view[data-view="deployment-plan"].active');
      if (!view || !global.token) {
        stopAutoRefresh();
        return;
      }
      refreshView().catch(() => {});
    }, 20000);
  }

  function $(id) {
    return document.getElementById(id);
  }

  function ui(key) {
    return typeof global.uiT === "function" ? global.uiT(key) : key;
  }

  function lang() {
    return typeof global.getCurrentLang === "function" ? global.getCurrentLang().slice(0, 2) : "de";
  }

  function companyQuery() {
    const role = String(global.getEffectiveUiRole?.() || "").toLowerCase();
    const cid = String(global.getEffectiveUiCompanyId?.() || "").trim();
    if (role === "superadmin" && cid) {
      return `?company_id=${encodeURIComponent(cid)}`;
    }
    return "";
  }

  function needsCompany() {
    return String(global.getEffectiveUiRole?.() || "").toLowerCase() === "superadmin"
      && !String(global.getEffectiveUiCompanyId?.() || "").trim();
  }

  async function api(path, options = {}) {
    return global.apiRequest(`${global.API_BASE}${path}`, options);
  }

  function isoToTimeInput(iso) {
    const s = String(iso || "").trim();
    if (!s) return "";
    if (s.length >= 16 && s.includes("T")) return s.slice(11, 16);
    if (/^\d{1,2}:\d{2}/.test(s)) return s.slice(0, 5);
    return "";
  }

  function timeInputToIso(dateStr, hhmm) {
    const date = String(dateStr || "").trim().slice(0, 10);
    const t = String(hhmm || "").trim();
    if (!date || !t) return "";
    const parts = t.split(":");
    const h = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10);
    if (Number.isNaN(h) || Number.isNaN(m)) return "";
    return `${date}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00`;
  }

  function escapeAttr(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function companyMonthParts() {
    const raw = $("cpDeploymentCompanyMonth")?.value || "";
    const [y, m] = raw.split("-").map((x) => parseInt(x, 10));
    if (!y || !m) {
      const now = new Date();
      return { year: now.getFullYear(), month: now.getMonth() + 1 };
    }
    return { year: y, month: m };
  }

  function modalMonthParts() {
    const raw = $("cpDeploymentMonth")?.value || "";
    const [y, m] = raw.split("-").map((x) => parseInt(x, 10));
    if (!y || !m) {
      const now = new Date();
      return { year: now.getFullYear(), month: now.getMonth() + 1 };
    }
    return { year: y, month: m };
  }

  function readModalDaysFromForm() {
    const host = $("cpDeploymentDaysList");
    if (!host) return;
    host.querySelectorAll(".deployment-day-row[data-dep-idx]").forEach((row) => {
      const i = parseInt(row.getAttribute("data-dep-idx"), 10);
      const d = modalDays[i];
      if (!d) return;
      d.location = row.querySelector('[data-dep-field="location"]')?.value.trim() || "";
      d.shiftStart = timeInputToIso(d.date, row.querySelector('[data-dep-field="start"]')?.value);
      d.shiftEnd = timeInputToIso(d.date, row.querySelector('[data-dep-field="end"]')?.value);
      d.notes = row.querySelector('[data-dep-field="notes"]')?.value.trim() || "";
      d.dayColor = row.querySelector('[data-dep-field="color"]')?.value || "";
    });
  }

  function renderDeclinesBanner(state) {
    const banner = $("cpDeploymentDeclinesBanner");
    if (!banner) return;
    const count = Number(state?.declinedDayCount || 0);
    if (!count) {
      banner.classList.add("hidden");
      banner.innerHTML = "";
      return;
    }
    const items = (state.recentDeclines || [])
      .slice(0, 8)
      .map((item) => {
        const name = escapeAttr(item.workerName || item.workerId || "—");
        const date = escapeAttr(String(item.workDate || "").slice(0, 10));
        const loc = escapeAttr(item.location || "—");
        const reason = escapeAttr(item.reason || "");
        const reasonPart = reason ? ` — ${reason}` : "";
        return `<li><strong>${name}</strong> · ${date} · ${loc}${reasonPart}</li>`;
      })
      .join("");
    banner.innerHTML = `
      <div class="deployment-declines-banner-inner">
        <p class="deployment-declines-banner-title">${escapeAttr(ui("deploymentDeclinesBannerTitle"))}</p>
        <p class="muted small">${escapeAttr(ui("deploymentDeclinesBannerHint"))}</p>
        <ul class="deployment-declines-list">${items}</ul>
      </div>`;
    banner.classList.remove("hidden");
    const declines = (state.recentDeclines || []).slice(0, 8);
    banner.querySelectorAll(".deployment-declines-list li").forEach((li, idx) => {
      const item = declines[idx];
      if (!item?.workerId) return;
      li.classList.add("deployment-decline-clickable");
      li.addEventListener("click", () => {
        const wname = String(item.workerName || item.workerId || "").trim();
        openWorkerModal(item.workerId, wname).catch((e) =>
          global.showToast?.(e.message, "error", 6000),
        );
      });
    });
  }

  function renderModalDaysList() {
    const host = $("cpDeploymentDaysList");
    if (!host) return;
    const header = `
      <div class="deployment-days-header" role="row">
        <span>${ui("deploymentColDay")}</span>
        <span>${ui("deploymentColLocation")}</span>
        <span>${ui("deploymentColStart")}</span>
        <span>${ui("deploymentColEnd")}</span>
        <span>${ui("deploymentColNotes")}</span>
        <span>${ui("deploymentColColor") || "Farbe"}</span>
        <span></span>
      </div>`;
    const rows = modalDays
      .map((d, i) => {
        const loc = escapeAttr(d.location || "");
        const notes = escapeAttr(d.notes || "");
        const start = escapeAttr(isoToTimeInput(d.shiftStart));
        const end = escapeAttr(isoToTimeInput(d.shiftEnd));
        const color = escapeAttr(d.dayColor || "#1f6feb");
        const isFree = !loc || /^(frei|free|off|aus|urlaub)$/i.test(loc.trim());
        const declined =
          String(d.workerResponse || "") === "declined" || Boolean(d.isDeclined);
        const reasonText = String(d.declineReason || "").trim();
        const declineHint = declined
          ? `<span class="deployment-day-declined">${escapeAttr(ui("deploymentWorkerDeclined"))}</span>`
          : "";
        const declineReasonBlock =
          declined && reasonText
            ? `<p class="deployment-decline-reason"><strong>${escapeAttr(ui("deploymentDeclineReasonLabel"))}:</strong> ${escapeAttr(reasonText)}</p>`
            : "";
        return `
      <div class="deployment-day-row${d.isWeekend ? " weekend" : ""}${declined ? " worker-declined" : ""}${isFree ? " is-free-day" : ""}" data-dep-idx="${i}" role="row" style="${d.dayColor ? `--dep-row-color:${escapeAttr(d.dayColor)}` : ""}">
        <span class="deployment-day-meta">${d.date.slice(8, 10)}.${d.date.slice(5, 7)}.<br /><span class="deployment-weekday">${d.weekday}</span>${declineHint}${declineReasonBlock}</span>
        <input type="text" data-dep-field="location" value="${loc}" placeholder="${escapeAttr(ui("deploymentLocationPh"))}" />
        <input type="time" data-dep-field="start" value="${start}" />
        <input type="time" data-dep-field="end" value="${end}" />
        <input type="text" data-dep-field="notes" value="${notes}" placeholder="${escapeAttr(ui("deploymentNotesPh"))}" />
        <input type="color" class="deployment-day-color" data-dep-field="color" value="${color}" title="${escapeAttr(ui("deploymentColColor") || "Farbe")}" />
        <div class="deployment-day-actions-inline">
          <button type="button" class="ghost-button deployment-day-free" data-dep-free="${i}">${ui("deploymentMarkFree") || "Frei"}</button>
          <button type="button" class="ghost-button deployment-day-clear" data-dep-clear="${i}">${ui("deploymentClearDay")}</button>
        </div>
      </div>`;
      })
      .join("");
    host.innerHTML = header + rows;
    host.querySelectorAll("[data-dep-clear]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const i = parseInt(btn.getAttribute("data-dep-clear"), 10);
        const d = modalDays[i];
        if (!d) return;
        d.location = "Frei";
        d.shiftStart = "";
        d.shiftEnd = "";
        d.notes = "";
        d.dayType = "free";
        renderModalDaysList();
      });
    });
    host.querySelectorAll("[data-dep-free]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const i = parseInt(btn.getAttribute("data-dep-free"), 10);
        const d = modalDays[i];
        if (!d) return;
        d.location = "Frei";
        d.shiftStart = "";
        d.shiftEnd = "";
        d.dayType = "free";
        if (!d.dayColor) d.dayColor = "#10b981";
        renderModalDaysList();
      });
    });
  }

  function applyBulkWeekdays() {
    readModalDaysFromForm();
    const loc = $("cpDeploymentBulkLocation")?.value.trim() || "";
    const start = $("cpDeploymentBulkStart")?.value || "";
    const end = $("cpDeploymentBulkEnd")?.value || "";
    modalDays.forEach((d) => {
      if (d.isWeekend) return;
      if (loc) d.location = loc;
      if (start) d.shiftStart = timeInputToIso(d.date, start);
      if (end) d.shiftEnd = timeInputToIso(d.date, end);
    });
    renderModalDaysList();
    global.showToast?.(ui("deploymentBulkApplied"), "success", 3500);
  }

  function clearWeekends() {
    readModalDaysFromForm();
    modalDays.forEach((d) => {
      if (!d.isWeekend) return;
      d.location = "";
      d.shiftStart = "";
      d.shiftEnd = "";
      d.notes = "";
    });
    renderModalDaysList();
  }

  async function reloadModalPlan() {
    const q = companyQuery();
    const { year, month } = modalMonthParts();
    if (!modalWorkerId) return;
    const data = await api(
      `/api/workforce/deployment-plan${q}${q ? "&" : "?"}worker_id=${encodeURIComponent(modalWorkerId)}&year=${year}&month=${month}&lang=${lang()}`,
    );
    modalDays = data.days || [];
    const declined = Number(data.declinedDayCount || 0);
    const metaEl = $("cpDeploymentModalDeclinedMeta");
    if (metaEl) {
      if (declined > 0) {
        metaEl.textContent = ui("deploymentModalDeclinedDays").replace("{count}", String(declined));
        metaEl.classList.remove("hidden");
      } else {
        metaEl.textContent = "";
        metaEl.classList.add("hidden");
      }
    }
    renderModalDaysList();
  }

  async function openWorkerModal(workerId, workerName) {
    modalWorkerId = workerId;
    const nameEl = $("cpDeploymentModalWorker");
    if (nameEl) nameEl.textContent = workerName;
    const companyMonth = $("cpDeploymentCompanyMonth")?.value;
    if (companyMonth) $("cpDeploymentMonth").value = companyMonth;
    $("cpDeploymentModal")?.classList.remove("hidden");
    const scrollHost = $("cpDeploymentModalScroll");
    if (scrollHost) {
      scrollHost.scrollTop = 0;
      window.setTimeout(() => scrollHost.focus({ preventScroll: true }), 50);
    }
    await reloadModalPlan();
  }

  async function saveModalPlan() {
    const q = companyQuery();
    const { year, month } = modalMonthParts();
    readModalDaysFromForm();
    const days = modalDays.map((d) => ({
      date: d.date,
      location: d.location,
      notes: d.notes || "",
      shiftStart: d.shiftStart,
      shiftEnd: d.shiftEnd,
      dayColor: d.dayColor || "",
      dayType: d.dayType || (/^(frei|free)$/i.test(String(d.location || "").trim()) ? "free" : ""),
    }));
    await api(`/api/workforce/deployment-plan${q}`, {
      method: "PUT",
      body: { workerId: modalWorkerId, year, month, days },
    });
    global.showToast?.(ui("deploymentSaved"), "success", 4000);
    await loadMonthBar();
    await loadWorkerList();
  }

  async function downloadModalPdf() {
    await saveModalPlan();
    const q = companyQuery();
    const { year, month } = modalMonthParts();
    const res = await fetch(`${global.API_BASE}/api/workforce/deployment-plan/pdf${q}`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${global.token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ workerId: modalWorkerId, year, month, lang: lang() }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.message || err.error || res.statusText);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `einsatzplan-${modalWorkerId}-${year}-${month}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function renderMonthStatus(batch) {
    const el = $("cpDeploymentMonthStatus");
    if (!el) return;
    const st = batch?.status || "draft";
    const awaiting = batch?.awaitingConfirm;
    let label = ui("deploymentStatusDraft");
    let cls = "deployment-status-badge draft";
    if (st === "sent" && !awaiting) {
      label = ui("deploymentStatusSent");
      cls = "deployment-status-badge sent";
    } else if (awaiting || st === "draft") {
      label = ui("deploymentStatusAwaiting");
      cls = "deployment-status-badge awaiting";
    }
    el.textContent = label;
    el.className = cls;
    $("cpDeploymentReopenMonthBtn")?.classList.toggle("hidden", st !== "sent" || awaiting);
  }

  async function loadMonthBar() {
    const bar = $("cpDeploymentMonthBar");
    if (!bar) return;
    if (needsCompany()) {
      bar.classList.add("hidden");
      return;
    }
    bar.classList.remove("hidden");
    const now = new Date();
    const monthInput = $("cpDeploymentCompanyMonth");
    if (monthInput && !monthInput.value) {
      monthInput.value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    }
    const { year, month } = companyMonthParts();
    const q = companyQuery();
    try {
      monthState = await api(`/api/workforce/deployment-month${q}${q ? "&" : "?"}year=${year}&month=${month}`);
      renderMonthStatus(monthState.batch);
      renderDeclinesBanner(monthState);
      const stats = $("cpDeploymentMonthStats");
      if (stats) {
        let text = ui("deploymentMonthStats")
          .replace("{ready}", String(monthState.readyCount ?? 0))
          .replace("{total}", String(monthState.totalWorkers ?? 0));
        const declined = Number(monthState.declinedDayCount || 0);
        if (declined > 0) {
          text += ui("deploymentMonthStatsDeclines").replace("{count}", String(declined));
        }
        stats.textContent = text;
      }
    } catch (e) {
      $("cpDeploymentMonthStats").textContent = e.message || String(e);
    }
  }

  async function loadWorkerList() {
    const host = $("cpDeploymentWorkerList");
    if (!host) return;
    if (needsCompany()) {
      host.innerHTML = `<p class="muted">${ui("deploymentSelectCompany")}</p>`;
      return;
    }
    const { year, month } = companyMonthParts();
    const q = companyQuery();
    try {
      const data = await api(`/api/workforce/deployment-month${q}${q ? "&" : "?"}year=${year}&month=${month}`);
      const workers = data.workers || [];
      if (!workers.length) {
        host.innerHTML = `<p class="muted">${ui("deploymentNoWorkers")}</p>`;
        return;
      }
      const head = `<tr><th>${ui("deploymentColWorker")}</th><th>Status</th><th>${ui("deploymentColDeclines")}</th><th></th></tr>`;
      const body = workers
        .map((w) => {
          const name = `${w.firstName || w.first_name || ""} ${w.lastName || w.last_name || ""}`.trim() || w.workerId || w.id;
          const ready = w.ready ? ui("deploymentReady") : ui("deploymentNotReady");
          const wid = w.workerId || w.id;
          const declined = Number(w.declinedDayCount || 0);
          const declineCell =
            declined > 0
              ? `<span class="deployment-worker-decline-pill">${escapeAttr(
                  ui("deploymentWorkerHasDeclines").replace("{count}", String(declined)),
                )}</span>`
              : `<span class="muted">—</span>`;
          const statusCell = `<span class="deployment-ready-pill${w.ready ? " ok" : ""}">${ready}</span>`;
          return `<tr${declined > 0 ? ' class="has-worker-declines"' : ""}>
            <td>${escapeAttr(name)}</td>
            <td>${statusCell}</td>
            <td>${declineCell}</td>
            <td><button type="button" class="primary-button small-button" data-cp-dep-edit="${escapeAttr(wid)}" data-cp-dep-name="${escapeAttr(name)}">${ui("deploymentEditBtn")}</button></td>
          </tr>`;
        })
        .join("");
      host.innerHTML = `<table class="data-table deployment-worker-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
      host.querySelectorAll("[data-cp-dep-edit]").forEach((btn) => {
        btn.addEventListener("click", () => {
          openWorkerModal(btn.getAttribute("data-cp-dep-edit"), btn.getAttribute("data-cp-dep-name") || "").catch(
            (e) => global.showToast?.(e.message, "error", 6000),
          );
        });
      });
    } catch (e) {
      host.innerHTML = `<p class="error">${escapeAttr(e.message)}</p>`;
    }
  }

  function scrollToWorkers() {
    $("cpDeploymentWorkersSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function refreshView() {
    if (!global.token) return;
    await loadMonthBar();
    await loadWorkerList();
  }

  function bindOnce() {
    if (bound) return;
    bound = true;

    $("cpDeploymentCompanyMonth")?.addEventListener("change", () => {
      refreshView().catch((e) => global.showToast?.(e.message, "error", 6000));
    });
    $("cpDeploymentPrepareNextBtn")?.addEventListener("click", async () => {
      const q = companyQuery();
      const res = await api(`/api/workforce/deployment-month/prepare-next${q}`, {
        method: "POST",
        body: { useAutopilotLogic: true },
      });
      global.showToast?.(ui("deploymentPreparedOk"), "success", 4000);
      if (res.year && res.month) {
        $("cpDeploymentCompanyMonth").value = `${res.year}-${String(res.month).padStart(2, "0")}`;
      }
      await refreshView();
    });
    $("cpDeploymentReopenMonthBtn")?.addEventListener("click", async () => {
      const q = companyQuery();
      const { year, month } = companyMonthParts();
      await api(`/api/workforce/deployment-month/reopen${q}`, {
        method: "POST",
        body: JSON.stringify({ year, month }),
      });
      global.showToast?.(ui("deploymentReopenOk"), "success", 4000);
      await refreshView();
    });
    $("cpDeploymentConfirmSendBtn")?.addEventListener("click", async () => {
      if (!window.confirm(ui("deploymentConfirmSendPrompt"))) return;
      const q = companyQuery();
      const { year, month } = companyMonthParts();
      await api(`/api/workforce/deployment-month/confirm-send${q}`, {
        method: "POST",
        body: { year, month, confirmSend: true, lang: lang() },
      });
      global.showToast?.(ui("deploymentSentOk"), "success", 5000);
      await refreshView();
    });

    $("cpDeploymentMonth")?.addEventListener("change", () =>
      reloadModalPlan().catch((e) => global.showToast?.(e.message, "error", 6000)),
    );
    $("cpDeploymentModalClose")?.addEventListener("click", () => $("cpDeploymentModal")?.classList.add("hidden"));
    $("cpDeploymentModal")?.addEventListener("click", (e) => {
      if (e.target?.id === "cpDeploymentModal") $("cpDeploymentModal").classList.add("hidden");
    });
    $("cpDeploymentSaveBtn")?.addEventListener("click", () =>
      saveModalPlan().catch((e) => global.showToast?.(e.message, "error", 6000)),
    );
    $("cpDeploymentPdfBtn")?.addEventListener("click", () =>
      downloadModalPdf().catch((e) => global.showToast?.(e.message, "error", 6000)),
    );
    $("cpDeploymentBulkWeekdays")?.addEventListener("click", applyBulkWeekdays);
    $("cpDeploymentBulkClearWeekends")?.addEventListener("click", clearWeekends);
    $("cpDeploymentFromShifts")?.addEventListener("click", async () => {
      const q = companyQuery();
      const { year, month } = modalMonthParts();
      await api(`/api/workforce/deployment-plan/from-shifts${q}`, {
        method: "POST",
        body: { workerId: modalWorkerId, year, month },
      });
      await reloadModalPlan();
      global.showToast?.(ui("deploymentFromShiftsOk"), "success", 3000);
    });
    $("cpDeploymentRotation")?.addEventListener("click", async () => {
      const raw = window.prompt(ui("deploymentRotationPrompt"), "Berlin, Potsdam, Dresden");
      if (!raw) return;
      const locations = raw.split(",").map((s) => s.trim()).filter(Boolean);
      const q = companyQuery();
      const { year, month } = modalMonthParts();
      await api(`/api/workforce/deployment-plan/rotation${q}`, {
        method: "POST",
        body: { workerId: modalWorkerId, year, month, locations, skipWeekends: true },
      });
      await reloadModalPlan();
    });
  }

  global.BaupassDeploymentPlan = {
    refresh: refreshView,
    scrollToWorkers,
    openWorker: (workerId, workerName) =>
      openWorkerModal(workerId, workerName || "").catch((e) =>
        global.showToast?.(e.message, "error", 6000),
      ),
    bindOnce,
    startAutoRefresh,
    stopAutoRefresh,
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindOnce);
  } else {
    bindOnce();
  }
})(window);
