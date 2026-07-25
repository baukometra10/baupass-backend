const { test, expect } = require('@playwright/test');

async function login(request, { username, password, loginScope }) {
  const response = await request.post('/api/login', {
    data: { username, password, loginScope },
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  expect(payload.token).toBeTruthy();
  return { headers: { Authorization: `Bearer ${payload.token}` }, payload };
}

test.describe('Owner gate / turnstile sensitive deny', () => {
  test('turnstile cannot list docs or contracts; admin unlock flow endpoint exists', async ({ request }) => {
    const saUser = process.env.E2E_SUPERADMIN_USER || 'superadmin';
    const saPass = process.env.E2E_SUPERADMIN_PASSWORD || '1234';
    const { headers: saHeaders } = await login(request, {
      username: saUser,
      password: saPass,
      loginScope: 'server-admin',
    });

    const created = await request.post('/api/companies', {
      headers: saHeaders,
      data: {
        name: `E2E Gate ${Date.now()}`,
        contact: 'e2e',
        adminPassword: '1234',
        turnstilePassword: '1234',
        turnstileCount: 1,
        plan: 'professional',
      },
    });
    expect([200, 201]).toContain(created.status());
    const body = await created.json();
    const companyId = body.company?.id || body.id;
    const gate = body.turnstileCredentials || {};
    test.skip(!companyId || !gate.username, 'Company/turnstile credentials missing');

    const { headers: gateHeaders } = await login(request, {
      username: gate.username,
      password: gate.password || '1234',
      loginScope: 'turnstile',
    });

    const docs = await request.get(`/api/v2/docs?company_id=${companyId}`, { headers: gateHeaders });
    expect(docs.status()).toBe(403);
    const docsBody = await docs.json();
    expect(docsBody.error).toBe('sensitive_forbidden');
    expect(docsBody.roleBlocked).toBeTruthy();

    const contracts = await request.get(`/api/contracts?company_id=${companyId}`, { headers: gateHeaders });
    expect(contracts.status()).toBe(403);
    const contractsBody = await contracts.json();
    expect(contractsBody.error).toBe('sensitive_forbidden');

    const lockStatus = await request.get(`/api/contracts/lock-status?company_id=${companyId}`, {
      headers: saHeaders,
    });
    expect(lockStatus.ok()).toBeTruthy();
    const status = await lockStatus.json();
    expect(typeof status.lockRequired === 'boolean' || typeof status.unlocked === 'boolean').toBeTruthy();
  });

  test('admin-v2 docs page exposes owner unlock overlay markup', async ({ request }) => {
    const page = await request.get('/admin-v2/docs.html');
    expect(page.ok()).toBeTruthy();
    const html = await page.text();
    expect(html).toContain('id="docsLockOverlay"');
    expect(html).toContain('id="docsLockSendBtn"');
    expect(html).toContain('id="docsLockVerifyBtn"');
    expect(html).toContain('owner-unlock.js');
  });
});
