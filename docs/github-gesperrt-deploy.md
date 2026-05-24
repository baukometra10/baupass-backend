# GitHub gesperrt („account is flagged“) – trotzdem online

Wenn GitHub **keine Drittanbieter-Apps** erlaubt, funktionieren **Render + GitHub** und **Railway + GitHub** nicht.

**GitHub brauchen Sie für Deploy nicht.** Drei Wege ohne GitHub-Verbindung:

| Weg | Kosten | Schwierigkeit | GitHub? |
|-----|--------|---------------|---------|
| **A: Docker Hub → Railway** | ~0 (Railway-Guthaben) | Mittel, nur Browser + Docker | Nein |
| **B: Railway CLI** (`railway up`) | ~0 | Einfach wenn Login klappt | Nein |
| **C: Lokal / VPS** | 0 lokal / ab ~4 € VPS | Einfach | Nein |

---

## Weg A: Docker Hub + Railway (empfohlen wenn CLI nervt)

Nur **Docker Hub** (E-Mail-Account) + **Railway im Browser**. Kein GitHub.

### 1. Docker Desktop

https://www.docker.com/products/docker-desktop/ → installieren → starten

### 2. Docker Hub Account

https://hub.docker.com → Sign Up (beliebiger Name, z. B. `meinname`)

### 3. Image bauen und hochladen (PowerShell)

```powershell
cd C:\Users\u4363\Desktop\baustelle
powershell -ExecutionPolicy Bypass -File .\deploy\docker-push.ps1
```

Das Skript fragt Ihren Docker-Hub-Benutzernamen und baut/pusht das Image.

Oder manuell (ersetzen `IHRNAME`):

```powershell
cd C:\Users\u4363\Desktop\baustelle
docker build -t IHRNAME/baupass:latest .
docker login
docker push IHRNAME/baupass:latest
```

### 4. Railway (nur Webseite)

1. https://railway.app → einloggen (E-Mail/Google – **nicht** GitHub nötig)
2. Projekt **baupass-control** → Service **web**
3. **Settings** → **Source** → **Disconnect** (GitHub trennen, falls noch verbunden)
4. **Deploy** / **Source** → **Docker Image** (oder „Deploy from image“)
5. Image: `IHRNAME/baupass:latest`
6. **Deploy** / Redeploy

### 5. Umgebungsvariablen (Railway → Variables)

| Variable | Wert |
|----------|------|
| `PUBLIC_BASE_URL` | `https://baupass-control.up.railway.app` |
| Volume | Mount `/data` (falls schon angelegt – DB bleibt) |

### 6. Prüfen

- https://baupass-control.up.railway.app/api/health
- https://baupass-control.up.railway.app/worker-build.json

**Jedes Update:** Schritt 3 erneut (`docker-push.ps1`), dann in Railway **Redeploy** (gleiches Image-Tag `latest`).

---

## Weg B: Railway CLI (Ordner hochladen, kein Git)

```powershell
npm install -g @railway/cli
cd C:\Users\u4363\Desktop\baustelle
railway login
```

→ Browser öffnet sich → bei **Railway** anmelden (nicht GitHub-App für Repo).

```powershell
railway link
.\deploy\railway-up.ps1
```

Wichtig: Bei `railway login` **Account Token** von railway.com/account/tokens – **keine** Projekt-UUID aus Cmd+K.

---

## Weg C: Nur PC / Handy im WLAN

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\start-lokal.ps1
```

- PC: http://localhost:8000/
- Handy (gleiches WLAN): `http://PC-IP:8000/worker.html?view=card` (`ipconfig` → IPv4)

Öffentlich testen: https://ngrok.com → `ngrok http 8000`

---

## Render ohne GitHub?

Render will fast immer ein Git-Repo. **Ohne GitHub** dort:

- **Docker Image** auf Render (Registry verbinden), oder
- lieber **Weg A** (Railway + Docker Hub)

---

## GitHub-Flag anfechten (optional)

https://support.github.com → „account flagged“ – kann Tage dauern.  
Für Deploy: Weg A oder B nutzen, nicht warten.

---

## Neues GitHub-Konto?

Nur als letzte Option für Versionsverwaltung. Für **Deploy** weiter Weg A/B – kein neues GitHub nötig.
