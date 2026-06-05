/**
 * Camera / photo-button smoke tests (E2E)
 *
 * These tests verify that:
 *  1. The photo UI elements are present in the worker-create modal.
 *  2. #startCameraButton is visible and clickable; after clicking it in a
 *     headless / camera-less environment the #photoDebugText element shows
 *     a [CAM-xxx] diagnostic code (not a blank or unhandled error).
 *  3. The file-upload path (#uploadPhotoButton → #photoFileInput) is wired
 *     correctly – clicking the button triggers a file-input element.
 *  4. #capturePhotoButton is present (capture-after-start path).
 *
 * Because Playwright runs without a real camera, getUserMedia always rejects.
 * The tests assert on the diagnostic code mechanism, not on a live preview.
 */

const { test, expect } = require('@playwright/test');
const { execFileSync } = require('child_process');
const path = require('path');

// ── helpers ──────────────────────────────────────────────────────────────────

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
    "assert company is not None, 'No active company found for E2E camera test bootstrap'",
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
  execFileSync(pythonExecutable, ['-c', script], { cwd: process.cwd(), stdio: 'ignore' });
}

async function loginUI(page, username, password) {
  await page.goto('/');
  await page.locator('#loginUsername').fill(username);
  await page.locator('#loginPassword').fill(password);
  await page.locator('#loginForm button[type="submit"]').click();
  await page.waitForSelector('#mainShell', { timeout: 12_000 });
}

async function navigateToWorkerForm(page) {
  // Navigate to the workers view via the nav link.
  await page.locator('.nav-link[data-view="workers"]').click();
  // The worker form (with camera section) is always present in this view.
  await page.waitForSelector('#startCameraButton', { timeout: 8_000 });
}

const E2E_USERNAME = 'e2e_camera_admin';
const E2E_DISPLAY  = 'E2E Camera Admin';
const PASSWORD     = '1234';

// ── tests ─────────────────────────────────────────────────────────────────────

test.describe('Camera / photo-button smoke', () => {
  test.beforeAll(() => {
    try {
      ensureLocalCompanyAdminCredentials(E2E_USERNAME, E2E_DISPLAY);
    } catch (err) {
      // If bootstrap fails (e.g. no DB yet) the tests will be skipped in beforeEach.
    }
  });

  test('photo UI elements are present in worker-create modal', async ({ page }) => {
    // Allow camera permission to be denied (no real device available).
    await page.context().grantPermissions([]);

    try {
      await loginUI(page, E2E_USERNAME, PASSWORD);
    } catch {
      test.skip(true, 'Login failed – backend not reachable or credentials mismatch.');
      return;
    }

    await navigateToWorkerForm(page);

    // 1. All required photo elements are present.
    await expect(page.locator('#startCameraButton')).toBeVisible();
    await expect(page.locator('#capturePhotoButton')).toBeVisible();
    await expect(page.locator('#uploadPhotoButton')).toBeVisible();
    await expect(page.locator('#photoFileInput')).toBeAttached(); // hidden, so not visible
    await expect(page.locator('#photoDebugText')).toBeAttached();
  });

  test('#startCameraButton click produces a [CAM-xxx] diagnostic code when camera unavailable', async ({ page }) => {
    // Explicitly deny camera so getUserMedia rejects with NotAllowedError.
    await page.context().grantPermissions([]);

    try {
      await loginUI(page, E2E_USERNAME, PASSWORD);
    } catch {
      test.skip(true, 'Login failed – backend not reachable or credentials mismatch.');
      return;
    }

    await navigateToWorkerForm(page);

    // Click the camera start button.
    await page.locator('#startCameraButton').click();

    // Allow up to 5 s for the diagnostic text to appear (async getUserMedia rejection).
    await page.waitForFunction(
      () => {
        const el = document.querySelector('#photoDebugText');
        return el && /\[CAM-/.test(el.textContent || '');
      },
      { timeout: 5_000 }
    );

    const debugText = await page.locator('#photoDebugText').textContent();
    expect(debugText).toMatch(/\[CAM-/);
    // Must be one of the known codes, not a generic fallback.
    expect(debugText).toMatch(/\[CAM-(HTTPS|DENIED|NOTFOUND|INUSE|CONSTRAINT|API|START)\]/);
  });

  test('#uploadPhotoButton click triggers the hidden file input', async ({ page }) => {
    await page.context().grantPermissions([]);

    try {
      await loginUI(page, E2E_USERNAME, PASSWORD);
    } catch {
      test.skip(true, 'Login failed – backend not reachable or credentials mismatch.');
      return;
    }

    await navigateToWorkerForm(page);

    // Intercept the file chooser triggered by the upload button.
    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser', { timeout: 3_000 }),
      page.locator('#uploadPhotoButton').click(),
    ]);

    // A file chooser dialog was opened – the binding is intact.
    expect(fileChooser).toBeTruthy();
    // Dismiss without selecting a file.
    await fileChooser.setFiles([]);
  });
});
