    const WP = window.WorkPassStorage;
    const wpGet = (key) => (WP?.getItem ? WP.getItem(key) : localStorage.getItem(key));
    const params = new URLSearchParams(location.search);
    const companyId = params.get("company_id") || wpGet(WP?.KEYS?.ADMIN_COMPANY || "workpass-admin-company") || "";
    const token = wpGet(WP?.KEYS?.ADMIN_TOKEN || "workpass-admin-token") || wpGet(WP?.KEYS?.SESSION_TOKEN || "workpass-session-token") || "";
    let currentContractId = "";
    let adminPdfPreviewObjectUrl = null;
    let contracts = [];
    let toolbarBusy = false;
    let workers = [];
    let baselineDraftText = "";
    let templateMeta = {};
    let lastSignSessions = [];
    let lastContractEvents = [];
    let salaryFieldsRedacted = false;
    let contractsSessionUnlocked = false;
    const SENSITIVE_FIELD_IDS = ["salaryType", "salaryMonthly", "salaryHourly", "currency", "contractEditor"];
    const TOOLBAR_BTN_IDS = ["generateBtn", "saveBtn", "pdfBtn", "printBtn", "signLinkEmployeeBtn", "signLinkEmployerBtn", "signEmailEmployeeBtn", "signEmailEmployerBtn", "signSmsEmployeeBtn", "deleteBtn"];

    function setStatus(text, { active = false, error = false } = {}) {
      const el = document.getElementById("statusLine");
      el.textContent = text;
      if (text) el.dataset.dynamic = "1";
      else delete el.dataset.dynamic;
      el.classList.toggle("is-active", active);
      el.classList.toggle("is-error", error);
    }

    function setToolbarBusy(activeId, statusText) {
      toolbarBusy = true;
      TOOLBAR_BTN_IDS.forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.disabled = true;
        el.classList.toggle("is-busy", id === activeId);
        el.classList.remove("is-ok", "is-warn");
      });
      if (statusText) setStatus(statusText, { active: true });
    }

    function clearToolbarBusy(okId) {
      toolbarBusy = false;
      TOOLBAR_BTN_IDS.forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.disabled = false;
        el.classList.remove("is-busy");
        if (okId && id === okId) {
          el.classList.add("is-ok");
          setTimeout(() => el.classList.remove("is-ok"), 1200);
        }
      });
    }

    function flashButtonWarn(btnId, message) {
      const el = document.getElementById(btnId);
      el?.classList.add("is-warn");
      setStatus(message, { error: true });
      setTimeout(() => {
        el?.classList.remove("is-warn");
        document.getElementById("statusLine")?.classList.remove("is-error");
      }, 1600);
    }

    async function withToolbarAction(btnId, statusMsg, fn) {
      if (toolbarBusy) return;
      const unlocked = await ensureUnlockedForMutation();
      if (!unlocked) return;
      setToolbarBusy(btnId, statusMsg);
      try {
        await fn();
        clearToolbarBusy(btnId);
      } catch (e) {
        clearToolbarBusy();
        if (e?.data?.error === "contracts_locked" || e?.data?.stepUpRequired) {
          salaryFieldsRedacted = true;
          contractsSessionUnlocked = false;
          applyRedactionUi(true);
          showLockOverlay({ setup: false });
        }
        setStatus(mapApiError(e), { error: true });
        throw e;
      }
    }

    function requireContract(btnId) {
      if (currentContractId) return true;
      flashButtonWarn(btnId, window.contractPageT("statusNoContract"));
      return false;
    }

    async function generateContractDraft() {
      const payload = {
        ...contractFormPayload(),
        parent_contract_id: document.getElementById("parentContractId").value || "",
        existing_text: document.getElementById("contractEditor").value.trim(),
      };
      if (currentContractId) {
        const data = await api(`/api/contracts/${encodeURIComponent(currentContractId)}/regenerate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        document.getElementById("contractEditor").value = data.contract?.final_text || data.contract?.draft_text || "";
        setStatus(window.contractPageT("statusDraftUpdated", { id: currentContractId }), { active: true });
      } else {
        const data = await api("/api/contracts/draft", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        currentContractId = data.contract?.id || "";
        document.getElementById("contractEditor").value = data.contract?.draft_text || data.contract?.final_text || "";
        setStatus(window.contractPageT("statusDraftCreated", { id: currentContractId }), { active: true });
      }
      await loadContracts();
    }

    async function submitNotesToAi() {
      const notesEl = document.getElementById("notes");
      const notes = notesEl.value.trim();
      if (!notes) {
        setStatus(window.contractPageT("statusNotesRequired"), { error: true });
        notesEl.focus();
        document.getElementById("notesSendBtn")?.classList.add("is-warn");
        setTimeout(() => document.getElementById("notesSendBtn")?.classList.remove("is-warn"), 800);
        return;
      }
      const sendBtn = document.getElementById("notesSendBtn");
      sendBtn?.classList.add("is-busy");
      sendBtn?.setAttribute("disabled", "disabled");
      try {
        await withToolbarAction("generateBtn", window.contractPageT("statusGenerating"), generateContractDraft);
        notesEl.value = "";
      } finally {
        sendBtn?.classList.remove("is-busy");
        sendBtn?.removeAttribute("disabled");
      }
    }

    function contractVoiceOptions() {
      const lang = document.getElementById("language").value;
      return {
        inputId: "notes",
        buttonId: "notesVoiceBtn",
        sendId: "notesSendBtn",
        hintId: "notesVoiceHint",
        lang,
        voiceReply: false,
        onTranscript: () => {
          submitNotesToAi().catch(() => {});
        },
        onListening: (active) => {
          const hint = document.getElementById("notesVoiceHint");
          if (!hint) return;
          hint.textContent = active
            ? window.contractPageT("voiceListening")
            : window.contractPageT("voiceHint");
          hint.classList.toggle("is-listening", active);
        },
        onTranscribing: (active) => {
          const hint = document.getElementById("notesVoiceHint");
          if (!hint) return;
          hint.textContent = active
            ? window.contractPageT("voiceTranscribing")
            : window.contractPageT("voiceHint");
          hint.classList.toggle("is-listening", active);
        },
      };
    }
    window.contractVoiceOptions = contractVoiceOptions;

    function bindNotesComposer() {
      window.BaupassAiUi?.bindVoiceInput?.(contractVoiceOptions());
      document.getElementById("notesSendBtn")?.addEventListener("click", () => {
        submitNotesToAi().catch(() => {});
      });
      document.getElementById("notes")?.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" && !ev.shiftKey) {
          ev.preventDefault();
          submitNotesToAi().catch(() => {});
        }
      });
    }
    const headers = () => ({ "Accept": "application/json", ...(token ? { "Authorization": `Bearer ${token}` } : {}) });
    const api = async (path, options = {}) => {
      const res = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) }, credentials: "include" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const err = new Error(data.error || data.message || res.statusText);
        err.data = data;
        err.status = res.status;
        if (data.error === "missing_fields" && Array.isArray(data.fields)) {
          err.message = window.contractPageT("statusMissingFields", { fields: data.fields.join(", ") });
        } else if (data.error === "recipient_email_required") {
          err.message = window.contractPageT("emailRecipientMissing");
        } else if (data.error === "sms_not_configured") {
          err.message = window.contractPageT("smsNotConfigured");
        } else if (data.error === "recipient_phone_required") {
          err.message = window.contractPageT("smsRecipientMissing");
        }
        throw err;
      }
      return data;
    };
    const backLink = document.getElementById("backLink");
    if (companyId) backLink.href = `/admin-v2/index.html?company_id=${encodeURIComponent(companyId)}#operations`;
    document.getElementById("companyId").value = companyId;

    function syncSalaryFields() {
      const hourly = document.getElementById("salaryType").value === "hourly";
      document.getElementById("salaryMonthlyWrap").classList.toggle("hidden", hourly);
      document.getElementById("salaryHourlyWrap").classList.toggle("hidden", !hourly);
    }
    document.getElementById("salaryType").addEventListener("change", syncSalaryFields);
    syncSalaryFields();

    const JURISDICTION_DEFAULTS = {
      DE: { currency: "EUR", language: "de" },
      AT: { currency: "EUR", language: "de" },
      CH: { currency: "CHF", language: "de" },
      FR: { currency: "EUR", language: "fr" },
      NL: { currency: "EUR", language: "en" },
      BE: { currency: "EUR", language: "en" },
      IT: { currency: "EUR", language: "it" },
      ES: { currency: "EUR", language: "es" },
      PL: { currency: "PLN", language: "pl" },
      EU: { currency: "EUR", language: "en" },
      SA: { currency: "SAR", language: "ar" },
      AE: { currency: "AED", language: "ar" },
      QA: { currency: "QAR", language: "ar" },
      KW: { currency: "KWD", language: "ar" },
      BH: { currency: "BHD", language: "ar" },
      OM: { currency: "OMR", language: "ar" },
      JO: { currency: "JOD", language: "ar" },
      LB: { currency: "LBP", language: "ar" },
      EG: { currency: "EGP", language: "ar" },
      TR: { currency: "TRY", language: "tr" },
      US: { currency: "USD", language: "en" },
      CA: { currency: "CAD", language: "en" },
      MX: { currency: "MXN", language: "en" },
      BR: { currency: "BRL", language: "en" },
      IN: { currency: "INR", language: "en" },
      PK: { currency: "PKR", language: "en" },
      SG: { currency: "SGD", language: "en" },
      MY: { currency: "MYR", language: "en" },
      AU: { currency: "AUD", language: "en" },
      MA: { currency: "MAD", language: "ar" },
      TN: { currency: "TND", language: "ar" },
      ZA: { currency: "ZAR", language: "en" },
      INT: { currency: "EUR", language: "en" },
    };
    const JURISDICTION_GROUPS = [
      { groupKey: "jGroupEurope", codes: ["DE", "AT", "CH", "FR", "NL", "BE", "IT", "ES", "PL", "EU"] },
      { groupKey: "jGroupMiddleEast", codes: ["SA", "AE", "QA", "KW", "BH", "OM", "JO", "LB", "EG", "TR"] },
      { groupKey: "jGroupAmericas", codes: ["US", "CA", "MX", "BR"] },
      { groupKey: "jGroupAsiaPacific", codes: ["IN", "PK", "SG", "MY", "AU"] },
      { groupKey: "jGroupAfrica", codes: ["MA", "TN", "ZA"] },
    ];
    const JURISDICTION_STANDALONE = ["INT"];
    function intlLocaleForContractPage(lang) {
      const map = { de: "de", en: "en", ar: "ar", tr: "tr", fr: "fr", es: "es", it: "it", pl: "pl" };
      return map[lang] || "en";
    }
    function countryLabelForJurisdiction(code) {
      if (code === "EU") return window.contractPageT("jEU");
      if (code === "INT") return window.contractPageT("jINT");
      try {
        const lang = window.getContractPageLang();
        const dn = new Intl.DisplayNames([intlLocaleForContractPage(lang)], { type: "region" });
        return dn.of(code) || code;
      } catch {
        return code;
      }
    }
    function renderJurisdictionSelect() {
      const sel = document.getElementById("jurisdiction");
      if (!sel) return;
      const prev = sel.value || "DE";
      sel.innerHTML = "";
      JURISDICTION_GROUPS.forEach(({ groupKey, codes }) => {
        const og = document.createElement("optgroup");
        og.label = window.contractPageT(groupKey);
        codes.forEach((code) => {
          const opt = document.createElement("option");
          opt.value = code;
          opt.textContent = countryLabelForJurisdiction(code);
          og.appendChild(opt);
        });
        sel.appendChild(og);
      });
      JURISDICTION_STANDALONE.forEach((code) => {
        const opt = document.createElement("option");
        opt.value = code;
        opt.textContent = countryLabelForJurisdiction(code);
        sel.appendChild(opt);
      });
      sel.value = [...sel.options].some((o) => o.value === prev) ? prev : "DE";
    }
    function eventTypeLabel(type) {
      const map = {
        "contract.created": "eventCreated",
        "contract.regenerated": "eventRegenerated",
        "contract.updated": "eventUpdated",
        "contract.pdf_generated": "eventPdfGenerated",
        "sign_link.created": "eventSignLinkCreated",
        "sign_link.sms": "eventSignLinkSms",
        "sign_link.reminder": "eventSignLinkReminder",
        "contract.signed": "eventSigned",
        "contract.sign_notify": "eventSignNotify",
      };
      const key = map[type];
      return key ? window.contractPageT(key) : (type || window.contractPageT("eventGeneric"));
    }
    window.refreshContractPageDynamicUi = function refreshContractPageDynamicUi() {
      renderJurisdictionSelect();
      updateSigningHint();
      renderContractList();
      renderSignSessions(lastSignSessions);
      renderEvents(lastContractEvents);
      checkIntegrations();
      const workerManual = document.querySelector("#workerPicker option[value='']");
      if (workerManual) workerManual.textContent = window.contractPageT("workerPickerManual");
    };
    function syncLocaleFromJurisdiction(force = false) {
      const code = document.getElementById("jurisdiction").value;
      const defaults = JURISDICTION_DEFAULTS[code] || JURISDICTION_DEFAULTS.INT;
      const currencySelect = document.getElementById("currency");
      if (force || !currencySelect.dataset.userSet) currencySelect.value = defaults.currency;
      if (force) document.getElementById("language").value = defaults.language;
      updateSigningHint();
      window.BaupassAiUi?.refreshComposerLabels?.(contractVoiceOptions());
    }
    function updateSigningHint() {
      const jurisdictionLabel = document.getElementById("jurisdiction").selectedOptions[0]?.textContent || "";
      const fullHint = `${window.contractPageT("signingHint").replace(/<[^>]+>/g, "")} · ${window.contractPageT("jurisdictionLabel")}: ${jurisdictionLabel}`;
      const hintEl = document.getElementById("signingHint");
      hintEl.textContent = window.contractPageT("signingShort");
      hintEl.title = fullHint;
    }
    document.getElementById("jurisdiction").addEventListener("change", () => syncLocaleFromJurisdiction(true));
    document.getElementById("language").addEventListener("change", updateSigningHint);
    document.getElementById("currency").addEventListener("change", () => { document.getElementById("currency").dataset.userSet = "1"; });

    function contractFormPayload() {
      const hourly = document.getElementById("salaryType").value === "hourly";
      const salaryMonthly = (document.getElementById("salaryMonthly").value || "").trim();
      const salaryHourly = (document.getElementById("salaryHourly").value || "").trim();
      const compensation = hourly
        ? { salary_type: "hourly", hourly_rate: salaryHourly, salary_gross_monthly: "" }
        : { salary_type: "monthly_fixed", salary_gross_monthly: salaryMonthly, hourly_rate: "" };
      return {
        company_id: companyId,
        template_id: document.getElementById("templateId").value,
        worker_id: document.getElementById("workerId").value || undefined,
        title: document.getElementById("contractTitle").value,
        language: document.getElementById("language").value,
        notes: document.getElementById("notes").value,
        form: {
          employee_name: document.getElementById("employeeName").value,
          employee_gender: document.getElementById("employeeGender").value,
          employee_birth_date: document.getElementById("employeeBirthDate").value,
          employee_email: document.getElementById("employeeEmail").value,
          employee_phone: document.getElementById("employeePhone").value,
          employee_address: document.getElementById("employeeAddress").value,
          employee_nationality: document.getElementById("employeeNationality").value,
          employee_work_permit: document.getElementById("employeeWorkPermit").value,
          employee_iban: document.getElementById("employeeIban").value,
          employee_tax_id: document.getElementById("employeeTaxId").value,
          collective_agreement: document.getElementById("collectiveAgreement").value === "yes" ? "yes" : "",
          collective_agreement_name: document.getElementById("collectiveAgreementName").value,
          job_title: document.getElementById("jobTitle").value,
          jurisdiction: document.getElementById("jurisdiction").value,
          start_date: document.getElementById("startDate").value,
          end_date: document.getElementById("endDate").value,
          work_location: document.getElementById("workLocation").value,
          weekly_hours: document.getElementById("weeklyHours").value,
          vacation_days: document.getElementById("vacationDays").value,
          probation_months: document.getElementById("probationMonths").value,
          currency: document.getElementById("currency").value,
          ...compensation,
        },
      };
    }
    function contractActionPayload() {
      return {
        company_id: companyId,
        final_text: document.getElementById("contractEditor").value,
        parent_contract_id: document.getElementById("parentContractId").value || "",
        ...contractFormPayload(),
      };
    }
    async function saveContractPayloadAsync() {
      const payload = contractActionPayload();
      const workerId = document.getElementById("workerId").value || "";
      const text = String(payload.final_text || "").trim();
      if (text && window.E2EAdminBridge?.cryptoReady?.() && !window.E2ECrypto.isE2EEnvelope(text)) {
        payload.final_text = await window.E2EAdminBridge.encryptField(text, workerId, companyId);
      }
      return payload;
    }
    function saveContractPayload() {
      return contractActionPayload();
    }
    function currentTemplateMeta() {
      const tid = document.getElementById("templateId").value;
      return templateMeta[tid] || {};
    }
    function validateBeforeAction() {
      window.ContractFormValidate?.clearFieldErrors?.();
      const form = contractFormPayload().form;
      const meta = currentTemplateMeta();
      let extra = [];
      try { extra = JSON.parse(meta.required_fields_json || "[]"); } catch { extra = []; }
      const result = window.ContractFormValidate.validateForm(form, {
        contractType: meta.contract_type || "employment",
        templateRequired: extra,
      });
      if (!result.ok) {
        window.ContractFormValidate.highlightFields(result.missingKeys);
        setStatus(window.contractPageT("statusMissingFields", { fields: result.missing.join(", ") }), { error: true });
        return false;
      }
      const text = document.getElementById("contractEditor").value.trim();
      if (!text) {
        setStatus(window.contractPageT("statusNotesRequired"), { error: true });
        return false;
      }
      return true;
    }
    function syncParentContractField() {
      const meta = currentTemplateMeta();
      const wrap = document.getElementById("parentContractWrap");
      const show = meta.contract_type === "amendment";
      wrap.classList.toggle("hidden", !show);
    }
    async function fetchContractPreviewBlob() {
      if (!currentContractId) throw new Error(window.contractPageT("statusNoContract"));
      await persistContract();
      const text = document.getElementById("contractEditor").value || "";
      const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>Vertrag</title></head><body style="font-family:Georgia,serif;padding:2rem;white-space:pre-wrap;line-height:1.45;">${String(text).replace(/&/g,"&amp;").replace(/</g,"&lt;")}</body></html>`;
      return new Blob([html], { type: "text/html" });
    }
    async function setEditorMode(mode) {
      const pdf = mode === "pdf";
      document.getElementById("tabEditorText").classList.toggle("active", !pdf);
      document.getElementById("tabEditorPdf").classList.toggle("active", pdf);
      document.getElementById("contractEditor").style.display = pdf ? "none" : "";
      const frame = document.getElementById("adminPdfPreview");
      frame.style.display = pdf ? "block" : "none";
      if (!pdf) return;
      if (!currentContractId) {
        frame.removeAttribute("src");
        return;
      }
      try {
        if (salaryFieldsRedacted) {
          const unlocked = await ensureUnlockedForMutation();
          if (!unlocked || salaryFieldsRedacted) {
            frame.removeAttribute("src");
            setStatus(window.contractPageT("salaryRedactedBanner") || "Gehalt gesperrt", { error: true });
            return;
          }
        }
        setStatus(window.contractPageT("statusWorking"));
        const blob = await fetchContractPreviewBlob();
        if (adminPdfPreviewObjectUrl) URL.revokeObjectURL(adminPdfPreviewObjectUrl);
        adminPdfPreviewObjectUrl = URL.createObjectURL(blob);
        frame.src = adminPdfPreviewObjectUrl;
        setStatus("");
      } catch (e) {
        frame.removeAttribute("src");
        setStatus(mapApiError(e), { error: true });
      }
    }
    async function loadEvents() {
      if (!currentContractId) return;
      try {
        const data = await api(`/api/contracts/${encodeURIComponent(currentContractId)}/events?company_id=${encodeURIComponent(companyId)}`);
        renderEvents(data.events || []);
      } catch {
        renderEvents([]);
      }
    }
    function renderEvents(events) {
      lastContractEvents = events || [];
      const panel = document.getElementById("eventsPanel");
      const list = document.getElementById("eventsList");
      if (!panel || !list) return;
      if (!currentContractId || !lastContractEvents.length) {
        panel.classList.add("hidden");
        list.innerHTML = "";
        return;
      }
      panel.classList.remove("hidden");
      list.innerHTML = lastContractEvents.slice(0, 12).map((ev) => {
        const ts = (ev.created_at || "").slice(0, 16).replace("T", " ");
        const label = eventTypeLabel(ev.event_type);
        return `<li>${ts} · ${label}</li>`;
      }).join("");
    }
    async function checkIntegrations() {
      const el = document.getElementById("integrationsHint");
      if (!el || !companyId) return;
      try {
        const data = await api(`/api/contracts/integrations-status?company_id=${encodeURIComponent(companyId)}`);
        const parts = [];
        if (!data.emailConfigured) parts.push(window.contractPageT("emailNotConfigured"));
        if (!data.smsConfigured) parts.push(window.contractPageT("smsNotConfigured"));
        if (parts.length) {
          el.textContent = parts.join(" · ");
          el.classList.remove("hidden");
        } else {
          el.classList.add("hidden");
        }
      } catch {
        el.classList.add("hidden");
      }
    }
    function mapApiError(e) {
      const code = e?.data?.error || e?.message || "";
      if (code === "recipient_email_required") return window.contractPageT("emailRecipientMissing");
      if (code === "recipient_phone_required") return window.contractPageT("smsRecipientMissing");
      if (code === "sms_not_configured") return window.contractPageT("smsNotConfigured");
      if (code === "sms_send_failed") return window.contractPageT("smsSendFailed");
      if (code === "contracts_locked") return window.contractPageT("lockDesc") || "Vertragszugang gesperrt.";
      if (code === "otp_invalid") return window.contractPageT("lockCodeRequired") || "Code ungültig.";
      if (code === "otp_delivery_failed") return e?.data?.message || "Code konnte nicht gesendet werden.";
      if (code === "invalid_phone") return "Ungültige Handynummer (+49…).";
      if (code === "rate_limited") return `Zu viele Versuche. Bitte ${e?.data?.retryInSeconds || 60}s warten.`;
      return e.message || window.contractPageT("statusError");
    }
    async function persistContract() {
      if (!currentContractId) return;
      if (salaryFieldsRedacted) {
        throw Object.assign(new Error(window.contractPageT("salaryRedactedBanner") || "Gehalt gesperrt"), {
          data: { error: "contracts_locked", stepUpRequired: true },
        });
      }
      const body = await saveContractPayloadAsync();
      await api(`/api/contracts/${encodeURIComponent(currentContractId)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    }
    function signStatusBadge(row) {
      const map = {
        draft: ["draft", "statusDraft"],
        ready: ["ready", "statusReady"],
        awaiting_signature: ["awaiting", "statusAwaiting"],
        partially_signed: ["partial", "statusPartial"],
        fully_signed: ["signed", "statusSigned"],
      };
      const key = row.signStatus || row.status || "draft";
      const [cls, i18n] = map[key] || ["draft", "statusDraft"];
      return `<span class="status-badge ${cls}">${window.contractPageT(i18n)}</span>`;
    }
    function renderSignSessions(sessions) {
      lastSignSessions = sessions || [];
      const panel = document.getElementById("signStatusPanel");
      const list = document.getElementById("signSessionList");
      if (!panel || !list) return;
      const rows = lastSignSessions;
      if (!currentContractId || !rows.length) {
        panel.classList.add("hidden");
        list.innerHTML = "";
        return;
      }
      panel.classList.remove("hidden");
      list.innerHTML = rows.slice(0, 6).map((s) => {
        const role = s.role === "employer" ? window.contractPageT("roleEmployer") : window.contractPageT("roleEmployee");
        const st = s.effectiveStatus || s.status || "pending";
        const stLabel = window.contractPageT(`signSession_${st}`) || st;
        const exp = (s.expires_at || "").slice(0, 10);
        return `<li>${role}: ${stLabel}${exp ? ` · ${exp}` : ""}${s.signer_name ? ` — ${s.signer_name}` : ""}</li>`;
      }).join("");
    }
    async function fillFormFromContract(data) {
      const input = data.input_json ? (typeof data.input_json === "string" ? JSON.parse(data.input_json) : data.input_json) : {};
      const form = input.form || {};
      const redacted = !!(data.salaryRedacted || data.bodyRedacted);
      if (redacted) {
        salaryFieldsRedacted = true;
        applyRedactionUi(true);
      }
      document.getElementById("contractTitle").value = data.title || "";
      if (data.template_id) document.getElementById("templateId").value = data.template_id;
      syncParentContractField();
      document.getElementById("parentContractId").value = data.parent_contract_id || "";
      document.getElementById("workerId").value = data.worker_id || "";
      document.getElementById("workerPicker").value = data.worker_id || "";
      document.getElementById("employeeName").value = form.employee_name || `${data.first_name || ""} ${data.last_name || ""}`.trim();
      document.getElementById("employeeGender").value = form.employee_gender || "";
      document.getElementById("employeeBirthDate").value = form.employee_birth_date || form.birth_date || "";
      document.getElementById("employeeEmail").value = form.employee_email || "";
      document.getElementById("employeePhone").value = form.employee_phone || "";
      document.getElementById("employeeAddress").value = form.employee_address || "";
      document.getElementById("employeeNationality").value = form.employee_nationality || "";
      document.getElementById("employeeWorkPermit").value = form.employee_work_permit || "";
      document.getElementById("employeeIban").value = form.employee_iban || "";
      document.getElementById("employeeTaxId").value = form.employee_tax_id || "";
      document.getElementById("collectiveAgreement").value = form.collective_agreement === "yes" ? "yes" : "";
      document.getElementById("collectiveAgreementName").value = form.collective_agreement_name || "";
      document.getElementById("jobTitle").value = form.job_title || "";
      document.getElementById("jurisdiction").value = form.jurisdiction || "DE";
      document.getElementById("language").value = data.language || "de";
      document.getElementById("startDate").value = form.start_date || "";
      document.getElementById("endDate").value = form.end_date || "";
      document.getElementById("workLocation").value = form.work_location || "";
      document.getElementById("weeklyHours").value = form.weekly_hours || "";
      document.getElementById("vacationDays").value = form.vacation_days || "";
      document.getElementById("probationMonths").value = form.probation_months || "";
      document.getElementById("salaryType").value = form.salary_type === "••••" ? "monthly_fixed" : (form.salary_type || "monthly_fixed");
      document.getElementById("currency").value = form.currency || "EUR";
      const monthly = form.salary_gross_monthly || form.gross_monthly || form.monthly_salary || form.salary || "";
      const hourly = form.hourly_rate || form.hourly_wage || "";
      document.getElementById("salaryMonthly").value = redacted && monthly ? (window.contractPageT("salaryRedactedPlaceholder") || "••••") : monthly;
      document.getElementById("salaryHourly").value = redacted && hourly ? (window.contractPageT("salaryRedactedPlaceholder") || "••••") : hourly;
      syncSalaryFields();
      document.getElementById("notes").value = input.notes || "";
      let contractText = data.final_text || data.draft_text || "";
      if (window.E2EAdminBridge && contractText) {
        contractText = await window.E2EAdminBridge.decryptField(contractText);
      }
      if (redacted && !contractText) {
        document.getElementById("contractEditor").value = window.contractPageT("bodyRedactedPlaceholder") || "";
      } else {
        document.getElementById("contractEditor").value = contractText;
      }
      baselineDraftText = data.draft_text || "";
      document.getElementById("diffPanel").classList.add("hidden");
      if (form.currency) document.getElementById("currency").dataset.userSet = "1";
      renderSignSessions(data.sign_sessions || []);
      loadEvents();
      updateSigningHint();
    }
    async function loadWorkers() {
      if (!companyId) return;
      try {
        const data = await api(`/api/workers?company_id=${encodeURIComponent(companyId)}`);
        workers = Array.isArray(data) ? data : (data.workers || []);
        const select = document.getElementById("workerPicker");
        const current = document.getElementById("workerId").value;
        select.innerHTML = `<option value="">${window.contractPageT("workerPickerManual")}</option>` +
          workers.map((w) => {
          const name = `${w.first_name || w.firstName || ""} ${w.last_name || w.lastName || ""}`.trim() || w.id;
          const email = w.contact_email || w.contactEmail || "";
          return `<option value="${w.id}">${name}${email ? ` (${email})` : ""}</option>`;
        }).join("");
        select.value = current || "";
      } catch {
        workers = [];
      }
    }
    document.getElementById("workerPicker")?.addEventListener("change", () => {
      const id = document.getElementById("workerPicker").value;
      document.getElementById("workerId").value = id;
      const worker = workers.find((w) => w.id === id);
      if (!worker) return;
      const first = worker.first_name || worker.firstName || "";
      const last = worker.last_name || worker.lastName || "";
      document.getElementById("employeeName").value = `${first} ${last}`.trim();
      const email = worker.contact_email || worker.contactEmail || "";
      if (email) document.getElementById("employeeEmail").value = email;
      const phone = worker.contact_phone || worker.contactPhone || "";
      if (phone) document.getElementById("employeePhone").value = phone;
      const addr = worker.home_address || worker.homeAddress || "";
      if (addr) document.getElementById("employeeAddress").value = addr;
      const birth = worker.birth_date || worker.birthDate || "";
      if (birth) document.getElementById("employeeBirthDate").value = birth.slice(0, 10);
      const gender = worker.gender || worker.employee_gender || "";
      if (gender) document.getElementById("employeeGender").value = gender;
      if (worker.role && !document.getElementById("jobTitle").value) {
        document.getElementById("jobTitle").value = worker.role;
      }
      if (worker.site && !document.getElementById("workLocation").value) {
        document.getElementById("workLocation").value = worker.site;
      }
    });
    function renderDiffPanel() {
      const panel = document.getElementById("diffPanel");
      const current = document.getElementById("contractEditor").value;
      const base = baselineDraftText || "";
      if (!base || base === current) {
        panel.innerHTML = window.contractPageT("diffEmpty");
        panel.classList.remove("hidden");
        return;
      }
      const baseLines = base.split("\n");
      const curLines = current.split("\n");
      const max = Math.max(baseLines.length, curLines.length);
      const changes = [];
      for (let i = 0; i < max; i++) {
        const a = baseLines[i] ?? "";
        const b = curLines[i] ?? "";
        if (a !== b) {
          if (a) changes.push(`<span class="diff-del">− ${escapeHtml(a)}</span>`);
          if (b) changes.push(`<span class="diff-add">+ ${escapeHtml(b)}</span>`);
        }
      }
      panel.innerHTML = changes.slice(0, 60).join("<br>") || window.contractPageT("diffEmpty");
      panel.classList.remove("hidden");
    }
    function escapeHtml(s) {
      return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }
    async function createSignLinkSms(role) {
      if (!validateBeforeAction()) return;
      await persistContract();
      const data = await api(`/api/contracts/${encodeURIComponent(currentContractId)}/sign-link/sms`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...contractActionPayload(), role, renew: false }),
      });
      setStatus(window.contractPageT("smsSent", { phone: data.recipient || "" }), { active: true });
      const detail = await api(`/api/contracts/${encodeURIComponent(currentContractId)}?company_id=${encodeURIComponent(companyId)}`);
      renderSignSessions(detail.sign_sessions || []);
    }
    async function loadTemplates() {
      const data = await api(`/api/contracts/templates?company_id=${encodeURIComponent(companyId)}`);
      const select = document.getElementById("templateId");
      select.innerHTML = (data.templates || []).map((row) => `<option value="${row.id}">${row.name}</option>`).join("");
    }
    async function loadContracts() {
      const data = await api(`/api/contracts?company_id=${encodeURIComponent(companyId)}`);
      contracts = data.contracts || [];
      if (data.salaryRedacted) {
        salaryFieldsRedacted = true;
        applyRedactionUi(true);
      }
      renderContractList();
    }
    function renderContractList() {
      const q = (document.getElementById("contractSearch").value || "").trim().toLowerCase();
      const host = document.getElementById("contractList");
      const rows = contracts.filter((row) => {
        const text = `${row.title || ""} ${row.worker_id || ""} ${row.first_name || ""} ${row.last_name || ""}`.toLowerCase();
        return !q || text.includes(q);
      });
      host.innerHTML = rows.length
        ? rows.map((row) => `<button type="button" class="contract-item${row.id === currentContractId ? " active" : ""}" data-id="${row.id}"><strong>${row.title || row.contract_type}</strong><br><span class="muted">${row.first_name || ""} ${row.last_name || ""}</span><br>${signStatusBadge(row)}</button>`).join("")
        : `<p class="muted">${window.contractPageT("noContracts")}</p>`;
      host.querySelectorAll("[data-id]").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const data = await api(`/api/contracts/${btn.getAttribute("data-id")}?company_id=${encodeURIComponent(companyId)}`);
          currentContractId = data.id || "";
          await fillFormFromContract(data);
          setStatus(`${data.title || data.id}`, { active: true });
          renderContractList();
        });
      });
    }
    async function downloadPdfFile(downloadPath) {
      const res = await fetch(downloadPath, { headers: headers(), credentials: "include" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || res.statusText);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${currentContractId || "vertrag"}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }
    function showUpgrade(requiredPlan) {
      document.getElementById("mainRoot").innerHTML = `
        <section class="upgrade-box" style="grid-column:1/-1;margin:auto;">
          <h2>${window.contractPageT("upgradeTitle")}</h2>
          <p class="muted">${window.contractPageT("upgradeBody", { plan: requiredPlan || "professional" })}</p>
          <p><a href="/admin-v2/index.html${companyId ? `?company_id=${encodeURIComponent(companyId)}` : ""}#platform">${window.contractPageT("upgradeLink")}</a></p>
        </section>`;
    }
    async function createSignLink(role, { sendEmail = false, renew = false } = {}) {
      if (!validateBeforeAction()) return;
      await persistContract();
      const data = await api(`/api/contracts/${encodeURIComponent(currentContractId)}/sign-link`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...contractActionPayload(), role, send_email: sendEmail, renew }),
      });
      const url = data.absoluteUrl || `${location.origin}${data.signUrl}`;
      if (sendEmail && data.emailSent) {
        setStatus(window.contractPageT("emailSent", { email: data.recipient || "" }), { active: true });
      } else {
        try {
          await navigator.clipboard.writeText(url);
          setStatus(window.contractPageT("linkCopied"), { active: true });
        } catch {
          window.prompt(window.contractPageT("linkCreated"), url);
          setStatus(window.contractPageT("linkCreated"), { active: true });
        }
      }
      const detail = await api(`/api/contracts/${encodeURIComponent(currentContractId)}?company_id=${encodeURIComponent(companyId)}`);
      renderSignSessions(detail.sign_sessions || []);
      await loadContracts();
    }
    async function ensureAccess() {
      if (!companyId) {
        setStatus(window.contractPageT("selectCompany"), { error: true });
        return false;
      }
      try {
        const me = await api("/api/me");
        if (me.role === "superadmin") {
          /* still need company lock for previewed company */
        } else {
          const ent = await api(`/api/platform/entitlements?company_id=${encodeURIComponent(companyId)}`);
          if (!ent.legacyFeatures?.employment_contracts) {
            showUpgrade(ent.planMeta?.minPlan || "professional");
            return false;
          }
        }
      } catch (e) {
        if (e.status === 403 && e.data?.error === "feature_not_available") {
          showUpgrade(e.data.requiredPlan);
          return false;
        }
      }
      return ensureContractsUnlocked();
    }

    let lockSetupMode = false;
    let lockAwaitingCode = false;

    function setLockMsg(text, { error = false, ok = false } = {}) {
      const el = document.getElementById("lockMsg");
      if (!el) return;
      el.textContent = text || "";
      el.classList.toggle("is-error", error);
      el.classList.toggle("is-ok", ok);
    }

    function showLockOverlay({ setup = false, enforced = false, smsConfigured = true } = {}) {
      lockSetupMode = setup;
      lockAwaitingCode = false;
      const overlay = document.getElementById("contractsLockOverlay");
      overlay?.classList.remove("hidden");
      document.getElementById("mainRoot")?.classList.add("hidden");
      document.getElementById("lockSetupBlock")?.classList.toggle("hidden", !setup);
      document.getElementById("lockCodeBlock")?.classList.add("hidden");
      document.getElementById("lockVerifyBtn")?.classList.add("hidden");
      document.getElementById("lockSendBtn")?.classList.remove("hidden");
      // Skip only when setup is optional (not enforced).
      document.getElementById("lockSkipSetupBtn")?.classList.toggle("hidden", !setup || enforced);
      document.getElementById("lockTitle").textContent = setup
        ? (window.contractPageT("lockSetupTitle") || "Owner-Zugang einrichten")
        : (window.contractPageT("lockTitle") || "Vertragszugang");
      document.getElementById("lockDesc").textContent = setup
        ? (enforced
            ? (window.contractPageT("lockSetupRequiredDesc") || "Pflicht: Owner-Handynummer einrichten, sonst bleiben Verträge und sensible Exporte gesperrt.")
            : (window.contractPageT("lockSetupDesc") || "Hinterlegen Sie die Handynummer des Firmeninhabers. Der Code kommt per SMS (E-Mail als Backup)."))
        : (window.contractPageT("lockDesc") || "Gehalt und Verträge sind geschützt. Bitte Code bestätigen.");
      const emailLabel = document.getElementById("lockEmailLabel");
      const hint = document.getElementById("lockDeliveryHint");
      if (!smsConfigured) {
        if (emailLabel) emailLabel.textContent = window.contractPageT("lockEmailRequired") || "E-Mail (erforderlich — SMS nicht konfiguriert)";
        if (hint) hint.textContent = window.contractPageT("lockNoSmsHint") || "Twilio-SMS fehlt. Code geht per E-Mail (SMTP/Resend/Brevo) oder als Debug-Code in der Entwicklung.";
      } else {
        if (emailLabel) emailLabel.textContent = window.contractPageT("lockEmailLabel") || "Backup-E-Mail (optional)";
        if (hint) hint.textContent = window.contractPageT("lockSmsOkHint") || "SMS aktiv. E-Mail als Backup empfohlen.";
      }
      setLockMsg("");
    }

    function hideLockOverlay() {
      document.getElementById("contractsLockOverlay")?.classList.add("hidden");
      document.getElementById("mainRoot")?.classList.remove("hidden");
    }

    function paintUnlockBadge(status) {
      const badge = document.getElementById("contractsUnlockBadge");
      const lockBtn = document.getElementById("contractsLockBtn");
      if (!badge || !lockBtn) return;
      if (status?.ownerSetupRequired) {
        badge.classList.remove("hidden");
        badge.textContent = window.contractPageT("lockSetupRequired") || "🔒 Setup Pflicht";
        badge.title = window.contractPageT("lockSetupRequiredHint") || "Owner-Handy erforderlich";
        lockBtn.classList.add("hidden");
        badge.onclick = () => showLockOverlay({ setup: true, enforced: true, smsConfigured: !!status.smsConfigured });
        return;
      }
      if (!status?.lockRequired) {
        badge.classList.remove("hidden");
        badge.textContent = window.contractPageT("lockNudge") || "🔒 PIN empfohlen";
        badge.title = window.contractPageT("lockNudgeHint") || "Owner-Handy einrichten für Gehaltsschutz";
        lockBtn.classList.add("hidden");
        badge.onclick = () => showLockOverlay({ setup: true, enforced: false, smsConfigured: !!status.smsConfigured });
        return;
      }
      if (status.unlocked) {
        badge.classList.remove("hidden");
        badge.textContent = window.contractPageT("lockUnlocked", { until: (status.unlockedUntil || "").slice(11, 16) }) || "✓ Freigeschaltet";
        badge.title = status.unlockedUntil || "";
        badge.onclick = null;
        lockBtn.classList.remove("hidden");
      } else {
        badge.classList.remove("hidden");
        badge.textContent = window.contractPageT("lockSoftBrowse") || "🔒 Gehalt gesperrt";
        badge.title = window.contractPageT("lockSoftBrowseHint") || "";
        badge.onclick = () => showLockOverlay({ setup: false, enforced: !!status.setupEnforced, smsConfigured: !!status.smsConfigured });
        lockBtn.classList.add("hidden");
      }
    }

    function applyRedactionUi(redacted) {
      const banner = document.getElementById("salaryRedactBanner");
      banner?.classList.toggle("hidden", !redacted);
      const form = document.getElementById("contractForm");
      form?.classList.toggle("field-redacted", !!redacted);
      SENSITIVE_FIELD_IDS.forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.readOnly = !!redacted;
        if (el.tagName === "SELECT") el.disabled = !!redacted;
      });
    }

    async function clearRedactionAndReload() {
      const wasRedacted = salaryFieldsRedacted;
      salaryFieldsRedacted = false;
      contractsSessionUnlocked = true;
      applyRedactionUi(false);
      hideLockOverlay();
      if (!wasRedacted) return;
      await loadContracts();
      if (currentContractId) {
        const detail = await api(`/api/contracts/${encodeURIComponent(currentContractId)}?company_id=${encodeURIComponent(companyId)}`);
        await fillFormFromContract(detail);
      }
    }

    async function ensureUnlockedForMutation() {
      if (contractsSessionUnlocked && !salaryFieldsRedacted) return true;
      const status = await api(`/api/contracts/lock-status?company_id=${encodeURIComponent(companyId)}`);
      paintUnlockBadge(status);
      if (status.ownerSetupRequired) {
        showLockOverlay({ setup: true, enforced: true, smsConfigured: !!status.smsConfigured });
        return new Promise((resolve) => {
          window.__contractsUnlockResolve = resolve;
        });
      }
      if (!status.lockRequired || status.unlocked) {
        await clearRedactionAndReload();
        return true;
      }
      showLockOverlay({ setup: false, enforced: !!status.setupEnforced, smsConfigured: !!status.smsConfigured });
      return new Promise((resolve) => {
        window.__contractsUnlockResolve = resolve;
      });
    }

    async function ensureContractsUnlocked() {
      const status = await api(`/api/contracts/lock-status?company_id=${encodeURIComponent(companyId)}`);
      paintUnlockBadge(status);
      if (status.ownerSetupRequired) {
        salaryFieldsRedacted = true;
        contractsSessionUnlocked = false;
        applyRedactionUi(true);
        showLockOverlay({ setup: true, enforced: true, smsConfigured: !!status.smsConfigured });
        return new Promise((resolve) => {
          window.__contractsUnlockResolve = resolve;
        });
      }
      if (!status.lockRequired) {
        salaryFieldsRedacted = false;
        contractsSessionUnlocked = true;
        applyRedactionUi(false);
        hideLockOverlay();
        return true;
      }
      if (status.unlocked) {
        salaryFieldsRedacted = false;
        contractsSessionUnlocked = true;
        applyRedactionUi(false);
        hideLockOverlay();
        return true;
      }
      // Soft browse: list/read with salary redaction; mutations require OTP.
      salaryFieldsRedacted = true;
      contractsSessionUnlocked = false;
      applyRedactionUi(true);
      hideLockOverlay();
      return true;
    }

    async function sendLockOtp() {
      const sendBtn = document.getElementById("lockSendBtn");
      if (sendBtn?.disabled) return;
      setLockMsg("");
      const phone = document.getElementById("lockOwnerPhone")?.value.trim() || "";
      const email = document.getElementById("lockOwnerEmail")?.value.trim() || "";
      const body = { company_id: companyId, setup: lockSetupMode };
      if (lockSetupMode) {
        body.phone = phone;
      }
      if (email) body.email = email;
      if (sendBtn) sendBtn.disabled = true;
      try {
        const res = await api("/api/contracts/lock/request-otp", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        lockAwaitingCode = true;
        document.getElementById("lockCodeBlock")?.classList.remove("hidden");
        document.getElementById("lockVerifyBtn")?.classList.remove("hidden");
        const via = (res.channels || []).join(" + ") || "SMS/E-Mail";
        const phoneBit = res.phoneMasked ? ` · ${res.phoneMasked}` : "";
        if (res.debugFallback || res.debugCode) {
          setLockMsg(
            res.message || (window.contractPageT("lockDebugFallback") || "Debug-Code (kein SMS/E-Mail-Versand)."),
            { ok: true },
          );
        } else {
          setLockMsg(
            (window.contractPageT("lockCodeSent", { via, phone: phoneBit }) || `Code gesendet (${via}).`),
            { ok: true },
          );
        }
        if (res.debugCode) {
          document.getElementById("lockOtpCode").value = res.debugCode;
        }
        document.getElementById("lockOtpCode")?.focus();
        // Cool-down between sends (default 45s).
        const wait = Math.max(15, Number(res.otpRequestMinSeconds || 45));
        setTimeout(() => { if (sendBtn) sendBtn.disabled = false; }, wait * 1000);
      } catch (e) {
        const retry = Number(e?.data?.retryInSeconds || 45);
        setLockMsg(mapApiError(e), { error: true });
        setTimeout(() => { if (sendBtn) sendBtn.disabled = false; }, Math.max(5, retry) * 1000);
      }
    }

    async function verifyLockOtp() {
      const code = document.getElementById("lockOtpCode")?.value.trim() || "";
      if (!code) {
        setLockMsg(window.contractPageT("lockCodeRequired") || "Bitte Code eingeben.", { error: true });
        return;
      }
      const phone = document.getElementById("lockOwnerPhone")?.value.trim() || "";
      const email = document.getElementById("lockOwnerEmail")?.value.trim() || "";
      const body = { company_id: companyId, code, setup: lockSetupMode };
      if (lockSetupMode) {
        body.phone = phone;
        if (email) body.email = email;
      }
      try {
        const res = await api("/api/contracts/lock/verify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        salaryFieldsRedacted = true; // force reload of unredacted payload
        paintUnlockBadge({ ...res, lockRequired: true, unlocked: true });
        setStatus(window.contractPageT("lockUnlockedToast") || "Vertragsbereich freigeschaltet.", { active: true });
        await clearRedactionAndReload();
        if (typeof window.__contractsUnlockResolve === "function") {
          window.__contractsUnlockResolve(true);
          window.__contractsUnlockResolve = null;
        }
      } catch (e) {
        setLockMsg(mapApiError(e), { error: true });
      }
    }

    document.getElementById("lockSendBtn")?.addEventListener("click", () => { sendLockOtp().catch(() => {}); });
    document.getElementById("lockVerifyBtn")?.addEventListener("click", () => { verifyLockOtp().catch(() => {}); });
    document.getElementById("lockSkipSetupBtn")?.addEventListener("click", () => {
      hideLockOverlay();
      if (typeof window.__contractsUnlockResolve === "function") {
        window.__contractsUnlockResolve(true);
        window.__contractsUnlockResolve = null;
      }
    });
    document.getElementById("salaryUnlockBtn")?.addEventListener("click", () => {
      showLockOverlay({ setup: false });
    });
    document.getElementById("contractsLockBtn")?.addEventListener("click", async () => {
      try {
        await api("/api/contracts/lock", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ company_id: companyId }),
        });
        salaryFieldsRedacted = true;
        contractsSessionUnlocked = false;
        applyRedactionUi(true);
        hideLockOverlay();
        paintUnlockBadge({ lockRequired: true, unlocked: false });
        await loadContracts();
        if (currentContractId) {
          const detail = await api(`/api/contracts/${encodeURIComponent(currentContractId)}?company_id=${encodeURIComponent(companyId)}`);
          await fillFormFromContract(detail);
        }
        setStatus(window.contractPageT("lockSoftBrowse") || "Gehalt gesperrt", { active: true });
      } catch (e) {
        setStatus(mapApiError(e), { error: true });
      }
    });
    document.getElementById("lockOtpCode")?.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") verifyLockOtp().catch(() => {});
    });

    document.getElementById("contractForm").addEventListener("submit", (ev) => ev.preventDefault());
    document.getElementById("contractSearch").addEventListener("input", renderContractList);
    document.getElementById("statusFilter").addEventListener("change", renderContractList);
    document.getElementById("templateId").addEventListener("change", syncParentContractField);
    document.getElementById("tabEditorText").addEventListener("click", () => { setEditorMode("text").catch(() => {}); });
    document.getElementById("tabEditorPdf").addEventListener("click", () => { setEditorMode("pdf").catch(() => {}); });
    document.getElementById("generateBtn").addEventListener("click", () => {
      withToolbarAction("generateBtn", window.contractPageT("statusGenerating"), generateContractDraft).catch(() => {});
    });
    document.getElementById("saveBtn").addEventListener("click", () => {
      if (!requireContract("saveBtn")) return;
      withToolbarAction("saveBtn", window.contractPageT("statusWorking"), async () => {
        await persistContract();
        setStatus(window.contractPageT("statusSaved"), { active: true });
        await loadContracts();
      }).catch(() => {});
    });
    document.getElementById("pdfBtn").addEventListener("click", () => {
      if (!requireContract("pdfBtn")) return;
      if (!validateBeforeAction()) return flashButtonWarn("pdfBtn");
      withToolbarAction("pdfBtn", window.contractPageT("statusWorking"), async () => {
        await persistContract();
        const data = await api(`/api/contracts/${encodeURIComponent(currentContractId)}/generate-pdf`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(contractActionPayload()),
        });
        if (data.download) await downloadPdfFile(data.download);
        setStatus(window.contractPageT("statusPdfReady"), { active: true });
      }).catch(() => {});
    });
    document.getElementById("printBtn").addEventListener("click", () => {
      if (!requireContract("printBtn")) return;
      if (!validateBeforeAction()) return flashButtonWarn("printBtn");
      withToolbarAction("printBtn", window.contractPageT("statusWorking"), async () => {
        await persistContract();
        const data = await api(`/api/contracts/${encodeURIComponent(currentContractId)}/generate-pdf`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(contractActionPayload()),
        });
        if (!data.download) throw new Error("PDF missing");
        const res = await fetch(data.download, { headers: headers(), credentials: "include" });
        if (!res.ok) throw new Error("PDF konnte nicht geladen werden.");
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const win = window.open(url, "_blank");
        if (win) {
          win.addEventListener("load", () => {
            try { win.focus(); win.print(); } catch (_) { /* popup blocked */ }
          });
          setStatus(window.contractPageT("statusPrintReady"), { active: true });
        } else {
          await downloadPdfFile(data.download);
          setStatus(window.contractPageT("statusPdfReady"), { active: true });
        }
        setTimeout(() => URL.revokeObjectURL(url), 120000);
      }).catch(() => {});
    });
    document.getElementById("deleteBtn").addEventListener("click", async () => {
      if (!requireContract("deleteBtn")) return;
      if (!window.confirm("Diesen Vertrag endgültig löschen?")) return;
      await withToolbarAction("deleteBtn", window.contractPageT("statusWorking"), async () => {
        await api(`/api/contracts/${encodeURIComponent(currentContractId)}?company_id=${encodeURIComponent(companyId)}`, { method: "DELETE" });
        currentContractId = "";
        document.getElementById("contractEditor").value = "";
        setStatus(window.contractPageT("statusDeleted"), { active: true });
        await loadContracts();
      }).catch(() => {});
    });
    document.getElementById("signEmailEmployeeBtn").addEventListener("click", () => {
      if (!requireContract("signEmailEmployeeBtn")) return;
      withToolbarAction("signEmailEmployeeBtn", window.contractPageT("statusWorking"), () => createSignLink("employee", { sendEmail: true })).catch(() => {});
    });
    document.getElementById("signEmailEmployerBtn").addEventListener("click", () => {
      if (!requireContract("signEmailEmployerBtn")) return;
      withToolbarAction("signEmailEmployerBtn", window.contractPageT("statusWorking"), () => createSignLink("employer", { sendEmail: true })).catch(() => {});
    });
    document.getElementById("renewSignEmployeeBtn").addEventListener("click", () => {
      if (!requireContract("renewSignEmployeeBtn")) return;
      withToolbarAction("renewSignEmployeeBtn", window.contractPageT("statusWorking"), () => createSignLink("employee", { renew: true })).catch(() => {});
    });
    document.getElementById("renewSignEmployerBtn").addEventListener("click", () => {
      if (!requireContract("renewSignEmployerBtn")) return;
      withToolbarAction("renewSignEmployerBtn", window.contractPageT("statusWorking"), () => createSignLink("employer", { renew: true })).catch(() => {});
    });
    document.getElementById("signSmsEmployeeBtn").addEventListener("click", () => {
      if (!requireContract("signSmsEmployeeBtn")) return;
      withToolbarAction("signSmsEmployeeBtn", window.contractPageT("statusWorking"), () => createSignLinkSms("employee")).catch(() => {});
    });
    document.getElementById("diffBtn").addEventListener("click", renderDiffPanel);
    document.getElementById("signLinkEmployeeBtn").addEventListener("click", () => {
      if (!requireContract("signLinkEmployeeBtn")) return;
      withToolbarAction("signLinkEmployeeBtn", window.contractPageT("statusWorking"), () => createSignLink("employee")).catch(() => {});
    });
    document.getElementById("signLinkEmployerBtn").addEventListener("click", () => {
      if (!requireContract("signLinkEmployerBtn")) return;
      withToolbarAction("signLinkEmployerBtn", window.contractPageT("statusWorking"), () => createSignLink("employer")).catch(() => {});
    });
    window.applyContractPageI18n?.();
    window.initContractPageLangSync?.();
    syncLocaleFromJurisdiction(false);
    bindNotesComposer();
    if (window.BaupassAuth?.resolveTenantBranding) {
      void window.BaupassAuth.resolveTenantBranding({ companyId: companyId || undefined });
    }
    document.getElementById("language").addEventListener("change", () => {
      window.BaupassAiUi?.refreshComposerLabels?.(contractVoiceOptions());
    });
    ensureAccess().then((ok) => {
      if (!ok) return;
      void window.E2EAdminBridge?.ensureIdentity?.();
      window.E2EAdminBridge?.mountSecurityPanel?.(document.getElementById("e2eSecurityHost"), { companyId });
      const preWorker = params.get("worker_id") || "";
      loadTemplates().then(() => loadWorkers()).then(loadContracts).then(checkIntegrations).then(() => {
        if (preWorker) {
          document.getElementById("workerPicker").value = preWorker;
          document.getElementById("workerId").value = preWorker;
          document.getElementById("workerPicker").dispatchEvent(new Event("change"));
        }
      }).catch((e) => { setStatus(e.message, { error: true }); });
    });
