# WorkPass Production Environment Variables

Vollständige Dokumentation aller erforderlichen und optionalen Umgebungsvariablen für den Produktionsbetrieb.

**Namenskonvention:** Kanonisches Präfix ist `SUPPIX_*`. Legacy `BAUPASS_*` wird beim Start gespiegelt (beide funktionieren). Plattformname in der UI: **WorkPass**. Betreiber/Firma: **Suppix AI**.

## ✅ Erforderliche Variablen (Startup-Blockierung)

Diese müssen vor dem Produktionsstart gesetzt sein oder der Server beendet sich mit Fehler.

### Authentifizierung & Sicherheit

| Variable | Beschreibung | Min. Länge | Beispiel |
|----------|-------------|-----------|---------|
| `BAUPASS_SECRET_KEY` | Flask Session Secret | 32 Zeichen | `secrets.token_hex(32)` |
| `BAUPASS_AUDIT_SIGNING_KEY` | Audit-Trail Signatur | 32 Zeichen | `secrets.token_hex(32)` |
| `BAUPASS_ENFORCE_HTTPS` | HTTPS Enforcement (Production must be `1` or `true`) | - | `1` |

### Datenbankverbindung

| Variable | Beschreibung | Standard | Beispiel |
|----------|-------------|---------|---------|
| `DATABASE_URL` | PostgreSQL Verbindung **ODER** | - | `postgresql://user:pass@host:5432/baupass` |
| `BAUPASS_ALLOW_SQLITE_PRODUCTION` | SQLite Fallback (Emergency nur) | `0` | `1` (mit Warnung) |

### Public URL (für Worker-App & externe Links)

**Mindestens eine muss gesetzt sein:**

| Variable | Priorität | Beispiel |
|----------|-----------|---------|
| `PUBLIC_BASE_URL` | 1️⃣ Erste Wahl | `https://baupass.example.com` |
| `RENDER_EXTERNAL_URL` | 2️⃣ Render.com | `https://baupass-production.onrender.com` |
| `RAILWAY_PUBLIC_DOMAIN` | 3️⃣ Railway.app | `https://baupass-production.up.railway.app` |

**URL-Anforderungen:**
- Muss gültige URL sein (mit Schema `https://` oder `http://`)
- `https://` erforderlich für Non-Localhost-Domains
- `http://localhost` oder `http://127.0.0.1` erlaubt für Dev/Testing

---

## 🔐 Sicherheits-Empfehlungen (mit Warnungen)

Nicht erforderlich, aber stark empfohlen für Sicherheit:

| Variable | Zweck | Standard | Empfehlung |
|----------|-------|---------|-----------|
| `BAUPASS_GATE_API_KEY` | Gate Tap API Authentifizierung | nicht gesetzt | Min. 32 Zeichen |
| `BAUPASS_GATE_ASYNC_INGEST` | Gate Tap: Accept (`202`) + RQ-Verarbeitung | `0` | Nur bei hohem Lastprofil; Sync bleibt Default |
| `BAUPASS_RECOVERY_SECRET` | Emergency Recovery Endpoint | nicht gesetzt | Min. 32 Zeichen |
| `BAUPASS_FIELD_ENCRYPTION_KEY` | Field-Level Dokument-Verschlüsselung | nicht gesetzt | Min. 32 Zeichen |
| `SENTRY_DSN` | Error Tracking & Monitoring | nicht gesetzt | Sentry URL |

---

## 📧 Email & SMTP

| Variable | Beschreibung | Standard | Beispiel |
|----------|-------------|---------|---------|
| `BAUPASS_IMAP_POLL_INTERVAL_SECONDS` | IMAP Polling Interval | `300` | `600` |
| `BAUPASS_SKIP_IMAP_POLL` | Skip IMAP auf Startup | `0` | `1` (für Readonly Replicas) |

---

## 🗄️ Datenbankoptionen

| Variable | Beschreibung | Default |
|----------|-------------|---------|
| `DB_POOL_MIN_SIZE` | Min. DB Connections | `2` |
| `DB_POOL_MAX_SIZE` | Max. DB Connections | `20` |
| `DB_POOL_TIMEOUT_SECONDS` | Connection Timeout | `10` |

**SQLite-specific:**
| Variable | Beschreibung | Default |
|----------|-------------|---------|
| `BAUPASS_DB_PATH` | SQLite DB Datei | `./backend/baupass.db` |

### Railway.app (SQLite + Volume)

Für Login auf Railway ohne PostgreSQL:

| Variable | Wert | Hinweis |
|----------|------|---------|
| `BAUPASS_PG_RUNTIME` | `0` | Kein PG-Schema-Check beim Login |
| `BAUPASS_DB_PATH` | `/data/baupass.db` | Pfad auf dem gemounteten Volume |
| Volume | Mount `/data` | Persistent — sonst leere DB bei jedem Deploy |

**Fehler «Datenbank-Schema ist unvollständig … SQLite-Prüfung fehlgeschlagen»:** Die Datei unter `BAUPASS_DB_PATH` fehlt oder ist leer (< 4 KB). Prüfen: Volume an Service gebunden, Env gesetzt, Redeploy, dann Deploy-Logs auf `[baupass] init_db` prüfen.

---

## 🚀 Startup-Verhalten

