# Andere Wege (wenn Railway CLI / Token nicht geht)

## Weg 1: Lokal auf Ihrem PC (sofort, ohne Cloud)

Im Terminal:

```powershell
cd C:\Users\u4363\Desktop\baustelle
powershell -ExecutionPolicy Bypass -File .\deploy\start-lokal.ps1
```

Dann im Browser:

- Admin: http://localhost:8000/
- Mitarbeiter: http://localhost:8000/worker.html?view=card

Fuer Zugriff vom Handy im gleichen WLAN: `http://IHRE-PC-IP:8000/...`  
(PC-IP mit `ipconfig` → IPv4)

Optional oeffentlich (Test): https://ngrok.com → `ngrok http 8000` → URL nutzen

---

## Weg 2: Docker + Railway (ohne GitHub, ohne railway login)

Voraussetzung: **Docker Desktop** installiert (docker.com/products/docker-desktop)

### 2a) Image bauen und zu Docker Hub pushen

```powershell
cd C:\Users\u4363\Desktop\baustelle
docker build -t IHR_DOCKERHUB_NAME/baupass:latest .
docker login
docker push IHR_DOCKERHUB_NAME/baupass:latest
```

### 2b) In Railway (nur Browser)

1. railway.app → Projekt **baupass-control**
2. Service **web** → **Settings**
3. Unter **Deploy** → **Source** → **Docker Image** (nicht GitHub)
4. Image: `IHR_DOCKERHUB_NAME/baupass:latest`
5. **Deploy**
6. Volume `/data` und Variable `PUBLIC_BASE_URL=https://baupass-control.up.railway.app`

Kein `railway login`, kein Token.

---

## Weg 3: Render.com (Alternative zu Railway)

1. https://render.com → Account
2. **New** → **Web Service**
3. Repo verbinden **oder** „Deploy from Docker“ / manuelles Image
4. Im Repo liegt bereits `render.yaml` als Vorlage
5. Start: `python backend/entrypoint.py --mode prod`
6. Disk mount fuer DB (Render Disk) oder Postgres

Domain z.B. `https://baupass-backend.onrender.com`

---

## Weg 4: Eigener Windows-Server / VPS

Alles in einen Ordner kopieren (USB, ZIP, RDP):

```powershell
pip install -r backend\requirements.txt
$env:PUBLIC_BASE_URL = "https://ihre-domain.de"
python backend\entrypoint.py --mode prod
```

Dauerhaft: `deploy\windows-service-install.ps1`  
HTTPS: `deploy\nginx.conf.example`

Anbieter: Hetzner, IONOS, Strato VPS (ca. 5–10 EUR/Monat)

---

## Weg 5: GitHub in Railway reparieren (wenn Sie doch Cloud wollen)

Fehler war: `repository not found`

1. railway.app → Service → Settings → Source
2. Repo **baupass/baupass-backend** (nicht „baustelle“)
3. Branch **main**
4. GitHub-App Railway: Zugriff auf Org **baupass** erlauben
5. Redeploy

Dann reicht `git push` vom PC – ohne CLI.

---

## Empfehlung

| Ziel | Weg |
|------|-----|
| Sofort testen ob App geht | **Weg 1** lokal |
| Cloud mit alter Domain baupass-control | **Weg 2** Docker Image |
| Kein Railway mehr | **Weg 3** Render oder **Weg 4** VPS |
