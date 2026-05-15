const { test, expect } = require('@playwright/test');
const { execFileSync } = require('child_process');
const path = require('path');

function getWorkspacePythonExecutable() {
  return process.platform === 'win32'
    ? path.resolve('.venv', 'Scripts', 'python.exe')
    : path.resolve('.venv', 'bin', 'python');
}

function createWorkerSessionToken() {
  const pythonExecutable = getWorkspacePythonExecutable();
  const setupScript = [
    'import sqlite3, uuid',
    'from datetime import datetime, timedelta',
    "db_path = 'backend/baupass.db'",
    'conn = sqlite3.connect(db_path)',
    'cur = conn.cursor()',
    "try: cur.execute(\"INSERT INTO settings (id, platform_name, operator_name, turnstile_endpoint, rental_model) VALUES (1, 'Test', 'Operator', '/', 'r')\"); conn.commit()",
    'except: conn.rollback()',
    "try: cur.execute(\"INSERT INTO companies (id, name, contact, plan, status) VALUES (?, ?, ?, ?, ?)\", ('1', 'E2E Co', '', 'starter', 'active')); conn.commit()",
    "except: conn.rollback(); cur.execute(\"UPDATE companies SET plan = ? WHERE id = ?\", ('starter','1')); conn.commit()",
    "worker_id = str(uuid.uuid4())",
    "token = str(uuid.uuid4())",
    "now = datetime.utcnow().isoformat() + 'Z'",
    "expires = (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'",
    "cur.execute(\"INSERT INTO workers (id, company_id, first_name, last_name, insurance_number, worker_type, role, site, valid_until, status, photo_data, badge_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\", (worker_id, '1', 'E2E', 'Worker', 'INS-E2E', 'worker', 'arbeiter', 'site-e2e', now, 'active', '', 'E2E-TST'))",
    "cur.execute(\"INSERT INTO worker_app_sessions (worker_id, token, expires_at) VALUES (?, ?, ?)\", (worker_id, token, expires))",
    'conn.commit()',
    'print(token)',
    'conn.close()',
  ].join('\n');
  return execFileSync(pythonExecutable, ['-c', setupScript], { cwd: process.cwd() }).toString().trim();
}

test.use({ serviceWorkers: 'block' });

test('worker session loads pass and dynamic QR', async ({ page, request }) => {
  const token = createWorkerSessionToken();

  const meResponse = await request.get('/api/worker-app/me', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(meResponse.status()).toBe(200);
  const mePayload = await meResponse.json();
  expect(mePayload.worker?.firstName).toBe('E2E');

  const qrResponse = await request.get('/api/worker-app/dynamic-qr', {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(qrResponse.status()).toBe(200);
  const qrPayload = await qrResponse.json();
  expect(qrPayload.qrToken).toBeTruthy();

  await page.addInitScript(({ sessionToken }) => {
    localStorage.removeItem('baupass-api-base');
    localStorage.setItem('baupass-worker-token', sessionToken);
    localStorage.removeItem('baupass-worker-cached-payload');
  }, { sessionToken: token });

  await page.goto('/emp-app.html?worker=1&v=20260515c', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('body.worker-loaded', { timeout: 45000 });
  await expect(page.locator('#workerName, #dashboardName').first()).toContainText('E2E');
  await expect(page.locator('#workerBrandName, #dashboardBrandName').first()).toHaveText(/BAUPASS/i);

  await page.locator('#navVacation').click();
  await expect(page.locator('#leaveRequestCard')).toBeVisible();
  await page.locator('#navTimesheet').click();
  await expect(page.locator('#timesheetCard')).toBeVisible();
  await page.locator('#navDocuments').click();
  await expect(page.locator('#documentsCard')).toBeVisible();
  await page.locator('#navHome').click();
  await expect(page.locator('#workerDashboard')).toBeVisible();
});
