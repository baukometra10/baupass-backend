const fs = require('fs');
const src = fs.readFileSync('app.js', 'utf8');
const lines = src.split('\n');
const re = /[äöüßÄÖÜ]/;
lines.forEach((line, i) => {
  const ln = i + 1;
  if (ln < 8500) return;
  const trimmed = line.trim();
  if (/^[a-zA-Z_]+\s*:/.test(trimmed)) return; // i18n key definition
  if (trimmed.startsWith('//')) return;          // comment
  if (trimmed.startsWith('*')) return;           // jsdoc
  if (!re.test(line)) return;
  // Skip lines already using runtimeText or uiT for the German part
  if (/runtimeText\(/.test(line) && !/[äöüßÄÖÜ].*runtimeText|runtimeText.*[äöüßÄÖÜ]/.test(line)) return;
  console.log(ln + ': ' + trimmed.substring(0, 130));
});
