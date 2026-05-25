# Railway Deploy hängt – Fix-Checkliste

## Symptom

- GitHub `main` hat neuere Commits (z. B. `a4a4792`, Build `20260516i`)
- Live unter `https://web-production-922fe.up.railway.app/api/health` zeigt noch:
  - `"railwayGitCommit": "25c9a71..."`
  - `"workerPwa": { "build": "20260516h" }`

→ **Railway hat die letzten Commits nicht ausgerollt.**

## Schnell prüfen

```text
https://web-production-922fe.up.railway.app/api/health
https://web-production-922fe.up.railway.app/worker-build.json
```

Erfolg = `railwayGitCommit` beginnt mit `a4a4792` oder neuer, `build` = `20260516i`.

## Option A: Manuell in Railway (sofort)

1. [railway.app](https://railway.app) → Projekt mit Domain `web-production-922fe`
2. **Deployments** → letzten **Failed**-Eintrag öffnen → Build-Log lesen
3. **Settings** → **Source**: Repo `baukometra10/baupass-backend`, Branch `main`
4. **Redeploy** / **Deploy latest** auf Commit `bd57ad1` (oder aktuellster `main`)

## Option B: GitHub Actions (dauerhaft)

Repository **Settings → Secrets and variables → Actions**:

| Secret | Wert |
|--------|------|
| `RAILWAY_TOKEN` | Account token von Railway → Account → Tokens |
| `RAILWAY_SERVICE_ID` | Service-ID aus Railway → Service → Settings |

Workflow: `.github/workflows/railway-deploy.yml` (läuft bei jedem Push auf `main`).

Nach dem Setzen: **Actions → railway-deploy → Run workflow**.

## Fehler: `##NOT-FOUND## repository not found` (Initialization)

Railway findet das verknüpfte GitHub-Repo **nicht** (kein Docker-Problem).

**Fix in Railway:**

1. Projekt → Service **web** → **Settings** → **Source**
2. **Disconnect** (Git-Verbindung trennen)
3. **Connect Repo** erneut → **`baukometra10/baupass-backend`**, Branch **`main`**
4. Prüfen: GitHub-App „Railway“ hat Zugriff auf **`baukometra10`** und das Repo (bei privaten Repos unter github.com/settings/installations)

Häufige Ursachen: Repo umbenannt/verschoben, Org gewechselt, GitHub-App-Zugriff entzogen, falscher Repo-Name (z. B. noch `baustelle` statt `baupass-backend`).

**Alternative ohne Railway-Git:** GitHub Actions mit `RAILWAY_TOKEN` + `RAILWAY_SERVICE_ID` (Workflow `.github/workflows/railway-deploy.yml`) – deployt direkt aus dem Checkout, unabhängig von „Snapshot code“.

## Häufige Fehler im Build-Log

- **Build-Timeout / „Diagnosis failed“** – oft weil `COPY . .` ohne `.dockerignore` über 800 MB (`node_modules`, `.git`, `.venv`) hochlädt. Ab Fix-Commit mit `.dockerignore` im Repo-Root sollte der Build deutlich kleiner sein.
- Falscher Branch / falsches Repo verknüpft
- Start-Command nicht `python backend/run_prod.py` (siehe `railway.json`)

## Nach erfolgreichem Deploy

Mitarbeiter-Link neu öffnen (Cache leeren):

`https://web-production-922fe.up.railway.app/worker.html?view=card&badge=IHRE-BADGE-ID`

Unten muss **Build 20260516i** stehen.
