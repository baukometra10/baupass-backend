// @ts-check
const { defineConfig } = require('@playwright/test');
const path = require('path');

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
const defaultPythonPath = process.platform === 'win32'
  ? path.resolve('.venv', 'Scripts', 'python.exe')
  : path.resolve('.venv', 'bin', 'python');
const pythonCommand = process.env.PYTHON || `"${defaultPythonPath}"`;
const e2eServerCommand = `npx cross-env BAUPASS_E2E_RESET_SUPERADMIN=1 ${pythonCommand} backend/server.py`;

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 45_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL,
  },
  webServer: process.env.E2E_SKIP_SERVER ? undefined : {
    command: e2eServerCommand,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 15_000,
  },
  reporter: [['list']],
});
