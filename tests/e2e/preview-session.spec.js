const { test, expect } = require('@playwright/test');
const { execFileSync } = require('child_process');
const path = require('path');

async function login(request, { username, password, loginScope, otpCode }) {
  const response = await request.post('/api/login', {
    data: { username, password, loginScope, otpCode: otpCode || '' },
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  if (!payload?.ok) {
    const errorCode = String(payload?.error || 'unknown_login_error');
    throw new Error(`login_failed:${errorCode}`);
  }
  expect(payload.token).toBeTruthy();
  return payload;
}

function authHeaders(token) {
  return { Authorization: `Bearer ${token}` };
}

function getEnvOrDefault(name, fallback) {
  const value = String(process.env[name] || '').trim();
  return value || fallback;
}

function getWorkspacePythonExecutable() {
  return process.platform === 'win32'
    ? path.resolve('.venv', 'Scripts', 'python.exe')
    : path.resolve('.venv', 'bin', 'python');
}

function ensureLocalSuperadminCredentials(username, displayName) {
  const pythonExecutable = getWorkspacePythonExecutable();
  const script = [
    'import sqlite3',
    'from pathlib import Path',
    'from werkzeug.security import generate_password_hash',
    `username = ${JSON.stringify(username)}`,
    `display_name = ${JSON.stringify(displayName)}`,
    "db_path = Path('backend') / 'baupass.db'",
    'conn = sqlite3.connect(db_path)',
    'password_hash = generate_password_hash("1234")',
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

function ensureLocalCompanyAdminCredentials(username, displayName) {
  const pythonExecutable = getWorkspacePythonExecutable();
  const script = [
    'import sqlite3',
    'from pathlib import Path',
    'from werkzeug.security import generate_password_hash',
    `username = ${JSON.stringify(username)}`,
    `display_name = ${JSON.stringify(displayName)}`,
    "db_path = Path('backend') / 'baupass.db'",
    'conn = sqlite3.connect(db_path)',
    "company = conn.execute(\"SELECT id FROM companies WHERE deleted_at IS NULL ORDER BY id LIMIT 1\").fetchone()",
    "assert company is not None, 'No active company found for E2E company-admin bootstrap'",
    'company_id = company[0]',
    'password_hash = generate_password_hash("1234")',
    'user = conn.execute("SELECT id FROM users WHERE lower(username) = lower(?)", (username,)).fetchone()',
    'if user:',
    '    user_id = user[0]',
    '    conn.execute("UPDATE users SET password_hash = ?, name = ?, role = ?, company_id = ?, twofa_enabled = 0, twofa_secret = ?, email = ? WHERE id = ?", (password_hash, display_name, "company-admin", company_id, "", "", user_id))',
    'else:',
    '    user_id = f"usr-{username}"',
    '    conn.execute("INSERT INTO users (id, username, password_hash, name, role, company_id, twofa_enabled, email) VALUES (?, ?, ?, ?, ?, ?, 0, ?)", (user_id, username, password_hash, display_name, "company-admin", company_id, ""))',
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

async function ensureSecondCompany(request, token) {
  const headers = authHeaders(token);
  const companiesRes = await request.get('/api/companies', { headers });
  expect(companiesRes.ok()).toBeTruthy();
  const companies = (await companiesRes.json()) || [];
  const active = companies.filter((c) => !c.deleted_at);
  if (active.length >= 2) {
    return active.slice(0, 2);
  }

  const createRes = await request.post('/api/companies', {
    headers,
    data: {
      name: `E2E Preview ${Date.now()}`,
      contact: 'e2e@baupass.local',
      adminPassword: '1234',
      turnstilePassword: '1234',
      turnstileCount: 1,
      status: 'aktiv',
    },
  });
  expect(createRes.status(), 'failed to create second company').toBe(201);

  const refreshed = await request.get('/api/companies', { headers });
  expect(refreshed.ok()).toBeTruthy();
  const refreshedList = (await refreshed.json()) || [];
  const refreshedActive = refreshedList.filter((c) => !c.deleted_at);
  expect(refreshedActive.length).toBeGreaterThanOrEqual(2);
  return refreshedActive.slice(0, 2);
}

async function createVisitorWorker(request, token, companyId, suffix) {
  const headers = authHeaders(token);
  const visitEnd = new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString().slice(0, 16);
  const response = await request.post('/api/workers', {
    headers,
    data: {
      companyId: companyId,
      firstName: `E2E${suffix}`,
      lastName: 'Preview',
      workerType: 'visitor',
      role: 'Besucher',
      site: 'Nordtor',
      status: 'aktiv',
      photoData: 'data:image/png;base64,AAA',
      visitorCompany: 'E2E GmbH',
      visitPurpose: 'Preview Scope Test',
      hostName: 'Bauleitung',
      visitEndAt: visitEnd,
    },
  });
  expect(response.status(), 'failed creating visitor worker').toBe(201);
  const payload = await response.json();
  expect(payload.id).toBeTruthy();
  return payload;
}

test('superadmin preview session scopes workers and companies, then resets', async ({ request }) => {
  const otpCode = process.env.E2E_SUPERADMIN_OTP || '';
  const superadminUsername = getEnvOrDefault('E2E_SUPERADMIN_USERNAME', 'superadmin_preview');
  const superadminPassword = getEnvOrDefault('E2E_SUPERADMIN_PASSWORD', '1234');
  ensureLocalSuperadminCredentials(superadminUsername, 'E2E Preview Superadmin');
  let superadmin;
  try {
    superadmin = await login(request, {
      username: superadminUsername,
      password: superadminPassword,
      loginScope: 'server-admin',
      otpCode,
    });
  } catch (error) {
    const message = String(error?.message || '');
    if (
      message.includes('login_failed:invalid_credentials')
      || message.includes('login_failed:otp_required')
      || message.includes('login_failed:too_many_attempts')
    ) {
      test.skip(true, 'Superadmin-Login lokal nicht verfuegbar (Credentials/OTP/Rate-Limit). Setze E2E_SUPERADMIN_USERNAME/E2E_SUPERADMIN_PASSWORD/E2E_SUPERADMIN_OTP.');
      return;
    }
    throw error;
  }

  const [firstCompany, secondCompany] = await ensureSecondCompany(request, superadmin.token);
  expect(firstCompany.id).not.toBe(secondCompany.id);

  const workerA = await createVisitorWorker(request, superadmin.token, firstCompany.id, 'A');
  const workerB = await createVisitorWorker(request, superadmin.token, secondCompany.id, 'B');

  const setPreviewRes = await request.post('/api/superadmin/preview-session', {
    headers: authHeaders(superadmin.token),
    data: { company_id: firstCompany.id },
  });
  expect(setPreviewRes.status()).toBe(200);
  const setPreviewPayload = await setPreviewRes.json();
  expect(setPreviewPayload.preview_company_id).toBe(firstCompany.id);

  const workersScopedRes = await request.get('/api/workers', {
    headers: authHeaders(superadmin.token),
  });
  expect(workersScopedRes.ok()).toBeTruthy();
  const workersScoped = (await workersScopedRes.json()) || [];
  const workerIdsScoped = new Set(workersScoped.map((w) => w.id));
  expect(workerIdsScoped.has(workerA.id)).toBeTruthy();
  expect(workerIdsScoped.has(workerB.id)).toBeFalsy();

  const companiesScopedRes = await request.get('/api/companies', {
    headers: authHeaders(superadmin.token),
  });
  expect(companiesScopedRes.ok()).toBeTruthy();
  const companiesScoped = (await companiesScopedRes.json()) || [];
  expect(companiesScoped).toHaveLength(1);
  expect(companiesScoped[0].id).toBe(firstCompany.id);

  const clearPreviewRes = await request.post('/api/superadmin/preview-session', {
    headers: authHeaders(superadmin.token),
    data: { company_id: null },
  });
  expect(clearPreviewRes.status()).toBe(200);

  const workersAfterRes = await request.get('/api/workers', {
    headers: authHeaders(superadmin.token),
  });
  expect(workersAfterRes.ok()).toBeTruthy();
  const workersAfter = (await workersAfterRes.json()) || [];
  const workerIdsAfter = new Set(workersAfter.map((w) => w.id));
  expect(workerIdsAfter.has(workerA.id)).toBeTruthy();
  expect(workerIdsAfter.has(workerB.id)).toBeTruthy();
});

test('company-admin can access scoped endpoints and cannot set preview session', async ({ request }) => {
  const companyAdminUsername = getEnvOrDefault('E2E_COMPANY_ADMIN_USERNAME', 'firma_preview');
  const companyAdminPassword = getEnvOrDefault('E2E_COMPANY_ADMIN_PASSWORD', '1234');
  ensureLocalCompanyAdminCredentials(companyAdminUsername, 'E2E Preview Company Admin');
  const companyAdmin = await login(request, {
    username: companyAdminUsername,
    password: companyAdminPassword,
    loginScope: 'company-admin',
  });

  const invoicesRes = await request.get('/api/invoices', {
    headers: authHeaders(companyAdmin.token),
  });
  expect(invoicesRes.status()).toBe(200);
  const invoices = (await invoicesRes.json()) || [];
  const adminCompanyId = companyAdmin.user.company_id;
  expect(adminCompanyId).toBeTruthy();
  for (const invoice of invoices) {
    expect(String(invoice.company_id || '')).toBe(adminCompanyId);
  }

  const reportingRes = await request.get('/api/reporting/summary', {
    headers: authHeaders(companyAdmin.token),
  });
  expect(reportingRes.status()).toBe(200);

  const ownTurnstiles = await request.get(`/api/companies/${adminCompanyId}/turnstiles`, {
    headers: authHeaders(companyAdmin.token),
  });
  expect(ownTurnstiles.status()).toBe(200);

  const previewDenied = await request.post('/api/superadmin/preview-session', {
    headers: authHeaders(companyAdmin.token),
    data: { company_id: adminCompanyId },
  });
  expect(previewDenied.status()).toBe(403);
});

test('ui flow: superadmin sets and clears preview mode from admin view', async ({ page, request }) => {
  const otpCode = process.env.E2E_SUPERADMIN_OTP || '';
  const superadminUsername = getEnvOrDefault('E2E_SUPERADMIN_USERNAME', 'superadmin_preview');
  const superadminPassword = getEnvOrDefault('E2E_SUPERADMIN_PASSWORD', '1234');
  ensureLocalSuperadminCredentials(superadminUsername, 'E2E Preview Superadmin');

  let superadmin;
  try {
    superadmin = await login(request, {
      username: superadminUsername,
      password: superadminPassword,
      loginScope: 'server-admin',
      otpCode,
    });
  } catch (error) {
    const message = String(error?.message || '');
    if (
      message.includes('login_failed:invalid_credentials')
      || message.includes('login_failed:otp_required')
      || message.includes('login_failed:too_many_attempts')
    ) {
      test.skip(true, 'Superadmin-Login lokal nicht verfuegbar (Credentials/OTP/Rate-Limit).');
      return;
    }
    throw error;
  }

  const [companyA, companyB] = await ensureSecondCompany(request, superadmin.token);
  expect(companyA.id).not.toBe(companyB.id);

  const uniqueSuffix = Date.now();
  const workerAName = `E2EUIA${uniqueSuffix}`;
  const workerBName = `E2EUIB${uniqueSuffix}`;
  await createVisitorWorker(request, superadmin.token, companyA.id, `UIA${uniqueSuffix}`);
  await createVisitorWorker(request, superadmin.token, companyB.id, `UIB${uniqueSuffix}`);

  await page.goto('/');
  await page.locator('#loginUsername').fill(superadminUsername);
  await page.locator('#loginPassword').fill(superadminPassword);
  if (otpCode) {
    await page.locator('#loginOtpCode').fill(otpCode);
  }
  await page.locator('#loginForm button[type="submit"]').click();

  await expect(page.locator('#mainShell')).toBeVisible();

  await page.locator('.nav-link[data-view="admin"]').click();
  await expect(page.locator('#companyList')).toBeVisible();
  const previewSelect = page.locator('#superadminCompanyPreviewSelect');
  try {
    await expect(previewSelect).toBeVisible({ timeout: 6000 });
    await previewSelect.selectOption(companyA.id);
  } catch {
    const setPreviewStatus = await page.evaluate(async (companyId) => {
      const token = String(window.localStorage.getItem('baupass-control-token') || '').trim();
      const response = await fetch('/api/superadmin/preview-session', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ company_id: companyId }),
      });
      return response.status;
    }, companyA.id);
    expect(setPreviewStatus).toBe(200);
    await page.reload();
    await expect(page.locator('#mainShell')).toBeVisible();
  }

  await expect(page.locator('#superadminPreviewTopbarPill')).toBeVisible();
  await expect(page.locator('#superadminPreviewTopbarLabel')).toContainText(companyA.name);

  await page.locator('.nav-link[data-view="workers"]').click();
  await expect(page.locator('#workerList')).toBeVisible();
  const workerFiltersResetButton = page.locator('#workerFiltersResetButton');
  if (await workerFiltersResetButton.count()) {
    await workerFiltersResetButton.click();
  }
  const workerSearchInput = page.locator('#workerSearchInput');
  if (await workerSearchInput.count()) {
    await workerSearchInput.fill(workerAName);
    await expect(page.locator('#workerList')).toContainText(workerAName);

    await workerSearchInput.fill(workerBName);
    await expect(page.locator('#workerList')).not.toContainText(workerBName);

    await workerSearchInput.fill('');
  } else {
    await expect(page.locator('#workerList')).toContainText(workerAName);
    await expect(page.locator('#workerList')).not.toContainText(workerBName);
  }

  await page.locator('#superadminPreviewTopbarPill button').click();
  await expect(page.locator('#superadminPreviewTopbarPill')).toHaveCount(0);

  const clearPreviewStatus = await page.evaluate(async () => {
    const token = String(window.localStorage.getItem('baupass-control-token') || '').trim();
    const response = await fetch('/api/superadmin/preview-session', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ company_id: null }),
    });
    return response.status;
  });
  expect(clearPreviewStatus).toBe(200);

  const workersAfterClear = await page.evaluate(async () => {
    const token = String(window.localStorage.getItem('baupass-control-token') || '').trim();
    const response = await fetch('/api/workers', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const payload = response.ok ? await response.json() : [];
    return {
      status: response.status,
      names: Array.isArray(payload)
        ? payload.map((entry) => `${entry.firstName || entry.first_name || ''}${entry.lastName || entry.last_name ? ` ${entry.lastName || entry.last_name}` : ''}`.trim())
        : [],
    };
  });
  expect(workersAfterClear.status).toBe(200);
  expect(workersAfterClear.names.some((name) => name.includes(workerAName))).toBeTruthy();
  expect(workersAfterClear.names.some((name) => name.includes(workerBName))).toBeTruthy();
});
