# Deploy ohne GitHub

Die App ist ein Python-Backend + statische Dateien (`emp-app.html`, `worker-app.js`, …).  
Alles kann **direkt vom PC** oder **eigenem Server** ausgeliefert werden.

## Option 1: Railway nur per CLI (empfohlen, wenn Domain bleiben soll)

GitHub in Railway **trennen**, Updates vom Rechner hochladen.

### Einmalig

1. Railway → Service **web** → **Settings** → **Source** → **Disconnect**
2. Auf dem PC (im Projektordner `baustelle`):

```powershell
npm install -g @railway/cli
railway login
railway link
```

`railway link` → Projekt **baupass-control** (Domain `baupass-control.up.railway.app`).

### Jedes Update (z. B. nach Worker-App-Fix)

```powershell
cd C:\Users\u4363\Desktop\baustelle
.\deploy\railway-up.ps1
```

Oder manuell: `railway up --detach`

### Prüfen

- `https://baupass-control.up.railway.app/api/health`
- `https://baupass-control.up.railway.app/worker-build.json` → Build-Tag aus `worker-build.json`

**Datenbank:** Volume unter `/data` auf Railway bleibt erhalten (nicht neu anlegen).

---

## Option 2: Eigener Windows-Server / VPS (ohne Railway)

Backend lokal oder auf Server, HTTPS davor (Nginx/Caddy).

```powershell
cd C:\Users\u4363\Desktop\baustelle
pip install -r backend\requirements.txt
$env:HOST = "127.0.0.1"
$env:PORT = "8000"
$env:PUBLIC_BASE_URL = "https://ihre-domain.de"
python backend\entrypoint.py --mode prod
```

Dienst dauerhaft: `deploy\windows-service-install.ps1`  
Reverse Proxy: `deploy\nginx.conf.example`

Mitarbeiter-URL dann z. B.:

`https://ihre-domain.de/emp-app.html?worker=1&view=card`

---

## Option 3: Docker-Image (ohne Git, beliebiger Host)

```powershell
cd C:\Users\u4363\Desktop\baustelle
docker build -t baupass:latest .
```

Image nach **Docker Hub** pushen und in Railway unter **Deploy from Docker image** nutzen — oder auf jedem VPS mit `docker run` starten.

`.dockerignore` im Repo hält den Build klein.

---

## Option 4: Render / anderer PaaS

`render.yaml` liegt im Repo; Verbindung kann per **CLI** oder Dashboard mit GitLab/Bitbucket erfolgen — oder Image-basiert wie Option 3.

---

## Was Sie nicht brauchen

- Kein GitHub für Railway, wenn Sie **CLI** oder **Docker-Image** nutzen
- Kein GitHub Pages für die Mitarbeiter-App — die PWA liegt im gleichen Ordner wie das Backend und wird von Flask mit ausgeliefert

## Git lokal behalten?

Lokales Git auf dem PC ist optional (Versionsstand). Für **Deploy** reicht der Ordner `baustelle` + `railway up` oder eigener Server.
