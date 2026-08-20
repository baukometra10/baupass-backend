/**
 * Payslip review studio UX helpers (confirm modal, prefs, pagination, metrics, CSV).
 * Keep side-effect free except DOM APIs passed in / queried by id.
 */
export const PAYSLIP_ASSET_V = "20260820lohnStudio14";

export const PAYSLIP_FILTERS_KEY = "workpass-payslip-filters";
export const PAYSLIP_KEYS_HINT_DISMISS_KEY = "workpass-payslip-keys-hint-dismissed";
export const PAYSLIP_LIST_PAGE_SIZE = 8;

export function trackPayslipMetric(name, detail = {}) {
  const payload = {
    name: String(name || "payslip"),
    at: Date.now(),
    ...detail,
  };
  if (typeof window === "undefined") return;
  try {
    window.dispatchEvent(new CustomEvent("workpass-payslip-metric", { detail: payload }));
  } catch {
    /* ignore */
  }
  try {
    if (!Array.isArray(window.__workpassPayslipMetrics)) window.__workpassPayslipMetrics = [];
    window.__workpassPayslipMetrics.push(payload);
    if (window.__workpassPayslipMetrics.length > 80) {
      window.__workpassPayslipMetrics = window.__workpassPayslipMetrics.slice(-80);
    }
  } catch {
    /* ignore */
  }
  try {
    if (window.WP_TELEMETRY?.track) {
      window.WP_TELEMETRY.track("payslip." + payload.name, payload);
    }
  } catch {
    /* ignore */
  }
}

