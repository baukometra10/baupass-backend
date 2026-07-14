const { test, expect } = require('@playwright/test');
const { execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');

async function login(request, { username, password, loginScope, otpCode }) {
  const response = await request.post('/api/login', {
    data: { username, password, loginScope, otpCode: otpCode || '' },
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  if (!payload?.ok) {
    throw new Error(`login_failed:${payload?.error || 'unknown'}`);
  }
  expect(payload.token).toBeTruthy();
  return payload;
}

function getWorkspacePythonExecutable() {
  if (process.env.PYTHON) {
    return process.env.PYTHON;
  }
  const candidates = process.platform === 'win32'
    ? [
        path.resolve('.venv311', 'Scripts', 'python.exe'),
        path.resolve('.venv', 'Scripts', 'python.exe'),
      ]
    : [
        path.resolve('.venv311', 'bin', 'python'),
        path.resolve('.venv', 'bin', 'python'),
      ];
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (found) return found;
  return process.platform === 'win32' ? 'python' : 'python3';
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

test.describe('Platform smoke', () => {
  const username = process.env.E2E_SUPERADMIN_USER || 'superadmin';
  const password = process.env.E2E_SUPERADMIN_PASSWORD || '1234';

  test.beforeAll(() => {
    ensureLocalSuperadminCredentials(username);
  });

  test('health, enterprise catalog, branding PDF preview', async ({ request }) => {
    const health = await request.get('/api/health/live');
    expect(health.ok()).toBeTruthy();

    const platformHealth = await request.get('/api/health/platform');
    expect(platformHealth.ok()).toBeTruthy();
    const platformPayload = await platformHealth.json();
    expect(platformPayload.status).toBe('ok');
    expect(platformPayload.ready).toBeTruthy();

    const loginPayload = await login(request, {
      username,
      password,
      loginScope: 'auto',
    });
    const headers = { Authorization: `Bearer ${loginPayload.token}` };

    const companies = await request.get('/api/companies', { headers });
    expect(companies.ok()).toBeTruthy();
    const companyRows = await companies.json();
    const firstCompany = Array.isArray(companyRows) ? companyRows.find((c) => !c.deleted_at) : null;
    expect(firstCompany?.id).toBeTruthy();

    const catalog = await request.get(
      `/api/platform/enterprise-catalog?company_id=${encodeURIComponent(firstCompany.id)}`,
      { headers },
    );
    expect(catalog.ok()).toBeTruthy();
    const cat = await catalog.json();
    expect(Array.isArray(cat.layers)).toBeTruthy();

    const pdf = await request.post(
      `/api/workforce/deployment-plan/pdf/branding-preview?company_id=${encodeURIComponent(firstCompany.id)}`,
      { headers, data: { lang: 'de' } },
    );
    expect(pdf.ok()).toBeTruthy();
    expect(pdf.headers()['content-type'] || '').toContain('application/pdf');
    const body = await pdf.body();
    expect(body.byteLength).toBeGreaterThan(500);
    expect(String.fromCharCode(...body.slice(0, 4))).toBe('%PDF');

    const fullHealth = await request.get('/api/health');
    expect(fullHealth.ok()).toBeTruthy();
    const healthPayload = await fullHealth.json();
    expect(healthPayload.architecture?.apiRouteProbe?.ok).toBeTruthy();

    const putCompany = await request.put(`/api/companies/${encodeURIComponent(firstCompany.id)}`, {
      headers,
      data: { name: firstCompany.name || 'Test' },
    });
    expect([200, 400, 422]).toContain(putCompany.status());
  });
});
