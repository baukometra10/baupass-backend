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

function env(name, fallback) {
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

async function loginSuperadminOrSkip(request) {
  const username = env('E2E_SUPERADMIN_USERNAME', 'superadmin_access_runtime');
  ensureLocalSuperadminCredentials(username, 'E2E Access Runtime Superadmin');
  try {
    return await login(request, {
      username,
      password: env('E2E_SUPERADMIN_PASSWORD', '1234'),
      loginScope: 'server-admin',
      otpCode: env('E2E_SUPERADMIN_OTP', ''),
    });
  } catch (error) {
    const message = String(error?.message || '');
    if (
      message.includes('login_failed:invalid_credentials')
      || message.includes('login_failed:invalid_otp')
      || message.includes('login_failed:otp_required')
      || message.includes('login_failed:too_many_attempts')
      || message.includes('login_failed:rate_limited')
    ) {
      test.skip(true, 'Superadmin-Login lokal nicht verfuegbar fuer Rechnungs-UI-Tests.');
      return null;
    }
    throw error;
  }
}

async function createVisitorWorker(request, token, companyId, suffix) {
  const headers = authHeaders(token);
  const visitEnd = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().slice(0, 16);
  const response = await request.post('/api/workers', {
    headers,
    data: {
      companyId,
      firstName: `E2E${suffix}`,
      lastName: 'Access',
      workerType: 'visitor',
      role: 'Besucher',
      site: 'Nordtor',
      status: 'aktiv',
      photoData: 'data:image/png;base64,AAA',
      visitorCompany: 'E2E Runtime GmbH',
      visitPurpose: 'API Runtime Test',
      hostName: 'Bauleitung',
      visitEndAt: visitEnd,
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

async function createAccessLog(request, token, workerId, direction, timestamp, note) {
  const response = await request.post('/api/access-logs', {
    headers: authHeaders(token),
    data: {
      workerId,
      direction,
      gate: 'E2E Gate',
      note,
      timestamp,
    },
  });
  expect(response.status()).toBe(201);
  return response.json();
}

test('latest access snapshot and invoice access line items reflect full scoped access history', async ({ request }) => {
  ensureLocalCompanyAdminCredentials('firma_access_runtime', 'E2E Access Runtime Admin');
  const companyAdmin = await login(request, {
    username: env('E2E_COMPANY_ADMIN_USERNAME', 'firma_access_runtime'),
    password: env('E2E_COMPANY_ADMIN_PASSWORD', '1234'),
    loginScope: 'company-admin',
  });

  const companyId = String(companyAdmin.user?.company_id || '');
  expect(companyId).toBeTruthy();

  const uniqueSuffix = Date.now();
  const workerA = await createVisitorWorker(request, companyAdmin.token, companyId, `A${uniqueSuffix}`);
  const workerB = await createVisitorWorker(request, companyAdmin.token, companyId, `B${uniqueSuffix}`);

  await createAccessLog(request, companyAdmin.token, workerA.id, 'check-in', '2026-04-10T07:00:00Z', 'E2E A in');
  await createAccessLog(request, companyAdmin.token, workerA.id, 'check-out', '2026-04-10T17:00:00Z', 'E2E A out');
  await createAccessLog(request, companyAdmin.token, workerB.id, 'check-in', '2026-04-11T08:00:00Z', 'E2E B in');

  const latestResponse = await request.get('/api/access-logs/latest', {
    headers: authHeaders(companyAdmin.token),
  });
  expect(latestResponse.status()).toBe(200);
  const latestPayload = await latestResponse.json();
  const latestItems = Array.isArray(latestPayload?.items) ? latestPayload.items : [];

  const latestA = latestItems.find((entry) => String(entry.worker_id || entry.workerId || '') === String(workerA.id));
  const latestB = latestItems.find((entry) => String(entry.worker_id || entry.workerId || '') === String(workerB.id));
  expect(latestA).toBeTruthy();
  expect(latestB).toBeTruthy();
  expect(String(latestA.direction || '')).toBe('check-out');
  expect(String(latestA.note || '')).toContain('E2E A out');
  expect(String(latestB.direction || '')).toBe('check-in');

  const lineItemsResponse = await request.get(`/api/invoices/access-line-items?companyId=${encodeURIComponent(companyId)}&invoicePeriod=${encodeURIComponent('2026-04-01 - 2026-04-30')}`, {
    headers: authHeaders(companyAdmin.token),
  });
  expect(lineItemsResponse.status()).toBe(200);
  const lineItemsPayload = await lineItemsResponse.json();
  const items = Array.isArray(lineItemsPayload?.items) ? lineItemsPayload.items : [];

  const itemA = items.find((entry) => String(entry.workerId || '') === String(workerA.id));
  const itemB = items.find((entry) => String(entry.workerId || '') === String(workerB.id));
  expect(itemA).toBeTruthy();
  expect(itemB).toBeTruthy();
  expect(Number(itemA.accessCount || 0)).toBe(2);
  expect(Number(itemA.amount || 0)).toBe(4);
  expect(Number(itemB.accessCount || 0)).toBe(1);
  expect(Number(itemB.amount || 0)).toBe(2);
});

test('ui access log load-more appends additional entries', async ({ page, request }) => {
  ensureLocalCompanyAdminCredentials('firma_access_runtime', 'E2E Access Runtime Admin');
  const companyAdminUsername = env('E2E_COMPANY_ADMIN_USERNAME', 'firma_access_runtime');
  const companyAdminPassword = env('E2E_COMPANY_ADMIN_PASSWORD', '1234');
  const companyAdmin = await login(request, {
    username: companyAdminUsername,
    password: companyAdminPassword,
    loginScope: 'company-admin',
  });

  const companyId = String(companyAdmin.user?.company_id || '');
  expect(companyId).toBeTruthy();

  const worker = await createVisitorWorker(request, companyAdmin.token, companyId, `LM${Date.now()}`);
  for (let index = 0; index < 405; index += 1) {
    const timestamp = new Date(Date.UTC(2026, 3, 1, 6, index, 0)).toISOString();
    const direction = index % 2 === 0 ? 'check-in' : 'check-out';
    await createAccessLog(request, companyAdmin.token, worker.id, direction, timestamp, `LoadMore ${index}`);
  }

  await page.goto('/');
  await page.locator('#loginUsername').fill(companyAdminUsername);
  await page.locator('#loginPassword').fill(companyAdminPassword);
  await page.locator('#loginScope').selectOption('company-admin');
  await page.locator('#loginForm button[type="submit"]').click();

  await expect(page.locator('#mainShell')).toBeVisible();
  await page.locator('.nav-link[data-view="access"]').click();
  await expect(page.locator('#accessLogList')).toBeVisible();
  await expect(page.locator('[data-access-load-more]')).toBeVisible();

  const entryLocator = page.locator('#accessLogList article[data-worker-id]');
  const countBefore = await entryLocator.count();
  expect(countBefore).toBe(400);

  await page.locator('[data-access-load-more]').click();
  await page.waitForFunction(
    (before) => document.querySelectorAll('#accessLogList article[data-worker-id]').length > before,
    countBefore
  );

  const countAfter = await entryLocator.count();
  expect(countAfter).toBeGreaterThan(countBefore);
});

test('ui worker detail access actions keep dashboard and access context', async ({ page, request }) => {
  ensureLocalCompanyAdminCredentials('firma_access_runtime', 'E2E Access Runtime Admin');
  const companyAdminUsername = env('E2E_COMPANY_ADMIN_USERNAME', 'firma_access_runtime');
  const companyAdminPassword = env('E2E_COMPANY_ADMIN_PASSWORD', '1234');
  const companyAdmin = await login(request, {
    username: companyAdminUsername,
    password: companyAdminPassword,
    loginScope: 'company-admin',
  });

  const companyId = String(companyAdmin.user?.company_id || '');
  expect(companyId).toBeTruthy();

  const worker = await createVisitorWorker(request, companyAdmin.token, companyId, `CTX${Date.now()}`);
  await createAccessLog(request, companyAdmin.token, worker.id, 'check-in', '2099-12-31T23:59:00Z', 'Context Dashboard In');

  await page.goto('/');
  await page.locator('#loginUsername').fill(companyAdminUsername);
  await page.locator('#loginPassword').fill(companyAdminPassword);
  await page.locator('#loginScope').selectOption('company-admin');
  await page.locator('#loginForm button[type="submit"]').click();

  await expect(page.locator('#mainShell')).toBeVisible();
  await expect(page.locator('.nav-link[data-view="dashboard"]')).toHaveClass(/active/);

  const dashboardBookingResponse = page.waitForResponse((response) => response.url().endsWith('/api/access-logs') && response.request().method() === 'POST' && response.status() === 201);
  await page.evaluate(async (workerId) => window.triggerWorkerAccess({ id: workerId }, 'check-out', { sourceView: 'dashboard' }), worker.id);
  await dashboardBookingResponse;
  await expect(page.locator('.nav-link[data-view="dashboard"]')).toHaveClass(/active/);

  await page.locator('.nav-link[data-view="access"]').click();
  await expect(page.locator('.nav-link[data-view="access"]')).toHaveClass(/active/);
  const accessWorkerEntry = page.locator(`#accessLogList article[data-worker-id="${worker.id}"]`).first();
  await expect(accessWorkerEntry).toBeVisible();
  await accessWorkerEntry.click();
  await page.waitForFunction(() => !document.querySelector('#dashboardDetailOverlay')?.classList.contains('hidden'));

  const dashboardOverlay = page.locator('#dashboardWorkerDetail');

  await expect(dashboardOverlay).toBeVisible();
  await expect(dashboardOverlay.locator('[data-direction="check-in"]')).toBeVisible();
  await expect(dashboardOverlay.locator('[data-direction="check-out"]')).toBeVisible();

  const accessBookingResponse = page.waitForResponse((response) => response.url().endsWith('/api/access-logs') && response.request().method() === 'POST' && response.status() === 201);
  await dashboardOverlay.locator('[data-direction="check-in"]').click();
  await accessBookingResponse;
  await expect(page.locator('.nav-link[data-view="access"]')).toHaveClass(/active/);
  await expect(dashboardOverlay).toBeVisible();
});

test('ui invoice preview renders server-side access line items', async ({ page, request }) => {
  const companyAdminUsername = env('E2E_COMPANY_ADMIN_USERNAME', 'firma');
  const companyAdminPassword = env('E2E_COMPANY_ADMIN_PASSWORD', '1234');
  const companyAdmin = await login(request, {
    username: companyAdminUsername,
    password: companyAdminPassword,
    loginScope: 'company-admin',
  });

  const companyId = String(companyAdmin.user?.company_id || '');
  expect(companyId).toBeTruthy();

  const superadmin = await loginSuperadminOrSkip(request);
  if (!superadmin) {
    return;
  }
  const superadminUsername = env('E2E_SUPERADMIN_USERNAME', 'superadmin_access_runtime');
  const superadminPassword = env('E2E_SUPERADMIN_PASSWORD', '1234');
  const superadminOtp = env('E2E_SUPERADMIN_OTP', '');

  const worker = await createVisitorWorker(request, companyAdmin.token, companyId, `INV${Date.now()}`);
  const workerName = `${worker.firstName || ''} ${worker.lastName || ''}`.trim();
  await createAccessLog(request, companyAdmin.token, worker.id, 'check-in', '2026-04-12T07:00:00Z', 'Invoice Preview In');
  await createAccessLog(request, companyAdmin.token, worker.id, 'check-out', '2026-04-12T17:00:00Z', 'Invoice Preview Out');

  await page.goto('/');
  await page.locator('#loginUsername').fill(superadminUsername);
  await page.locator('#loginPassword').fill(superadminPassword);
  await page.locator('#loginScope').selectOption('server-admin');
  if (superadminOtp) {
    await page.locator('#loginOtpCode').fill(superadminOtp);
  }
  await page.locator('#loginForm button[type="submit"]').click();

  await expect(page.locator('#mainShell')).toBeVisible();
  await page.locator('.nav-link[data-view="admin"]').dispatchEvent('click');
  await page.waitForFunction(() => document.querySelector('.view[data-view="admin"]')?.classList.contains('active'));

  await expect(page.locator('#invoiceCompanySelect')).toBeVisible();
  await page.locator('#invoiceCompanySelect').selectOption(companyId);
  await page.locator('#invoiceRecipientEmail').fill('preview-e2e@example.com');
  await page.locator('#invoiceDate').fill('2026-04-30');
  await page.locator('#invoiceDueDate').fill('2026-05-14');
  await page.locator('#invoicePeriod').fill('2026-04-01 - 2026-04-30');
  await page.locator('#invoiceDescription').fill('E2E Preview Access Items');
  await page.locator('#invoiceNetAmount').fill('0');
  await page.locator('#invoiceVatRate').fill('19');

  await page.locator('#invoicePreviewButton').click();

  const previewFrame = page.frameLocator('#invoicePreviewFrame');
  await expect(previewFrame.locator('body')).toContainText(workerName);
  await expect(previewFrame.locator('body')).toContainText('2');
});

test('ui invoice send shows smtp-not-configured fallback alert', async ({ page, request }) => {
  const superadmin = await loginSuperadminOrSkip(request);
  if (!superadmin) {
    return;
  }

  const companyResponse = await request.get('/api/companies', {
    headers: authHeaders(superadmin.token),
  });
  expect(companyResponse.status()).toBe(200);
  const companies = await companyResponse.json();
  const company = Array.isArray(companies) ? companies.find((entry) => !entry.deleted_at) : null;
  expect(company).toBeTruthy();

  const worker = await createVisitorWorker(request, superadmin.token, company.id, `SEND${Date.now()}`);
  await createAccessLog(request, superadmin.token, worker.id, 'check-in', '2026-04-13T07:00:00Z', 'Invoice Send In');
  await createAccessLog(request, superadmin.token, worker.id, 'check-out', '2026-04-13T17:00:00Z', 'Invoice Send Out');

  const superadminUsername = env('E2E_SUPERADMIN_USERNAME', 'superadmin_access_runtime');
  const superadminPassword = env('E2E_SUPERADMIN_PASSWORD', '1234');
  const superadminOtp = env('E2E_SUPERADMIN_OTP', '');

  await page.goto('/');
  await page.locator('#loginUsername').fill(superadminUsername);
  await page.locator('#loginPassword').fill(superadminPassword);
  await page.locator('#loginScope').selectOption('server-admin');
  if (superadminOtp) {
    await page.locator('#loginOtpCode').fill(superadminOtp);
  }
  await page.locator('#loginForm button[type="submit"]').click();

  await expect(page.locator('#mainShell')).toBeVisible();
  await page.locator('.nav-link[data-view="admin"]').click();
  await expect(page.locator('#invoiceCompanySelect')).toBeVisible();

  await page.route('**/api/invoices/send', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        sent: false,
        error: 'SMTP ist nicht konfiguriert',
        invoice: { id: 'inv-e2e-fallback' },
      }),
    });
  });

  await page.locator('#invoiceCompanySelect').selectOption(String(company.id));
  await page.locator('#invoiceRecipientEmail').fill('smtp-fallback-e2e@example.com');
  await page.locator('#invoiceDate').fill('2026-04-30');
  await page.locator('#invoiceDueDate').fill('2026-05-14');
  await page.locator('#invoicePeriod').fill('2026-04-01 - 2026-04-30');
  await page.locator('#invoiceDescription').fill('E2E Send SMTP Fallback');
  await page.locator('#invoiceOperatorStreet').fill('Musterstrasse 12');
  await page.locator('#invoiceOperatorZipCity').fill('12345 Berlin');
  await page.locator('#invoiceOperatorEmail').fill('rechnung@example.com');
  await page.locator('#invoiceIban').fill('DE89370400440532013000');
  await page.locator('#invoiceBankName').fill('Musterbank');
  await page.locator('#invoiceTaxId').fill('123/456/78901');
  await page.locator('#invoiceVatId').fill('DE123456789');
  await page.locator('#invoiceNetAmount').fill('0');
  await page.locator('#invoiceVatRate').fill('19');

  const dialogPromise = page.waitForEvent('dialog');
  await page.locator('#invoiceSendButton').click();
  const dialog = await dialogPromise;
  expect(dialog.message()).toContain('Rechnung wurde gespeichert');
  expect(dialog.message()).toContain('SMTP');
  await dialog.accept();
});

