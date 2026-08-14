/**
 * Persist healthFund/birthDate into payslip.employee on rebuild,
 * and backfill existing jobs from employee registry.
 *
 * Run inside Lohn app root (/app):
 *   node /tmp/patch-lohn-persist-stammdaten.mjs
 */
import fs from "fs";
import { createRequire } from "module";

const require = createRequire("/app/server/store.mjs");
const { getEmployee } = require("/app/server/employee-registry.mjs");
const { listPayrollJobs, loadPayrollJob, savePayrollJob } = require("/app/server/store.mjs");

const enrichPath = "/app/server/employee-enrich.mjs";
let src = fs.readFileSync(enrichPath, "utf8");

const oldBlock = `    employee: {
      id: String(state.employeeId || state.badgeId || ""),
      badgeId: String(state.badgeId || state.employeeId || ""),
      name: String(state.employeeName || ""),
      address: String(state.employeeAddress || ""),
      taxId: String(state.employeeTaxId || ""),
      insuranceNo: String(state.employeeInsuranceNo || ""),
      taxClass: String(state.taxClass || ""),
      personnelNumber: String(state.personnelNumber || ""),
      printPersNr: String(state.personnelNumber || ""),
    },`;

const newBlock = `    employee: {
      id: String(state.employeeId || state.badgeId || ""),
      badgeId: String(state.badgeId || state.employeeId || ""),
      name: String(state.employeeName || ""),
      address: String(state.employeeAddress || ""),
      taxId: String(state.employeeTaxId || ""),
      insuranceNo: String(state.employeeInsuranceNo || ""),
      taxClass: String(state.taxClass || ""),
      personnelNumber: String(state.personnelNumber || ""),
      printPersNr: String(state.personnelNumber || ""),
      birthDate: String(state.employeeBirthDate || ""),
      entryDate: String(state.employeeEntryDate || ""),
      healthFund: String(state.healthFund || ""),
      healthPercent: String(state.healthPercent || ""),
      healthAdditionalPercent: String(state.healthAdditionalPercent || ""),
    },`;

if (!src.includes(oldBlock)) {
  if (src.includes("healthFund: String(state.healthFund")) {
    console.log("rebuildJob already persists healthFund");
  } else {
    console.error("Could not find payslip.employee block in employee-enrich.mjs");
    process.exit(1);
  }
} else {
  src = src.replace(oldBlock, newBlock);
  fs.writeFileSync(enrichPath, src, "utf8");
  console.log("Patched employee-enrich.mjs rebuildJob");
}

function pick(...vals) {
  for (const v of vals) {
    const s = String(v ?? "").trim();
    if (s) return s;
  }
  return "";
}

let updated = 0;
try {
  const jobs = listPayrollJobs({}) || [];
  for (const row of jobs) {
  const job = loadPayrollJob(row.jobId) || row;
  if (!job || job.demo) continue;
  const companyId = pick(job.company?.id, String(job.jobId || "").split("::")[0]);
  const badge = pick(
    job.employee?.badgeId,
    job.employee?.id,
    job.payslip?.employee?.badgeId,
    job.payslip?.employee?.id,
  );
  if (!companyId || !badge) continue;
  const reg = getEmployee(companyId, badge);
  if (!reg) continue;
  const meta = reg.meta || {};
  const payslip = { ...(job.payslip || {}) };
  const emp = { ...(payslip.employee || {}) };
  let changed = false;
  const fill = (key, ...vals) => {
    if (pick(emp[key])) return;
    const v = pick(...vals);
    if (!v) return;
    emp[key] = v;
    changed = true;
  };
  fill("personnelNumber", reg.personnelNumber, meta.personnelNumber, emp.printPersNr);
  fill("printPersNr", reg.personnelNumber, meta.personnelNumber, emp.personnelNumber);
  fill("healthFund", meta.healthFund, meta.kk, meta.krankenkasse);
  fill("healthPercent", meta.healthPercent, meta.kkPercent);
  fill("birthDate", meta.birthDate, meta.dateOfBirth);
  fill("entryDate", meta.entryDate, meta.startDate);
  fill("taxClass", meta.taxClass);
  fill("insuranceNo", meta.insuranceNo, meta.svNr);
  fill("taxId", meta.taxId);
  fill("address", meta.address);
  if (!changed) continue;
  payslip.employee = emp;
  savePayrollJob({ ...job, payslip });
  updated += 1;
  console.log("backfilled", job.jobId, emp.healthFund || "", emp.personnelNumber || "");
  }
  console.log("STAMMDATEN_OK updated", updated);
} catch (err) {
  console.log("STAMMDATEN_OK code-patched; backfill skipped:", String(err && err.message ? err.message : err).slice(0, 160));
}