| Variable | Beschreibung | Default | Werte |
|----------|-------------|---------|-------|
| `BAUPASS_ENV` | Umgebung | `production` | `production`, `prod`, `testing`, `development` |
| `BAUPASS_OWNER_STEP_UP_ENFORCE` | Owner-OTP für Verträge/Exporte erzwingen | an (außer testing/dev) | `0`/`1` |
| `BAUPASS_OWNER_OTP_ALLOW_DEBUG` | OTP im API zurückgeben wenn SMS/Mail fehlt | an in testing/dev | `0`/`1` |
| `BREVO_API_KEY` | Brevo API (E-Mail + optional SMS) | - | `xkeysib-…` |
| `BREVO_SMS_SENDER` | Absendername für Brevo-SMS (max. 11 Zeichen) | `SUPPIX` | z.B. `SUPPIX` |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | SMS optional (Fallback neben Brevo) | - | Twilio |
| `SMTP_HOST` / `RESEND_API_KEY` | E-Mail alternativ zu Brevo | - | SMTP oder Resend |
| `BAUPASS_RUN_DUNNING_ON_BOOT` | Mahnung auf Startup | `0` | `1` oder `0` |
| `BAUPASS_SEED_DEMO_ENTERPRISE` | Demo-Daten auf Startup | `0` | `1` oder `0` |
| `BAUPASS_BACKUP_ON_BOOT` | DB-Backup vor Start | `1` | `1` oder `0` |
| `BAUPASS_ARCHIVE_ACCESS_LOGS_ON_BOOT` | Access-Logs archivieren | `0` | `1` oder `0` |

---

## 📊 Observability & Logging

| Variable | Beschreibung | Default | Werte |
|----------|-------------|---------|-------|
| `LOG_LEVEL` | Log-Level | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `BAUPASS_STRUCTURED_LOGS` | JSON-Structured Logs | `1` | `1` oder `0` |
| `BAUPASS_ENABLE_HSTS` | HSTS Header | nicht gesetzt | `1` |
| `BAUPASS_PLATFORM_ENABLED` | Prometheus Metrics | `1` | `1` oder `0` |

---

## 💾 Storage & Uploads

| Variable | Beschreibung | Default | Werte |
|----------|-------------|---------|-------|
| `UPLOAD_BACKEND` | Storage Backend | `local` | `local`, `s3` |
| `S3_BUCKET` | S3 Bucket Name | - | `my-bucket` |
| `S3_ENDPOINT_URL` | S3 Endpoint (MinIO etc.) | - | `https://minio.example.com` |
| `S3_ACCESS_KEY` | S3 Access Key | - | - |
| `S3_SECRET_KEY` | S3 Secret Key | - | - |

---

## 🖥️ Waitress Server Config

| Variable | Beschreibung | Default | Empfehlung |
|----------|-------------|---------|-----------|
| `HOST` | Binding Host | `0.0.0.0` | `0.0.0.0` |
| `PORT` | Binding Port | `8000` | `8000`, `8080` |
| `BAUPASS_WAITRESS_THREADS` | Worker Threads | `16` | `8`–`32` je CPU |
| `BAUPASS_WAITRESS_CONNECTION_LIMIT` | Max Connections | `400` | `200`–`1000` |
| `BAUPASS_WAITRESS_CHANNEL_TIMEOUT` | Channel Timeout (s) | `120` | `30`–`300` |
| `BAUPASS_WAITRESS_CLEANUP_INTERVAL` | Cleanup Interval (s) | `30` | `10`–`60` |
| `BAUPASS_WAITRESS_QUEUE_WARNINGS` | Log Queue Warnings | `0` | `1` (debug) |

---

## ✅ Validation auf Startup

Der Produktionsserver führt folgende Prüfungen durch:

1. **SECRET_KEY**: Min. 32 Zeichen, nicht leer
2. **DATABASE_URL**: PostgreSQL erforderlich, falls nicht `BAUPASS_ALLOW_SQLITE_PRODUCTION=1`
3. **AUDIT_SIGNING_KEY**: Min. 32 Zeichen
4. **PUBLIC_BASE_URL**: Gültige URL mit https:// (außer Localhost)
5. **BAUPASS_ENFORCE_HTTPS**: Muss `1` sein in Production

**Bei Fehler:** Server beendet sich mit `sys.exit(1)` und gibt Fehlermeldungen aus.

---

## 📝 Beispiel .env (Production)

```bash
# Required
BAUPASS_ENV=production
BAUPASS_SECRET_KEY=<64-char-hex-from-secrets.token_hex(32)>
BAUPASS_AUDIT_SIGNING_KEY=<64-char-hex>
DATABASE_URL=postgresql://user:password@db.example.com:5432/baupass
PUBLIC_BASE_URL=https://baupass.example.com
BAUPASS_ENFORCE_HTTPS=1

# Security (recommended)
BAUPASS_GATE_API_KEY=<32-char-minimum>
BAUPASS_RECOVERY_SECRET=<32-char-minimum>
SENTRY_DSN=https://key@sentry.io/project-id

# Server
HOST=0.0.0.0
PORT=8000
BAUPASS_WAITRESS_THREADS=24
BAUPASS_WAITRESS_CONNECTION_LIMIT=500

# Observability
LOG_LEVEL=INFO
BAUPASS_STRUCTURED_LOGS=1
BAUPASS_PLATFORM_ENABLED=1

# Startup
BAUPASS_RUN_DUNNING_ON_BOOT=0
BAUPASS_BACKUP_ON_BOOT=1
```

---

## 🔍 Debugging

**Um zu sehen, welche Variablen gesetzt sind:**
```bash
python -c "import os; [print(f'{k}={v[:10]}...' if len(str(v))>10 else f'{k}={v}') for k, v in sorted(os.environ.items()) if 'BAUPASS' in k or 'DATABASE' in k]"
```

**Produktionsvalidierung vor Start:**
```bash
python -c "from backend.app.config import ProductionConfig; ProductionConfig.validate(); print('✅ Config valid')"
```