export function readPayslipFilterPrefs() {
  try {
    const raw = sessionStorage.getItem(PAYSLIP_FILTERS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export function writePayslipFilterPrefs(state) {
  try {
    sessionStorage.setItem(
      PAYSLIP_FILTERS_KEY,
      JSON.stringify({
        inbox: state.inbox === "archive" ? "archive" : "open",
        archiveQuery: String(state.archiveQuery || ""),
        archiveStatus: String(state.archiveStatus || "all"),
        openFilter: String(state.openFilter || "all"),
        docTypeFilter: String(state.docTypeFilter || "all"),
        archivePeriod: String(state.archivePeriod || ""),
        filtersExpanded: Boolean(state.filtersExpanded),
        autoAdvanceAfterSend: state.autoAdvanceAfterSend !== false,
      }),
    );
  } catch {
    /* ignore */
  }
}

export function applyPayslipFilterPrefs(state) {
  const prefs = readPayslipFilterPrefs();
  if (!prefs) return state;
  if (prefs.inbox === "archive" || prefs.inbox === "open") state.inbox = prefs.inbox;
  if (typeof prefs.archiveQuery === "string") state.archiveQuery = prefs.archiveQuery;
  if (prefs.archiveStatus) state.archiveStatus = prefs.archiveStatus;
  if (prefs.openFilter) state.openFilter = prefs.openFilter;
  if (prefs.docTypeFilter) state.docTypeFilter = prefs.docTypeFilter;
  if (typeof prefs.archivePeriod === "string") state.archivePeriod = prefs.archivePeriod;
  if (typeof prefs.filtersExpanded === "boolean") state.filtersExpanded = prefs.filtersExpanded;
  if (typeof prefs.autoAdvanceAfterSend === "boolean") state.autoAdvanceAfterSend = prefs.autoAdvanceAfterSend;
  return state;
}

export function isPayslipKeysHintDismissed() {
  try {
    return sessionStorage.getItem(PAYSLIP_KEYS_HINT_DISMISS_KEY) === "1";
  } catch {
    return false;
  }
}

export function dismissPayslipKeysHint() {
  try {
    sessionStorage.setItem(PAYSLIP_KEYS_HINT_DISMISS_KEY, "1");
  } catch {
    /* ignore */
  }
}

export function paginatePayslipBatches(batches, visibleCount) {
  const list = Array.isArray(batches) ? batches : [];
  const n = Math.max(PAYSLIP_LIST_PAGE_SIZE, Number(visibleCount) || PAYSLIP_LIST_PAGE_SIZE);
  return {
    visible: list.slice(0, n),
    total: list.length,
    hasMore: list.length > n,
    remaining: Math.max(0, list.length - n),
  };
}

export function payslipMatchHint(matchStatus, t) {
  const match = String(matchStatus || "matched");
  const tr = typeof t === "function" ? t : () => "";
  if (match === "unmatched") {
    return tr("lohn.matchHintUnmatched") || "Kein Mitarbeiter erkannt — bitte manuell zuweisen.";
  }
  if (match === "ambiguous") {
    return tr("lohn.matchHintAmbiguous") || "Mehrere Treffer möglich — Zuordnung prüfen und speichern.";
  }
  if (match === "matched") {
    return tr("lohn.matchHintMatched") || "Mitarbeiter erkannt. Bei Fehler Zuordnung ändern.";
  }
  return "";
}

export function payslipEmptyStateHtml({ title, body, actionsHtml = "", escapeHtml }) {
  const esc = typeof escapeHtml === "function" ? escapeHtml : (s) => String(s ?? "");
  return `<div class="payslip-studio-empty payslip-empty-rich" role="status">
    <strong class="payslip-empty-title">${esc(title)}</strong>
    <p class="payslip-empty-body">${esc(body)}</p>
    ${actionsHtml || ""}
  </div>`;
}

export function downloadPayslipAuditCsv(rows, filename = "payslip-protokoll.csv") {
  const list = Array.isArray(rows) ? rows : [];
  const header = ["status", "name", "kind", "period", "amount", "at", "source"];
  const lines = [header.join(";")];
  for (const row of list) {
    const cells = [
      row.status || row.action || "",
      row.name || "",
      row.kind || "",
      row.period || "",
      row.amount || "",
      row.at || "",
      row.source || "",
    ].map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`);
    lines.push(cells.join(";"));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
  trackPayslipMetric("audit_csv_export", { rows: list.length });
}

/**
 * Promise-based confirm dialog using #payslipConfirmModal markup.
 * @returns {Promise<boolean>}
 */
export function openPayslipConfirmModal({
  title,
  body,
  warnings = [],
  confirmLabel,
  cancelLabel,
  danger = false,
} = {}) {
  const modal = document.getElementById("payslipConfirmModal");
  if (!modal) {
    return Promise.resolve(window.confirm([title, body, ...(warnings || [])].filter(Boolean).join("\n\n")));
  }
  const titleEl = document.getElementById("payslipConfirmTitle");
  const bodyEl = document.getElementById("payslipConfirmBody");
  const warnEl = document.getElementById("payslipConfirmWarnings");
  const okBtn = document.getElementById("payslipConfirmOk");
  const cancelBtn = document.getElementById("payslipConfirmCancel");
  const backdrop = document.getElementById("payslipConfirmBackdrop");
  if (titleEl) titleEl.textContent = title || "";
  if (bodyEl) bodyEl.textContent = body || "";
  if (warnEl) {
    if (warnings?.length) {
      warnEl.classList.remove("hidden");
      warnEl.innerHTML = `<ul>${warnings
        .slice(0, 10)
        .map((w) => `<li>${String(w).replace(/</g, "&lt;")}</li>`)
        .join("")}</ul>`;
    } else {
      warnEl.classList.add("hidden");
      warnEl.innerHTML = "";
    }
  }
  if (okBtn) {
    okBtn.textContent = confirmLabel || "OK";
    okBtn.classList.toggle("danger", Boolean(danger));
  }
  if (cancelBtn) cancelBtn.textContent = cancelLabel || "Abbrechen";
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");
  document.body.classList.add("payslip-confirm-open");
  okBtn?.focus?.();

  return new Promise((resolve) => {
    const finish = (ok) => {
      modal.classList.add("hidden");
      modal.setAttribute("aria-hidden", "true");
      document.body.classList.remove("payslip-confirm-open");
      okBtn?.removeEventListener("click", onOk);
      cancelBtn?.removeEventListener("click", onCancel);
      backdrop?.removeEventListener("click", onCancel);
      document.removeEventListener("keydown", onKey);
      resolve(Boolean(ok));
    };
    const onOk = () => finish(true);
    const onCancel = () => finish(false);
    const onKey = (ev) => {
      if (ev.key === "Escape") {
        ev.preventDefault();
        finish(false);
      } else if (ev.key === "Enter") {
        ev.preventDefault();
        finish(true);
      }
    };
    okBtn?.addEventListener("click", onOk);
    cancelBtn?.addEventListener("click", onCancel);
    backdrop?.addEventListener("click", onCancel);
    document.addEventListener("keydown", onKey);
  });
}
