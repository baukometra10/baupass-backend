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

async function loginSuperadminOrSkip(request, credentials) {
  try {
    return await login(request, credentials);
  } catch (error) {
    const message = String(error?.message || '');
    if (
      message.includes('login_failed:invalid_credentials')
      || message.includes('login_failed:otp_required')
      || message.includes('login_failed:too_many_attempts')
    ) {
      test.skip(true, 'Superadmin-Login lokal nicht verfuegbar (Credentials/OTP/Rate-Limit).');
      return null;
    }
    throw error;
  }
}

async function firstActiveCompany(request, token) {
  const response = await request.get('/api/companies', { headers: authHeaders(token) });
  expect(response.status()).toBe(200);
  const rows = (await response.json()) || [];
  const active = rows.find((row) => !row.deleted_at);
  expect(active).toBeTruthy();
  return active;
}

test('company-admin is forbidden for invoice ops endpoints', async ({ request }) => {
  ensureLocalCompanyAdminCredentials('firma_invoice_ops', 'E2E Invoice Ops Admin');
  const companyAdmin = await login(request, {
    username: env('E2E_COMPANY_ADMIN_USERNAME', 'firma_invoice_ops'),
    password: env('E2E_COMPANY_ADMIN_PASSWORD', '1234'),
    loginScope: 'company-admin',
  });

  const headers = authHeaders(companyAdmin.token);

  const metrics = await request.get('/api/invoices/ops-metrics', { headers });
  expect(metrics.status()).toBe(403);

  const deadLetters = await request.get('/api/invoices/dead-letters', { headers });
  expect(deadLetters.status()).toBe(403);

  const approvals = await request.get('/api/invoices/approvals/pending', { headers });
  expect(approvals.status()).toBe(403);
});

test('superadmin bulk retry approval requires second approver and can be approved', async ({ request }) => {
  ensureLocalSuperadminCredentials(env('E2E_SUPERADMIN_USERNAME', 'superadmin_invoice_ops_1'), 'E2E Invoice Ops Superadmin 1', env('E2E_SUPERADMIN_PASSWORD', '1234'));
  ensureLocalSuperadminCredentials(env('E2E_SUPERADMIN2_USERNAME', 'superadmin_invoice_ops_2'), 'E2E Invoice Ops Superadmin 2', env('E2E_SUPERADMIN2_PASSWORD', 'E2Epass!123'));
  const requester = await loginSuperadminOrSkip(request, {
    username: env('E2E_SUPERADMIN_USERNAME', 'superadmin_invoice_ops_1'),
    password: env('E2E_SUPERADMIN_PASSWORD', '1234'),
    loginScope: 'server-admin',
    otpCode: env('E2E_SUPERADMIN_OTP', ''),
  });
  if (!requester) {
    return;
  }

  const approver = await loginSuperadminOrSkip(request, {
    username: env('E2E_SUPERADMIN2_USERNAME', 'superadmin_invoice_ops_2'),
    password: env('E2E_SUPERADMIN2_PASSWORD', 'E2Epass!123'),
    loginScope: 'server-admin',
    otpCode: env('E2E_SUPERADMIN2_OTP', ''),
  });
  if (!approver) {
    return;
  }

  if (String(requester.user?.id || '') === String(approver.user?.id || '')) {
    test.skip(true, 'Approval-Flow braucht zwei unterschiedliche Superadmin-Konten.');
    return;
  }

  const company = await firstActiveCompany(request, requester.token);
  const invoiceNumber = `E2E-OPS-${Date.now()}`;

  const createInvoice = await request.post('/api/invoices/send', {
    headers: authHeaders(requester.token),
    data: {
      companyId: company.id,
      recipientEmail: 'ops-e2e@example.com',
      invoiceNumber,
      invoiceDate: '2026-04-19',
      dueDate: '2026-05-03',
      invoicePeriod: '2026-04',
      description: 'E2E Ops Approval Flow',
      renderedHtml: '<html><body>E2E Ops Approval Flow</body></html>',
      netAmount: 100,
      vatRate: 19,
    },
  });
  expect(createInvoice.status()).toBe(200);
  const createdPayload = await createInvoice.json();
  const invoiceId = createdPayload?.invoice?.id;
  expect(invoiceId).toBeTruthy();

  const bulkRetry = await request.post('/api/invoices/retry-send-bulk', {
    headers: authHeaders(requester.token),
    data: { invoiceIds: [invoiceId] },
  });
  expect(bulkRetry.status()).toBe(202);
  const bulkPayload = await bulkRetry.json();
  const approvalId = bulkPayload?.approvalId;
  expect(approvalId).toBeTruthy();

  const selfApprove = await request.post(`/api/invoices/approvals/${approvalId}/decision`, {
    headers: authHeaders(requester.token),
    data: { decision: 'approve' },
  });
  expect(selfApprove.status()).toBe(403);

  const approve = await request.post(`/api/invoices/approvals/${approvalId}/decision`, {
    headers: authHeaders(approver.token),
    data: { decision: 'approve' },
  });
  expect(approve.status()).toBe(200);
  const approvePayload = await approve.json();
  expect(approvePayload?.status).toBe('approved');

  const pendingAfter = await request.get('/api/invoices/approvals/pending', {
    headers: authHeaders(requester.token),
  });
  expect(pendingAfter.status()).toBe(200);
  const pendingRows = (await pendingAfter.json()) || [];
  expect(pendingRows.some((row) => String(row.id) === String(approvalId))).toBeFalsy();
});
