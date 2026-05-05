const fs = require("fs");
const path = require("path");
const code = fs.readFileSync(path.join(__dirname, "../app.js"), "utf8");

const missing = [
  "accessLoadMoreButton", "checkedInLate", "confirmDeleteWorkerBulk",
  "imapTestFail", "imapTestOk", "manualEntryCheckin", "manualEntryCheckout",
  "manualEntryError", "manualEntryNoResults", "manualEntryNoteCheckin",
  "manualEntryNoteCheckout", "manualEntrySearch", "workEndTimeLabel", "workStartTimeLabel"
];

// Find UI_TRANSLATIONS en block
const uiStart = code.indexOf("const UI_TRANSLATIONS = {");
const enBlockStart = code.indexOf("'en': {", uiStart) + "'en': {".length;
let depth = 1, pos = enBlockStart;
while (depth > 0 && pos < code.length) {
  if (code[pos] === "{") depth++;
  else if (code[pos] === "}") depth--;
  pos++;
}
const enBlock = code.slice(enBlockStart, pos - 1);

// Find getRuntimeUiTexts map.de block
const fnStart = code.indexOf("function getRuntimeUiTexts()");
const mapStart = code.indexOf("const map = {", fnStart);
const deStart2 = code.indexOf("de: {", mapStart) + "de: {".length;
let depth2 = 1, pos2 = deStart2;
while (depth2 > 0 && pos2 < code.length) {
  if (code[pos2] === "{") depth2++;
  else if (code[pos2] === "}") depth2--;
  pos2++;
}
const deBlock = code.slice(deStart2, pos2 - 1);

missing.forEach((k) => {
  const rx = new RegExp(`${k}:\\s*["']([^"']+)["']`);
  const enM = rx.exec(enBlock);
  const deM = rx.exec(deBlock);
  process.stdout.write(k + ":\n");
  if (enM) process.stdout.write("  EN (UI_TRANSLATIONS): " + enM[1] + "\n");
  if (deM) process.stdout.write("  DE (map.de): " + deM[1] + "\n");
  if (!enM && !deM) process.stdout.write("  (not found!)\n");
});
