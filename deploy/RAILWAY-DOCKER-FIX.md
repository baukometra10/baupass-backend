# Railway + Docker: 502 beheben

## Was wir sehen

| URL | Status | Bedeutung |
|-----|--------|-----------|
| `baupass-control.up.railway.app` | **502** | Container läuft nicht / falscher Port / stürzt ab |
| `web-production-922fe.up.railway.app` | **200** | Alter Stand (`20260516h`), funktioniert noch |

Docker-Image **`baupass/baupass:latest`** ist OK (lokal getestet, Build `20260516i`).

Problem liegt an der **Railway-Konfiguration**, nicht am Docker-Build.

---

## Lösung A (empfohlen): Alten funktionierenden Service nutzen

Datenbank und Domain bleiben, nur Image wechseln:

1. https://railway.app → Projekt mit **`web-production-922fe`**
2. Service **web** → **Settings** → **Source**
3. GitHub **Disconnect**
4. **Docker Image** → `baupass/baupass:latest`
5. **Deploy**

**Variables** vom alten Service **nicht löschen** (SMTP, IMAP, Secrets bleiben).

6. Prüfen: https://web-production-922fe.up.railway.app/worker-build.json → `20260516i`

Domain später auf `baupass-control` umziehen, wenn der Service dort läuft.

---

## Lösung B: `baupass-control` reparieren

### 1. Deploy-Logs

Railway → Service **baupass-control** → **Deployments** → letztes Deploy → **View Logs**

Typische Fehler:

- `CRITICAL: init_db() failed`
- `Address already in use`
- `Permission denied` auf `/data`
- Container startet, beendet sich sofort

### 2. Networking (Port)

**Settings** → **Networking** / **Public Networking**:

- Port: **`$PORT`** oder den Port, den Railway anzeigt (oft nicht 8000 fest eintragen)
- Die App liest `PORT` aus der Umgebung (`run_prod.py`) – das passt, wenn Railway `PORT` setzt.

### 3. Volume

- Volume an **`/data`** mounten (wie beim alten Service)
- Volume **nicht** löschen

### 4. Wichtige Variables (vom alten Service kopieren)

Mindestens:

| Variable | Zweck |
|----------|--------|
| `PUBLIC_BASE_URL` | `https://baupass-control.up.railway.app` |
| `BAUPASS_DB_PATH` | `/data/baupass.db` (optional, Auto-Erkennung unter `/data`) |

Optional für schnelleren Start (weniger 502 beim Hochfahren):

| Variable | Wert |
|----------|------|
| `BAUPASS_ENABLE_IMAP_POLLER` | `0` (später wieder `1` wenn IMAP passt) |
| `BAUPASS_RUN_DUNNING_ON_BOOT` | `0` |

Alle anderen Variablen (SMTP, Brevo, Secrets) vom **web-production**-Service **kopieren**.

### 5. Redeploy

**Deploy** → Image `baupass/baupass:latest` → warten 3–5 Min.

---

## Nach jedem Fix

```text
https://IHRE-URL.up.railway.app/api/health        → status ok
https://IHRE-URL.up.railway.app/worker-build.json → build 20260516i
```

---

## Update erneut hochladen

```powershell
cd C:\Users\u4363\Desktop\baustelle
docker build -t baupass/baupass:latest .
docker push baupass/baupass:latest
```

Railway → **Redeploy** (gleiches Image `latest`).

---

## Wenn Railway gar nicht geht

Lokal (sofort):

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\start-lokal.ps1
```

Oder VPS / Render mit Docker-Image (ohne GitHub): `docs/github-gesperrt-deploy.md`
