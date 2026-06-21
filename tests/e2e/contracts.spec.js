const { test, expect } = require('@playwright/test');

async function login(request) {
  const username = process.env.E2E_SUPERADMIN_USER || 'superadmin';
  const password = process.env.E2E_SUPERADMIN_PASSWORD || '1234';
  const response = await request.post('/api/login', {
    data: { username, password, loginScope: 'server-admin' },
  });
  expect(response.ok()).toBeTruthy();
  const payload = await response.json();
  return { headers: { Authorization: `Bearer ${payload.token}` }, payload };
}

test.describe('Employment contracts', () => {
  test('templates list and validation endpoint for professional company', async ({ request }) => {
    const { headers, payload } = await login(request);
    const companies = await request.get('/api/companies', { headers });
    expect(companies.ok()).toBeTruthy();
    const list = await companies.json();
    const company = (list.companies || list || [])[0];
    const companyId = company?.id || payload.companyId;
    test.skip(!companyId, 'No company available for contract smoke test');

    const templates = await request.get(`/api/contracts/templates?company_id=${companyId}`, { headers });
    if (templates.status() === 403) {
      test.skip(true, 'employment_contracts not enabled on this plan');
    }
    expect(templates.ok()).toBeTruthy();
    const tpl = await templates.json();
    expect(Array.isArray(tpl.templates)).toBeTruthy();
    expect(tpl.templates.length).toBeGreaterThan(0);

    const integrations = await request.get(`/api/contracts/integrations-status?company_id=${companyId}`, { headers });
    expect(integrations.ok()).toBeTruthy();
    const status = await integrations.json();
    expect(typeof status.emailConfigured).toBe('boolean');
    expect(typeof status.smsConfigured).toBe('boolean');
  });
});