test('ui invoice send shows success alert when send succeeds', async ({ page, request }) => {
  const superadmin = await loginSuperadminOrSkip(request);
  if (!superadmin) {
    return;
  }

  const companyResponse = await request.get('/api/companies', {
    headers: authHeaders(superadmin.token),
  });
  expect(companyResponse.status()).toBe(200);
  const companies = await companyResponse.json();
  const company = Array.isArray(companies) ? companies.find((entry) => !entry.deleted_at) : null;
  expect(company).toBeTruthy();

  const worker = await createVisitorWorker(request, superadmin.token, company.id, `SENDOK${Date.now()}`);
  await createAccessLog(request, superadmin.token, worker.id, 'check-in', '2026-04-14T07:00:00Z', 'Invoice Send Success In');
  await createAccessLog(request, superadmin.token, worker.id, 'check-out', '2026-04-14T17:00:00Z', 'Invoice Send Success Out');

  const superadminUsername = env('E2E_SUPERADMIN_USERNAME', 'superadmin_access_runtime');
  const superadminPassword = env('E2E_SUPERADMIN_PASSWORD', '1234');
  const superadminOtp = env('E2E_SUPERADMIN_OTP', '');

  await page.goto('/');
  await page.locator('#loginUsername').fill(superadminUsername);
  await page.locator('#loginPassword').fill(superadminPassword);
  await page.locator('#loginScope').selectOption('server-admin');
  if (superadminOtp) {
    await page.locator('#loginOtpCode').fill(superadminOtp);
  }
  await page.locator('#loginForm button[type="submit"]').click();

  await expect(page.locator('#mainShell')).toBeVisible();
  await page.locator('.nav-link[data-view="admin"]').click();
  await expect(page.locator('#invoiceCompanySelect')).toBeVisible();

  await page.route('**/api/invoices/send', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        sent: true,
        error: '',
        invoice: { id: 'inv-e2e-success' },
      }),
    });
  });

  await page.locator('#invoiceCompanySelect').selectOption(String(company.id));
  await page.locator('#invoiceRecipientEmail').fill('smtp-success-e2e@example.com');
  await page.locator('#invoiceDate').fill('2026-04-30');
  await page.locator('#invoiceDueDate').fill('2026-05-14');
  await page.locator('#invoicePeriod').fill('2026-04-01 - 2026-04-30');
  await page.locator('#invoiceDescription').fill('E2E Send Success');
  await page.locator('#invoiceOperatorStreet').fill('Musterstrasse 12');
  await page.locator('#invoiceOperatorZipCity').fill('12345 Berlin');
  await page.locator('#invoiceOperatorEmail').fill('rechnung@example.com');
  await page.locator('#invoiceIban').fill('DE89370400440532013000');
  await page.locator('#invoiceBankName').fill('Musterbank');
  await page.locator('#invoiceTaxId').fill('123/456/78901');
  await page.locator('#invoiceVatId').fill('DE123456789');
  await page.locator('#invoiceNetAmount').fill('0');
  await page.locator('#invoiceVatRate').fill('19');

  const dialogPromise = page.waitForEvent('dialog');
  await page.locator('#invoiceSendButton').click();
  const dialog = await dialogPromise;
  expect(dialog.message()).toContain('Rechnung wurde per E-Mail versendet.');
  await dialog.accept();
});