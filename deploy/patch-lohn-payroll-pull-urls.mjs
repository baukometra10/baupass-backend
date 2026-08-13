/**
 * Patch WorkPass Lohn server/month-close.mjs resolvePlatformPullUrls().
 *
 * Why: Lohn auto-pull used /api/contracts as a fallback. That overwrote real
 * payroll batches (wageItems + company.name) with empty contract rows and
 * marked jobs as "Firma fehlt" / "Lohnarten/Brutto fehlen".
 *
 * Prefer:
 *   GET /api/v2/accounting/payroll-batch
 *   GET /api/v2/accounting/hours
 *
 * Run on the Lohn service (cwd must contain server/month-close.mjs), e.g.:
 *   Get-Content deploy/patch-lohn-payroll-pull-urls.mjs -Raw |
 *     railway ssh -s workpass-Lohn -- "cat > /tmp/patch.mjs && node /tmp/patch.mjs"
 *
 * Or:  .\deploy\patch-lohn-payroll-pull-urls.ps1
 */
import fs from "fs";

const p = "server/month-close.mjs";
const marker = "NEVER /api/contracts";

if (!fs.existsSync(p)) {
  console.error("PATCH_FAIL missing", p);
  process.exit(1);
}

let s = fs.readFileSync(p, "utf8");
if (s.includes(marker)) {
  console.log("ALREADY_PATCHED");
  process.exit(0);
}

const fnStart = s.indexOf("export function resolvePlatformPullUrls");
if (fnStart < 0) {
  console.error("PATCH_FAIL resolvePlatformPullUrls not found");
  process.exit(1);
}

const blockStart = s.indexOf("if (hostBase) {", fnStart);
if (blockStart < 0) {
  console.error("PATCH_FAIL hostBase block not found");
  process.exit(1);
}

let i = blockStart + "if (hostBase) {".length;
let depth = 1;
while (i < s.length && depth > 0) {
  if (s[i] === "{") depth += 1;
  else if (s[i] === "}") depth -= 1;
  i += 1;
}
const blockEnd = i;

const replacement = `if (hostBase) {
    // Prefer real payroll batch/hours APIs — NEVER /api/contracts (overwrites with empty wageItems)
    add(\`\${hostBase}/api/v2/accounting/payroll-batch\`);
    add(\`\${hostBase}/api/v2/accounting/hours\`);
    add(\`\${hostBase}/api/workpass/payroll/export\`);
    add(\`\${hostBase}/api/workpass/accounting/payroll/export\`);
  }
`;

const out = s.slice(0, blockStart) + replacement.trimStart() + s.slice(blockEnd);
fs.writeFileSync(p, out);
console.log("PATCH_OK");
