// Admin overview: Lagebild panel + Inbox filter chips.
const { test, expect } = require('@playwright/test');
const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');

async function login(request, { username, password, loginScope }) {
  const response = await request.post('/api/login', {
    data: { username, password, loginScope, otpCode: '' },
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  if (!payload?.ok) throw new Error(`login_failed:${payload?.error || 'unknown'}`);
  return payload;
}

function getWorkspacePythonExecutable() {
  if (process.env.PYTHON) return process.env.PYTHON;
  const candidates = process.platform === 'win32'
    ? [
        path.resolve('.venv311', 'Scripts', 'python.exe'),
        path.resolve('.venv', 'Scripts', 'python.exe'),
      ]
    : [
        path.resolve('.venv311', 'bin', 'python'),
        path.resolve('.venv', 'bin', 'python'),
      ];
  return candidates.find((c) => fs.existsSync(c)) || (process.platform === 'win32' ? 'python' : 'python3');
}

function ensureLocalSuperadminCredentials(username) {
  const pythonExecutable = getWorkspacePythonExecutable();
  const script = [
    'import sqlite3',
    'from pathlib import Path',
    'from werkzeug.security import generate_password_hash',
    `username = ${JSON.stringify(username)}`,
    "db_path = Path('backend') / 'baupass.db'",
    'conn = sqlite3.connect(db_path)',
    'password_hash = generate_password_hash("1234")',
    'user = conn.execute("SELECT id FROM users WHERE lower(username) = lower(?)", (username,)).fetchone()',
    'if user:',
    '    user_id = user[0]',
    '    conn.execute("UPDATE users SET password_hash = ?, role = ?, company_id = NULL WHERE id = ?", (password_hash, "superadmin", user_id))',
    'else:',
    '    user_id = f"usr-{username}"',
    '    conn.execute("INSERT INTO users (id, username, password_hash, name, role, company_id) VALUES (?, ?, ?, ?, ?, NULL)", (user_id, username, password_hash, "E2E Super", "superadmin"))',
    'conn.commit()',
    'conn.close()',
  ].join('\n');
  execFileSync(pythonExecutable, ['-c', script], { cwd: process.cwd(), stdio: 'ignore' });
}

test.describe('Admin Lagebild + Inbox UI', () => {
  const username = process.env.E2E_SUPERADMIN_USER || 'superadmin';
  const password = process.env.E2E_SUPERADMIN_PASSWORD || '1234';

  test.beforeAll(() => {
    ensureLocalSuperadminCredentials(username);
  });

  test('lage panel and inbox filters render', async ({ page, request }) => {
    const loginPayload = await login(request, {
      username,
      password,
      loginScope: 'auto',
    });
    const headers = { Authorization: `Bearer ${loginPayload.token}` };
    const companies = await request.get('/api/companies', { headers });
    expect(companies.ok()).toBeTruthy();
    const companyRows = await companies.json();
    const list = Array.isArray(companyRows)
      ? companyRows
      : (companyRows.companies || []);
    const firstCompany = list.find((c) => !c.deleted_at);
    expect(firstCompany?.id).toBeTruthy();
    const cid = firstCompany.id;

    await page.addInitScript(({ token, companyId }) => {
      localStorage.setItem('workpass-admin-token', token);
      localStorage.setItem('workpass-admin-user', JSON.stringify({ role: 'superadmin' }));
      localStorage.setItem('workpass-admin-company', companyId);
      localStorage.setItem('baupass-admin-v2-lang', 'de');
    }, { token: loginPayload.token, companyId: cid });

    await page.goto(`/admin-v2/index.html?company_id=${encodeURIComponent(cid)}`, {
      waitUntil: 'domcontentloaded',
    });

    const lage = page.locator('#lagePanel');
    await expect(lage).toBeVisible({ timeout: 20000 });
    await expect(lage.locator('.lage-kpi').first()).toBeVisible();
    await expect(lage.locator('.lage-map-embed iframe')).toHaveAttribute('src', /ops-live-map\.html/);

    await page.locator('button[data-tab="inbox"]').first().click();
    await expect(page.locator('#tab-inbox')).toBeVisible({ timeout: 15000 });
    const chips = page.locator('.inbox-filter-chip');
    await expect(chips.first()).toBeVisible({ timeout: 15000 });
    const chipCount = await chips.count();
    expect(chipCount).toBeGreaterThan(1);

    const leaveChip = page.locator('.inbox-filter-chip[data-source="leave"]');
    if (await leaveChip.count()) {
      await leaveChip.click();
      await expect(leaveChip).toHaveClass(/active/);
    }
  });
});
