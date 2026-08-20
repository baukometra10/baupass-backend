/**
 * Payslip studio chrome wiring — mocked APIs, no live Lohn required.
 */
const { test, expect } = require("@playwright/test");

const MOCK_BATCHES = {
  ok: true,
  batches: [
    {
      id: "batch-e2e-1",
      companyId: "co-e2e",
      companyName: "E2E Co",
      period: "2026-08",
      releasableCount: 1,
      statements: [
        {
          statementId: "stmt-1",
          displayName: "Test Worker",
          matchStatus: "matched",
          status: "pending",
          reviewed: true,
          canRelease: true,
          workerId: "w1",
          badgeId: "B-1",
          documentPeriod: "2026-08",
          netAmount: 1200,
          currency: "EUR",
          docType: "lohnabrechnung",
          title: "Lohnabrechnung",
        },
      ],
    },
  ],
};

test.describe("Payslip studio chrome", () => {
  test("Liste, Filter, Protokoll, Pull, confirm modal wiring", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("workpass-admin-token", "e2e-token");
      localStorage.setItem(
        "workpass-admin-user",
        JSON.stringify({ id: "u1", username: "e2e", role: "company-admin", company_id: "co-e2e" }),
      );
      localStorage.setItem("workpass-admin-company", "co-e2e");
      sessionStorage.removeItem("workpass-payslip-keys-hint-dismissed");
    });

    await page.route("**/api/**", async (route) => {
      const req = route.request();
      const url = req.url();
      if (url.includes("/api/v2/auth/session") || url.includes("/api/login")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            ok: true,
            token: "e2e-token",
            user: { id: "u1", username: "e2e", role: "company-admin", company_id: "co-e2e" },
          }),
        });
      }
      if (url.includes("/api/companies")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([{ id: "co-e2e", name: "E2E Co" }]),
        });
      }
      if (url.includes("/api/payroll/statements/pending")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MOCK_BATCHES),
        });
      }
      if (url.includes("/api/payroll/statements/pull-from-lohn")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ok: true, createdCount: 0, pendingCount: 1, message: "ok" }),
        });
      }
      if (url.includes("/api/payroll/statements/") && url.includes("/sheet")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ok: true, html: "<div class='datev-sheet-a4'>E2E</div>" }),
        });
      }
      if (url.includes("/api/inbox/counts") || url.includes("/api/payroll/accounting")) {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ok: true, counts: { open: 0, critical: 0 }, items: [] }),
        });
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      });
    });

    await page.goto("/admin-v2/index.html?company_id=co-e2e&payslipReview=1");
    const studio = page.locator("#payslipReviewStudio");
    await expect(studio).toBeVisible({ timeout: 20000 });
    await expect(page.locator("#payslipStudioTitle")).toBeVisible();

    // Filter toggle
    await page.locator("#payslipFiltersToggle").click();
    await expect(page.locator("#payslipArchiveTools")).not.toHaveClass(/is-collapsed/);

    // Liste collapse / expand
    await page.locator("#payslipListCollapseBtn").click();
    await expect(page.locator("#payslipStudioLayout")).toHaveClass(/is-list-collapsed/);
    await page.locator("#payslipListExpandRail").click();
    await expect(page.locator("#payslipStudioLayout")).not.toHaveClass(/is-list-collapsed/);

    // Pane chevron
    await page.locator("#payslipListCollapseBtnPane").click();
    await expect(page.locator("#payslipStudioLayout")).toHaveClass(/is-list-collapsed/);
    await page.locator("#payslipListExpandRail").click();

    // Protokoll
    await page.locator("#payslipStudioAuditBtn").click();
    await expect(page.locator("#payslipStudioAudit")).toBeVisible();
    await expect(page.locator("#payslipStudioAudit")).toContainText(/Protokoll/i);

    // Pull
    await page.locator("#payslipStudioPullBtn").click();
    await expect(page.locator("#payslipStudioSyncLine")).toBeVisible();

    // Release confirm modal
    await page.locator("#payslipStudioReleaseAll").click();
    await expect(page.locator("#payslipConfirmModal")).toBeVisible();
    await page.locator("#payslipConfirmCancel").click();
    await expect(page.locator("#payslipConfirmModal")).toBeHidden();

    // Keys hint dismiss
    const hint = page.locator("#payslipKeysHintBar");
    if (await hint.isVisible()) {
      await page.locator("#payslipKeysHintDismiss").click();
      await expect(hint).toBeHidden();
    }
  });
});
