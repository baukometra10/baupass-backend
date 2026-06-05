const { test, expect } = require('@playwright/test');
const { execFileSync } = require('child_process');
const path = require('path');

function env(name, fallback) {
  const value = String(process.env[name] || '').trim();
  return value || fallback;
}

function getWorkspacePythonExecutable() {
  return process.platform === 'win32'
    ? path.resolve('.venv', 'Scripts', 'python.exe')
    : path.resolve('.venv', 'bin', 'python');
}

function ensureLocalSuperadminCredentials(username, displayName, password = '1234') {
  const pythonExecutable = getWorkspacePythonExecutable();
  const script = [
    'import sqlite3',
    'from pathlib import Path',
    'from werkzeug.security import generate_password_hash',
    `username = ${JSON.stringify(username)}`,
    `display_name = ${JSON.stringify(displayName)}`,
    `password = ${JSON.stringify(password)}`,
    "db_path = Path('backend') / 'baupass.db'",
    'conn = sqlite3.connect(db_path)',
    'password_hash = generate_password_hash(password)',
    'user = conn.execute("SELECT id FROM users WHERE lower(username) = lower(?)", (username,)).fetchone()',
    'if user:',
    '    user_id = user[0]',
    '    conn.execute("UPDATE users SET password_hash = ?, name = ?, role = ?, company_id = NULL, twofa_enabled = 0, twofa_secret = ?, email = ? WHERE id = ?", (password_hash, display_name, "superadmin", "", "", user_id))',
    'else:',
    '    user_id = f"usr-{username}"',
    '    conn.execute("INSERT INTO users (id, username, password_hash, name, role, company_id, twofa_enabled, email) VALUES (?, ?, ?, ?, ?, NULL, 0, ?)", (user_id, username, password_hash, display_name, "superadmin", ""))',
    'conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))',
    'conn.execute("DELETE FROM otp_codes WHERE user_id = ?", (user_id,))',
    'conn.commit()',
    'conn.close()',
  ].join('\n');
  execFileSync(pythonExecutable, ['-c', script], {
    cwd: process.cwd(),
    stdio: 'ignore',
  });
}

async function loginUi(page, { username, password }) {
  await page.goto('/');
  await page.fill('#loginUsername', username);
  await page.fill('#loginPassword', password);
  await page.locator('#loginForm button[type="submit"]').click();
  await expect(page.locator('#authOverlay')).toHaveAttribute('aria-hidden', 'true');
}

test('capture visual baseline for core control views', async ({ page }, testInfo) => {
  const username = env('E2E_SUPERADMIN_USERNAME', 'superadmin_visual_baseline');
  const password = env('E2E_SUPERADMIN_PASSWORD', '1234');
  ensureLocalSuperadminCredentials(username, 'E2E Visual Baseline Superadmin', password);

  await loginUi(page, { username, password });
  await page.setViewportSize({ width: 1440, height: 980 });

  const dashboardPath = testInfo.outputPath('visual-dashboard.png');
  await page.screenshot({ path: dashboardPath, fullPage: true });
  await testInfo.attach('dashboard', { path: dashboardPath, contentType: 'image/png' });

  await page.click('.nav-link[data-view="access"]');
  await expect(page.locator('.view.active[data-view="access"]')).toBeVisible();
  const accessPath = testInfo.outputPath('visual-access.png');
  await page.screenshot({ path: accessPath, fullPage: true });
  await testInfo.attach('access', { path: accessPath, contentType: 'image/png' });

  await page.click('.nav-link[data-view="invoices"]');
  await expect(page.locator('.view.active[data-view="invoices"]')).toBeVisible();
  const invoicesPath = testInfo.outputPath('visual-invoices.png');
  await page.screenshot({ path: invoicesPath, fullPage: true });
  await testInfo.attach('invoices', { path: invoicesPath, contentType: 'image/png' });
});
