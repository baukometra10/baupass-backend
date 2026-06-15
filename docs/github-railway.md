# GitHub + Railway (Standard-Workflow)

Repository: **https://github.com/baukometra10/baupass-backend**

Railway baut bei jedem Push auf `main` automatisch neu (wenn das Repo als Quelle verbunden ist).

---

## 1. Code auf GitHub bringen

PowerShell im Projektordner:

```powershell
cd C:\Users\u4363\Desktop\baustelle
.\deploy\github-push.ps1
```

Beim Login:

- **Benutzer:** `baukometra10`
- **Passwort:** Personal Access Token ([Tokens erstellen](https://github.com/settings/tokens), Haken **repo**)

Prüfen: Auf GitHub sollte `main` mit Ordnern `backend/`, `index.html`, `Dockerfile` sichtbar sein.

---

## 2. Railway mit GitHub verbinden

1. https://railway.app → einloggen  
2. **New Project** → **Deploy from GitHub repo**  
3. GitHub-App **Railway** autorisieren (Konto **baukometra10**)  
4. Repo **`baupass-backend`** wählen  
5. Branch **`main`** → Deploy startet  

Falls das Repo **nicht** in der Liste steht:

- https://github.com/settings/installations → **Railway** → **Configure**  
- **Repository access** → **Only select repositories** → `baupass-backend` hinzufügen  

---

## 3. Railway-Einstellungen (einmalig)

| Einstellung | Wert |
|-------------|------|
| **Builder** | Dockerfile (automatisch via `railway.json`) |
| **Start** | `python backend/entrypoint.py --mode prod` |
| **Volume** | Mount **`/data`** (Datenbank bleibt erhalten) |
| **`PUBLIC_BASE_URL`** | `https://DEINE-DOMAIN.up.railway.app` |
| **Redis** (empfohlen) | Service **Redis** + `REDIS_URL` referenzieren |
| **RQ Worker** (empfohlen) | Zweiter Service: `python -m backend.app.tasks.worker` |

Ausführlich (DE/AR): [railway-production-setup-AR.md](./railway-production-setup-AR.md)  
7-Tage Markt-Plan: [market-readiness-7-days-AR.md](./market-readiness-7-days-AR.md)

Domain: Service → **Settings** → **Networking** → **Generate Domain**.

Nach Domain-Erstellung `PUBLIC_BASE_URL` setzen und **Redeploy**.

---

## 4. Täglicher Ablauf (nur noch Git)

```powershell
cd C:\Users\u4363\Desktop\baustelle
git add .
git commit -m "kurze Beschreibung der Änderung"
.\deploy\github-push.ps1
```

Railway deployt automatisch (1–5 Minuten).

Prüfen:

- `https://DEINE-DOMAIN.up.railway.app/api/health`
- `https://DEINE-DOMAIN.up.railway.app/worker-build.json`

---

## 5. Optional: GitHub Actions (Backup-Deploy)

Wenn Railway das Repo nicht findet (`NOT-FOUND`), kann zusätzlich der Workflow laufen:

**GitHub** → Repo → **Settings** → **Secrets and variables** → **Actions**:

| Secret | Woher |
|--------|--------|
| `RAILWAY_TOKEN` | Railway → Account → **Tokens** |
| `RAILWAY_SERVICE_ID` | Railway → Service → Settings → **Service ID** |

Workflow: `.github/workflows/railway-deploy.yml` (startet bei jedem Push auf `main`).

---

## Wichtig: Daten nach Git-Push weg (Karten / Mitarbeiter fehlen)

**Ursache:** Ohne persistentes Volume speichert Railway die SQLite-DB **im Container**. Jeder neue Deploy startet mit einer **leeren** Datenbank – Karten wirken „nie angelegt“.

**Pflicht (einmalig pro Railway-Service):**

1. Service → **Volumes** → Volume anlegen und an **`/data`** mounten (nicht löschen bei Updates).
2. Variable setzen: `BAUPASS_DB_PATH=/data/baupass.db` (optional, Auto-Erkennung wenn `/data` beschreibbar ist).
3. **Redeploy** – danach neu angelegte Mitarbeiter bleiben erhalten.

**Prüfen nach Deploy:**

```text
https://DEINE-DOMAIN.up.railway.app/api/health
```

Erwartung: `"db": { "persistent": true, "workersActive": <Anzahl> }`.  
Bei `"persistent": false` → Volume fehlt oder falscher Service.

**Nicht zwei verschiedene Railway-URLs mischen** (z. B. alter `web-production-*` vs. neuer `baupass-production-*`) – jeder Service hat seine **eigene** Datenbank.

Backups auf dem Volume: `/data/backups/` (automatisch beim Start, wenn Mitarbeiter existieren).

---

## Häufige Probleme

| Problem | Lösung |
|---------|--------|
| Nach Push sind alle Karten weg | Volume `/data` + `BAUPASS_DB_PATH=/data/baupass.db`; `/api/health` → `persistent: true` |
| `denied to baupass` beim Push | `.\deploy\github-push.ps1` (löscht alte Anmeldung) |
| Repo leer auf GitHub | Push noch nicht gelungen → Schritt 1 |
| Railway zeigt alten Stand | **Deployments** → **Redeploy**; Health prüfen: `railwayGitCommit` |
| Build-Timeout | `.dockerignore` im Repo (liegt im Projekt) |
| 502 nach Deploy | Volume `/data`, Logs unter **Deployments** |

---

## Altes Konto / Docker-Image

Früher: `baupass/baupass-backend` oder Docker Hub `baupass/baupass:latest`.

Jetzt: **nur noch GitHub** `baukometra10/baupass-backend` als Source in Railway (GitHub trennen → Repo neu verbinden).
