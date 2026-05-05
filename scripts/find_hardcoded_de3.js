const fs = require('fs');
const src = fs.readFileSync('app.js', 'utf8');
const lines = src.split('\n');
const re = /[äöüßÄÖÜ]/;
// Check lines 6000-8500 (where render functions may be, but past the i18n definition block ~line 4000-7900)
lines.forEach((line, i) => {
  const ln = i + 1;
  if (ln < 6000 || ln > 8500) return;
  const trimmed = line.trim();
  if (/^[a-zA-Z_]+\s*:/.test(trimmed)) return;
  if (trimmed.startsWith('//')) return;
  if (trimmed.startsWith('*')) return;
  if (!re.test(line)) return;
  console.log(ln + ': ' + trimmed.substring(0, 130));
});
