const { test, expect } = require('@playwright/test');
const { execFileSync } = require('child_process');
const path = require('path');

function getWorkspacePythonExecutable() {
  return process.platform === 'win32'
    ? path.resolve('.venv', 'Scripts', 'python.exe')
    : path.resolve('.venv', 'bin', 'python');
}

test.use({ serviceWorkers: 'block' });

test('worker manual sync sends offline event queue to backend', async ({ page }) => {
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
    "cur.execute(\"INSERT INTO workers (id, company_id, first_name, last_name, insurance_number, worker_type, role, site, valid_until, status, photo_data, badge_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)\", (worker_id, '1', 'E2E', 'Test', 'INS-E2E', 'worker', 'arbeiter', 'site-e2e', now, 'active', '', 'E2E-TST'))",
    "cur.execute(\"INSERT INTO worker_app_sessions (worker_id, token, expires_at) VALUES (?, ?, ?)\", (worker_id, token, expires))",
    'conn.commit()',
    'print(token)',
    'conn.close()',
  ].join('\n');
  const token = execFileSync(pythonExecutable, ['-c', setupScript], { cwd: process.cwd() }).toString().trim();

  const offlineEvent = {
    type: 'offline_login',
    occurredAt: new Date().toISOString(),
    distanceMeters: 12,
  };

  await page.addInitScript(({ sessionToken }) => {
    localStorage.removeItem('baupass-api-base');
    localStorage.setItem('baupass-worker-token', sessionToken);
    localStorage.setItem('baupass-offline-photo-queue', JSON.stringify([]));
    localStorage.removeItem('baupass-offline-event-queue');
    localStorage.removeItem('baupass-worker-cached-payload');
  }, { sessionToken: token });

  await page.goto('http://127.0.0.1:8080/emp-app.html?worker=1', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('body.worker-loaded', { timeout: 45000 });

  await page.evaluate((event) => {
    localStorage.setItem('baupass-offline-event-queue', JSON.stringify([event]));
  }, offlineEvent);

  const [syncRequest] = await Promise.all([
    page.waitForRequest(
      (req) => req.url().includes('/api/worker-app/offline-events') && req.method() === 'POST',
      { timeout: 15000 },
    ),
    page.evaluate(() => manualSyncOfflineData()),
  ]);

  const response = await syncRequest.response();
  expect(response, 'offline-events request should receive a response').not.toBeNull();
  expect(response.status()).toBe(200);

  await expect
    .poll(async () => {
      const raw = await page.evaluate(() => localStorage.getItem('baupass-offline-event-queue'));
      return JSON.parse(raw || '[]').length;
    }, { timeout: 10000 })
    .toBe(0);
});
