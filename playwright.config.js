// @ts-check
const { defineConfig } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8080';
function resolveWorkspacePython() {
  const candidates = process.platform === 'win32'
    ? [
        path.resolve('.venv311', 'Scripts', 'python.exe'),
        path.resolve('.venv', 'Scripts', 'python.exe'),
      ]
    : [
        path.resolve('.venv311', 'bin', 'python'),
        path.resolve('.venv', 'bin', 'python'),
      ];
  return candidates.find((candidate) => fs.existsSync(candidate)) || candidates[candidates.length - 1];
}
const defaultPythonPath = resolveWorkspacePython();
const pythonCommand = process.env.PYTHON || `"${defaultPythonPath}"`;
const projectRoot = path.resolve(__dirname);
const e2eServerCommand = `npx cross-env BAUPASS_E2E_RESET_SUPERADMIN=1 PYTHONPATH="${projectRoot}" ${pythonCommand} -m backend.server`;

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
    timeout: 120_000,
  },
  reporter: [['list']],
});
