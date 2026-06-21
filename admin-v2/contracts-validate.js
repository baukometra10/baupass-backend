/** Client-side contract form validation (mirrors backend validation.py). */
window.ContractFormValidate = (function () {
  const BASE_REQUIRED = [
    "employee_name",
    "employee_gender",
    "employee_address",
    "job_title",
    "start_date",
    "work_location",
  ];
  const FIELD_IDS = {
    employee_name: "employeeName",
    employee_gender: "employeeGender",
    employee_birth_date: "employeeBirthDate",
    employee_address: "employeeAddress",
    job_title: "jobTitle",
    start_date: "startDate",
    end_date: "endDate",
    work_location: "workLocation",
    weekly_hours: "weeklyHours",
    salary_gross_monthly: "salaryMonthly",
    hourly_rate: "salaryHourly",
    vacation_days: "vacationDays",
    probation_months: "probationMonths",
  };
  const LABELS_DE = {
    employee_name: "Name des Arbeitnehmers",
    employee_gender: "Anrede (Herr/Frau)",
    employee_address: "Adresse",
    job_title: "Position",
    start_date: "Arbeitsbeginn",
    end_date: "Vertragsende",
    work_location: "Arbeitsort",
    weekly_hours: "Wochenstunden",
    salary_gross_monthly: "Bruttogehalt",
    hourly_rate: "Stundenlohn",
    vacation_days: "Urlaubstage",
    probation_months: "Probezeit",
  };

  function isEmpty(v) {
    return !String(v ?? "").trim();
  }

  function cleanAmount(v) {
    return String(v ?? "").trim().replace(/[^\d,.\-]/g, "").replace(/\s/g, "");
  }

  function normalizeForm(form) {
    form = { ...(form || {}) };
    if (isEmpty(form.salary_gross_monthly)) {
      for (const k of ["gross_monthly", "monthly_salary", "salary"]) {
        if (!isEmpty(form[k])) {
          form.salary_gross_monthly = cleanAmount(form[k]);
          break;
        }
      }
    } else {
      form.salary_gross_monthly = cleanAmount(form.salary_gross_monthly);
    }
    if (isEmpty(form.hourly_rate)) {
      for (const k of ["hourly_wage", "salary_hourly"]) {
        if (!isEmpty(form[k])) {
          form.hourly_rate = cleanAmount(form[k]);
          break;
        }
      }
    } else {
      form.hourly_rate = cleanAmount(form.hourly_rate);
    }
    const raw = String(form.salary_type || "").trim().toLowerCase();
    let salaryType = "monthly_fixed";
    if (raw === "hourly" || raw === "hour" || raw === "hourly_wage") salaryType = "hourly";
    else if (!isEmpty(form.hourly_rate) && isEmpty(form.salary_gross_monthly)) salaryType = "hourly";
    form.salary_type = salaryType;
    if (salaryType === "hourly") form.salary_gross_monthly = "";
    return form;
  }

  function fieldApplies(key, salaryType, contractType) {
    if (key === "salary_gross_monthly") return salaryType !== "hourly" && contractType !== "mini_job";
    if (key === "hourly_rate") return salaryType === "hourly";
    return true;
  }

  function validateForm(form, options = {}) {
    form = normalizeForm(form);
    const contractType = options.contractType || "employment";
    const templateRequired = Array.isArray(options.templateRequired) ? options.templateRequired : [];
    const salaryType = form.salary_type || "monthly_fixed";
    const required = [...BASE_REQUIRED];
    for (const key of templateRequired) {
      if (key && !required.includes(key)) required.push(key);
    }
    if (contractType === "fixed_term" && !required.includes("end_date")) required.push("end_date");
    if (salaryType === "hourly") {
      if (!required.includes("hourly_rate")) required.push("hourly_rate");
    } else if (contractType !== "mini_job" && !required.includes("salary_gross_monthly")) {
      required.push("salary_gross_monthly");
    }
    const missing = [];
    const missingKeys = [];
    const seen = new Set();
    for (const key of required) {
      if (seen.has(key)) continue;
      seen.add(key);
      if (!fieldApplies(key, salaryType, contractType)) continue;
      if (isEmpty(form[key])) {
        missingKeys.push(key);
        missing.push(LABELS_DE[key] || key);
      }
    }
    return { ok: missing.length === 0, missing, missingKeys, form };
  }

  function clearFieldErrors() {
    document.querySelectorAll(".field-error").forEach((el) => el.classList.remove("field-error"));
  }

  function highlightFields(missingKeys) {
    clearFieldErrors();
    for (const key of missingKeys || []) {
      const id = FIELD_IDS[key];
      const el = id ? document.getElementById(id) : null;
      if (!el) continue;
      const label = el.closest("label");
      if (label) label.classList.add("field-error");
      else el.classList.add("field-error");
    }
  }

  return { validateForm, normalizeForm, highlightFields, clearFieldErrors, FIELD_IDS };
})();
