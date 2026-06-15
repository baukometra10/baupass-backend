# Repository Guidelines

## Project Structure & Module Organization
This repository follows a multi-component architecture for an enterprise platform focused on identity and access control:
- **Root**: Contains the core PWA/Web Frontend built with vanilla HTML/JS/CSS (no build step). `.\app.js` and `.\index.html` are the main entry points.
- **`.\backend`**: A Python Flask monolith (`.\backend\server.py`) handling API v1/v2, SQLite/PostgreSQL storage, background jobs (RQ), and PDF generation.
- **`.\mobile`**: A Flutter application for employees located in the `.\mobile` directory.
- **`.\desktop`**: An Electron-based shell wrapping the web platform.
- **`.\admin-v2`**: A modernized, lightweight admin dashboard using API v2.
- **`.\deploy`**: Contains environment-specific orchestration scripts (PowerShell/Bash) for Railway, Hetzner, and Windows Service installation.

## Build, Test, and Development Commands
### Backend (Python)
- **Install dependencies**: `pip install -r .\backend\requirements.txt`
- **Start Dev Server**: `python .\backend\server.py`
- **Start Prod Server**: `python .\backend\entrypoint.py --mode prod`
- **Run Tests**: `pytest` (executed from root or `.\backend`)

### Frontend & Desktop (Node.js)
- **Start Desktop App**: `npm run desktop`
- **Desktop (Local URL)**: `npm run desktop:local`
- **Build Desktop**: `npm run build`
- **Run E2E Tests**: `npm run test:e2e` (Playwright)

### Mobile (Flutter)
- **Install Dependencies**: `flutter pub get`
- **Run App**: `flutter run`
- **Build APK**: `flutter build apk`

## Coding Style & Naming Conventions
- **Frontend**: Standard Vanilla JS. Avoid adding complex build tools or frameworks to the root PWA. Follow the established pattern of using global state or event listeners in `.\app.js`.
- **Backend**: Use Flask's routing and `werkzeug.security` for auth. Most logic is currently centralized in `.\backend\server.py`.
- **Environment**: Use `.\.env` files for configuration. The system supports `.\.env.railway.example` and `.\.env.worker-mobile.example` as templates.

## Testing Guidelines
- **E2E Testing**: Powered by Playwright. Tests are located in `.\tests\e2e`. Use `npm run test:e2e:platform` for smoke tests.
- **Backend Testing**: Powered by Pytest. Tests are located in `.\backend\tests`.
- **Manual Checks**: Refer to the "Kamera-/Foto-Regression-Checkliste" in `.\README.md` for manual verification of hardware-linked features.

## Commit & Pull Request Guidelines
Follow the established pattern of descriptive, prefix-less commit messages that reference the component and the fix/feature:
- `Fix [Component] [Status Code] and [Description]` (e.g., "Fix WebSocket 400, Cameras API 500, and error handling")
- `Unify [Component] [Description]`
- `Implement [Feature] [Description]`

## Agent Instructions
- **Ignore Patterns**: Respect `.\.cursorignore`. Avoid scanning or searching `node_modules/`, `.venv/`, `mobile/build/`, and large log files like `server-err.txt`.
- **Database**: Local SQLite databases (`.\backend\*.db`) are ignored by git; do not attempt to commit them.
- **Security**: Never commit secrets found in `.\backend\wallet\` or `.env` files.
