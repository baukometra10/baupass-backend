# WorkPass kostenlos online stellen

> **GitHub gesperrt („account is flagged“)?**  
> Render/Railway **mit GitHub** geht dann nicht. → **`docs/github-gesperrt-deploy.md`** (Docker Hub + Railway, ohne GitHub).

Empfehlung **mit funktionierendem GitHub**: Render.com.  
**Ohne GitHub**: Docker Hub + Railway (siehe oben).

| Anbieter | Kosten | Schwierigkeit | Nachteil |
|----------|--------|---------------|----------|
| **Render** | 0 EUR | Einfach | Schläft nach ~15 Min ohne Besucher (kalt start ~30 s) |
| Railway | ~5 USD Guthaben/Monat | Mittel | CLI/Token-Probleme bei Ihnen |
| Lokal + ngrok | 0 EUR | Sehr einfach | Nur Test, URL ändert sich |

---

## Render – Schritt für Schritt (ca. 15 Minuten)

### 1. Account

1. https://render.com → **Get Started** (mit GitHub anmelden ist am einfachsten)
2. GitHub-Zugriff auf Repo **baupass/baupass-backend** erlauben

### 2. Neuen Web Service

1. Dashboard → **New +** → **Web Service**
2. Repository **baupass-backend** auswählen
3. Einstellungen:

| Feld | Wert |
|------|------|
| Name | `baupass` (oder beliebig) |
| Region | Frankfurt (EU) wenn verfügbar |
| Branch | `main` |
| Runtime | **Python 3** |
| Build Command | `pip install -r backend/requirements.txt` |
| Start Command | `python backend/entrypoint.py --mode prod` |
| Plan | **Free** |

4. **Environment Variables** (optional, Render setzt die URL oft automatisch):

| Key | Value |
|-----|--------|
| `PYTHON_VERSION` | `3.11.9` |
| `PUBLIC_BASE_URL` | *(nach Deploy, siehe Schritt 3)* |

> **Hinweis Datenbank:** Im **Free Plan** gibt es keine dauerhafte Festplatte. Für echte Produktion später einen **Disk** (kostenpflichtig) oder Railway mit Volume nutzen. Zum Testen reicht Free.

5. **Create Web Service** → Build läuft 5–10 Minuten

### 3. URL eintragen

Nach dem Deploy zeigt Render eine URL, z. B.:

`https://baupass-xxxx.onrender.com`

Diese URL bei Render unter **Environment** setzen:

- `PUBLIC_BASE_URL` = `https://baupass-xxxx.onrender.com` (ohne Slash am Ende)

→ **Save** → Service startet neu.

### 4. Testen

- Admin: `https://IHRE-URL.onrender.com/`
- Mitarbeiter: `https://IHRE-URL.onrender.com/worker.html?view=card`
- Health: `https://IHRE-URL.onrender.com/api/health`

Build-Tag prüfen: `https://IHRE-URL.onrender.com/worker-build.json` → sollte `20260516i` zeigen.

### 5. Updates hochladen

Code auf GitHub pushen (`main`) → Render baut automatisch neu.

Ohne GitHub: ZIP des Ordners `baustelle` ist bei Render nicht vorgesehen – dann GitHub einmal verbinden oder Docker-Weg nutzen (`docs/alternative-deploy-wege.md`).

---

## Alternative: Nur testen (kostenlos, PC muss laufen)

```powershell
cd C:\Users\u4363\Desktop\baustelle
powershell -ExecutionPolicy Bypass -File .\deploy\start-lokal.ps1
```

Öffentlich erreichbar (Test): https://ngrok.com → `ngrok http 8000`

---

## Was Sie nicht brauchen

- Railway CLI / Token
- Bezahlung (Free Plan reicht zum Start)
- Eigenen Server verwalten (bei Render)

---

## Wenn Render „Build failed“

Build Log lesen. Häufig:

- Falscher Build-Befehl → muss `pip install -r backend/requirements.txt` sein
- `render.yaml` im Repo-Root liegt bereits korrekt vor
