# BauPass Control

Enterprise-Plattform fuer digitale Identitaet, Zutrittskontrolle, Workforce, Compliance, Dokumente und Reporting — mandantenfaehig (Bau, Industrie, Logistik, Luftfahrt, Sicherheit, oeffentlicher Sektor, Behoerden).

## Enthaltene Funktionen

- Login-Overlay mit Rollen fuer Super-Admin, Firmen-Admin und Drehkreuz-Terminal
- Firmenverwaltung fuer mehrere Baufirmen als Vermietungs- oder SaaS-Grundlage
- Je Hauptfirma koennen mehrere Subunternehmen (Nachunternehmer) angelegt und Mitarbeitern zugeordnet werden
- Mitarbeitererfassung mit Vorname, Nachname, Rentenversicherungsnummer, Funktion, Baustelle, Gueltigkeit und Status
- Kameraaufnahme direkt im Browser und Speicherung des Fotos im lokalen Browser-Speicher
- Digitaler Ausweis mit Badge-ID und echtem QR-Code-Bild
- Check-in und Check-out fuer Drehkreuz-Szenarien mit Zutrittsprotokoll
- Zutrittsjournal mit Datum/Uhrzeit, Richtung und Drehkreuz inkl. Filter und CSV-Export
- Pförtner-Live-Ansicht zeigt beim Ein- und Austritt sofort Mitarbeiterdaten (Foto, Name, Firma, Zeit, Drehkreuz)
- Akustisches Signal und 2-Sekunden Vollbild-Hinweis bei Ein- und Austritt (mit Website-Logo)
- Tagesbericht pro Drehkreuz (Eintritte, Austritte, letzte Buchung) fuer Firmenansicht
- Stunden-Auswertung fuer Eintritt/Austritt (00:00-23:00) im Zutrittsbereich
- Warnliste fuer offene Eintritte (letzte Buchung ist Check-in ohne Check-out)
- Ampel-Warnstufen fuer offene Eintritte (gruen/gelb/rot nach Offen-Dauer)
- Automatische Tagesabschluss-Pruefung ab 18:00 mit Hinweis auf offene Eintritte
- Tagesabschluss-Quittierung mit Kommentar und Audit-Log
- Druckbarer Tagesreport (Browser-Print, als PDF speicherbar)
- Rechnungsdruck mit Firmenlogo und eigenem Design (Farben, Branding)
- Rechnungsversand per E-Mail mit SMTP (inkl. Versandstatus und Fehleranzeige)
- Das Rechnungslogo wird gleichzeitig als Website-Logo in der Oberfläche verwendet
- Aus dem gleichen Logo wird automatisch auch das Browser-Tab-Icon (Favicon) erzeugt
- Optionaler Ein-Klick-Import für das mitgelieferte BauKometra Branding
- Zusätzliches alternatives BauKometra Preset (zweiter Ein-Klick-Import)
- Super-Admin-Bereich fuer Plattformname, Betreiber, Vermietungsmodell und zukuenftigen Drehkreuz-API-Endpunkt
- Rollenbasierte Sichtbarkeit: Firmen-Admins sehen nur ihre Firma, Drehkreuz-Login bekommt nur Zutrittsfunktionen
- Bearbeiten und Loeschen von Mitarbeitern sowie Firmenstatus-Steuerung
- Soft-Delete und Wiederherstellung fuer Mitarbeiter und Firmen
- Passwortwechsel im Adminbereich
- 2FA (TOTP) fuer den Super-Admin inkl. QR-Setup
- Audit-Log mit Filterfunktion und CSV-Export
- Mitarbeiter-App als installierbare Web-App unter `/worker.html` mit digitalem Ausweis
- Datenexport als JSON fuer Backups, Nachweise oder spaetere Migration in ein Backend

## So startest du die Plattform lokal

1. Python 3.11+ installieren (falls noch nicht vorhanden).
2. Im Projektordner eine virtuelle Umgebung erstellen und aktivieren.
3. Abhaengigkeiten installieren: `pip install -r backend/requirements.txt`.
4. Server starten: `python backend/server.py`.
5. Im Browser `http://127.0.0.1:8000` oeffnen.
6. Mit einem Demo-Zugang anmelden und optional auf "Demo-Daten laden" klicken.

## API-Notizen (neu)

- `GET /api/compliance/expiring-docs?days=30&limit=150`
	- Rollen: `superadmin`, `company-admin`
	- Liefert bald ablaufende Pflichtdokumente mit Feldern wie `workerName`, `companyName`, `docType`, `expiryDate`, `daysLeft`, `status` (`expired`, `today`, `upcoming`).
	- `days` ist serverseitig auf `1..180` begrenzt, `limit` auf `1..500`.

- `GET /api/access-logs/day-close-check`
	- Fuehrt weiterhin die Tagesabschluss-Pruefung aus.
	- Wenn nach 18:00 offene Eintritte vorhanden sind, werden Push-Erinnerungen dedupliziert pro Worker/Tag versendet.

## Produktivbetrieb (Windows + Reverse Proxy)

1. Abhaengigkeiten installieren: `pip install -r backend/requirements.txt`
2. Backend nur intern starten, z. B. mit `HOST=127.0.0.1`, `PORT=8000` und `python backend/entrypoint.py --mode prod`
   - Der gemeinsame Entrypoint verwendet lokal `--mode dev` und auf Railway `--mode prod`.
3. Im Reverse Proxy eine echte HTTPS-Domain davor setzen, Vorlage: `deploy/nginx.conf.example`
4. Backend-Linkbasis setzen: `PUBLIC_BASE_URL=https://baupass.example.com`
5. Gate-Reader absichern: `BAUPASS_GATE_API_KEY=<starkes-geheimes-token>`
6. Recovery absichern: `BAUPASS_RECOVERY_SECRET=<langes-notfall-secret>`
7. Optional Recovery-Benutzer setzen: `BAUPASS_RECOVERY_USERNAME=superadmin`
8. Optional als Windows-Task/Dienst installieren: `deploy/windows-service-install.ps1`

Konkreter Ablauf mit echter Domain:

1. DNS setzen: `baupass.example.com` muss auf den oeffentlichen Server zeigen.
2. Backend lokal auf dem Windows-Host starten:

```powershell
$env:HOST = "127.0.0.1"
$env:PORT = "8000"
$env:PUBLIC_BASE_URL = "https://baupass.example.com"
$env:BAUPASS_GATE_API_KEY = "ein-langes-gate-secret"
$env:BAUPASS_RECOVERY_SECRET = "ein-langes-recovery-secret"
python backend/entrypoint.py --mode prod
```

Beim Start gibt der gemeinsame Entrypoint Runtime-Warnungen aus, z. B. fuer fehlende Secrets, fehlende `PUBLIC_BASE_URL` oder Demo-Passwoerter (`1234`) auf Admin-/Terminal-Konten.

## Render Deploy

1. Repository direkt in Render als `Web Service` verbinden.
2. Render kann jetzt die Root-Dateien `requirements.txt` und `render.yaml` verwenden.
3. Start-Command ist `python backend/entrypoint.py --mode prod`.
4. Die App bindet standardmaessig an `0.0.0.0` und nutzt `PORT` von Render.
5. Nach dem Deploy sollte `https://baupass-backend.onrender.com/api/health` `{"status":"ok"...}` liefern.

Wenn im Render-Dashboard weiter `Failed deploy` steht, sind die ersten Stellen zum Pruefen:

- Build Log: Python-Pakete konnten nicht installiert werden
- Runtime Log: Startfehler beim Import oder Port-Binding
- Environment: falscher Start-Command oder fehlende `PORT`-Weitergabe

## Railway Deploy (mit GitHub – empfohlen)

Repository: **https://github.com/baukometra10/baupass-backend**

Ausfuehrliche Anleitung: **`docs/github-railway.md`**

Kurzablauf:

1. Code pushen: `.\deploy\github-push.ps1` (Konto **baukometra10**, Token mit `repo`)
2. Railway → **New Project** → **Deploy from GitHub repo** → `baupass-backend`, Branch `main`
3. Volume **`/data`** mounten, Variable **`PUBLIC_BASE_URL`** = Railway-Domain
4. Pruefen: `https://<deine-railway-domain>/api/health`

Bei jedem weiteren Update: `git commit` + `.\deploy\github-push.ps1` → Railway deployt automatisch.

Fuer Recovery und Gate-Reader in Railway zusaetzlich setzen:

- `BAUPASS_GATE_API_KEY`
- `BAUPASS_RECOVERY_SECRET`
- optional `BAUPASS_RECOVERY_USERNAME`

3. Oder als Autostart-Task installieren:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows-service-install.ps1 -HostAddress "127.0.0.1" -Port 8000 -PublicBaseUrl "https://baupass.example.com"
```

4. Nginx auf dem Reverse-Proxy-Server installieren und die Vorlage aus `deploy/nginx.conf.example` aktivieren.
5. `PUBLIC_BASE_URL` muss gesetzt sein, damit Worker-Links, QR-Codes und externe URLs korrekt erzeugt werden.
6. Zertifikat mit Let's Encrypt ausstellen, z. B. unter Ubuntu:

```bash
sudo apt update
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d baupass.example.com
```

6. Danach pruefen:

```bash
curl -I https://baupass.example.com/api/health
```

Fuer den vollstaendigen Runtime-Check als Superadmin nach Login:

```bash
curl https://baupass.example.com/api/system/runtime-check \
	-H "Cookie: baupass_session=<deine-session>"
```

Fuer den Notfall-Passwortreset ohne bestehende Session:

```bash
curl -X POST https://baupass.example.com/api/system/recover-admin \
	-H "Content-Type: application/json" \
	-d '{"recoverySecret":"<recovery-secret>","username":"superadmin","newPassword":"NeuesSicheresPasswort1"}'
```

Der Recovery-Endpoint setzt das Passwort neu, loescht aktive Sessions des Zielkontos und entfernt Login-Sperren fuer den Benutzernamen.

7. Admin-Oberflaeche neu ueber `https://baupass.example.com` oeffnen und einen neuen Mitarbeiter-QR erzeugen.

Wichtig fuer echte Handy-Scans:

- Der QR-Code muss auf eine oeffentlich oder im LAN erreichbare `https://`-Adresse zeigen.
- Hinter Nginx/Apache muessen `X-Forwarded-Proto` und `Host` sauber gesetzt sein, damit das Backend wieder `https://...`-Links erzeugt.
- Ohne echte Domain und gueltiges Zertifikat zeigt iPhone/Safari je nach Einstellung weiterhin Warnungen oder blockiert den Aufruf.

Beispiel unter Windows PowerShell fuer den internen Backend-Start hinter Nginx:

```powershell
$env:HOST = "127.0.0.1"
$env:PORT = "8000"
$env:PUBLIC_BASE_URL = "https://baupass.example.com"
python backend/entrypoint.py --mode prod
```

## Demo-Zugaenge




## Mitarbeiter-App (Hybrid / Flutter)

- Admin oeffnet die Mitarbeiterliste und klickt bei einer Person auf `App-Link`.
- Der erzeugte Link wird in die Zwischenablage kopiert und kann per Messenger/E-Mail gesendet werden.
- Mitarbeiter oeffnet den Link, der Zugang wird einmalig aktiviert, danach bleibt die Sitzung lokal gespeichert.
- Auf Mobilgeraeten kann die Seite als App installiert werden ("Zum Startbildschirm").
- Direkter Einstieg lokal: `http://127.0.0.1:8000/worker.html`
- Direkter Einstieg produktiv: `https://deine-domain.tld/worker.html`

## Kamera-/Foto-Regression-Checkliste

Bei Änderungen an der Fotoaufnahme bitte diese Punkte jedes Mal kurz prüfen:

- Buttons und Input in der Admin-Maske sind gebunden: `#startCameraButton`, `#capturePhotoButton`, `#uploadPhotoButton`, `#photoFileInput`.
- Klick auf "Kamera starten" zeigt Livebild oder einen klaren Fehlertext mit Diagnosecode in eckigen Klammern.
- Klick auf "Foto aufnehmen" erstellt ein Bild und aktualisiert die Vorschau.
- Klick auf "Foto hochladen" öffnet den Dateidialog bzw. mobil die Kamera/Galerie.
- Worker-App-Fotooverlay funktioniert ebenfalls inkl. Fallback auf Dateiauswahl.

Aktuelle Kamera-Diagnosecodes (Support):

- `CAM-HTTPS`: unsicherer Kontext, HTTPS fehlt.
- `CAM-PERM`: Kamerazugriff wurde verweigert/blockiert.
- `CAM-NODEVICE`: kein Kameragerät verfügbar.
- `CAM-INUSE`: Kamera wird bereits von anderer App/Tab verwendet.
- `CAM-CONSTRAINT`: angeforderte Kamera-Constraints nicht erfüllbar.
- `CAM-API`: Browser bietet keine nutzbare Camera-API/Fallback.
- `CAM-START`: allgemeiner Startfehler (siehe Reason-Text).

## Enterprise Backup und Restore-Check

Fuer produktive Abnahme ist jetzt ein technisch pruefbarer Backup/Restore-Flow enthalten:

- Backup-Tool: backend/ops/db_backup.py
- Backup-Wrapper: scripts/run_backup.ps1
- Restore-Verify-Wrapper: scripts/verify_backup_restore.ps1

Manueller Backup-Lauf:

```powershell
python backend/ops/db_backup.py backup
```

Manueller Restore-Verifikationstest:

```powershell
python backend/ops/db_backup.py verify-restore
```

Standard-Ablage:

- Datenbank-Backups: backend/backups/sqlite
- Restore-Checks: backend/backups/sqlite/restore-check

Retention (Standard 30 Tage) ueber ENV steuerbar:

```powershell
$env:BAUPASS_DB_BACKUP_RETENTION_DAYS = "30"
```

Vollstaendige Betriebsanleitung und Task-Scheduler-Beispiele:

- docs/enterprise-backup-restore-runbook.md

## Enterprise Structured Logging und Correlation IDs

Das Backend schreibt jetzt strukturierte JSON-Logs pro Request und pro unhandled Exception.

Wichtige Felder:

- `event` (z. B. `http_request_completed`, `http_request_exception`)
- `requestId` (aus `X-Request-Id`/`X-Correlation-Id` oder automatisch erzeugt)
- `method`, `path`, `status`, `durationMs`, `remoteAddr`, `userAgent`

Jede Response enthaelt den Header `X-Request-Id`, damit API-Clients, Reverse-Proxy und Support-Tickets denselben Request eindeutig verfolgen koennen.

Ein-/Ausschalten ueber ENV (Standard aktiviert):

```powershell
$env:BAUPASS_STRUCTURED_LOGS = "1"
```

## Rollenmodell

- Super-Admin: volle Systemkontrolle, Firmen anlegen, Plattform konfigurieren, alle Daten sehen
- Firmen-Admin: Mitarbeiter und Zutritte nur fuer die eigene Baufirma verwalten
- Drehkreuz-Terminal: schneller Zutrittsmodus fuer Check-in und Check-out vor Ort

Hinweis: Firmen sehen im Zutrittsjournal nur die Eintraege ihrer eigenen Mitarbeiter.

## Uebergabe an eine Baufirma (mandantensicher)

1. Als Super-Admin anmelden.
2. Im Adminbereich die Baufirma anlegen (es wird automatisch ein Firmen-Admin erzeugt).
3. Zugangsdaten nur an diese Firma geben (Benutzername + Startpasswort).
4. Firma weist ihre eigenen Mitarbeiter und optional Subunternehmen zu.
5. Optional zusaetzlichen Drehkreuz-Account nur fuer diese Firma nutzen.

Wichtig:
- Firmen-Admins sehen nur Daten ihrer eigenen Firma.
- Drehkreuz-Accounts sehen nur Zutrittsfunktionen und ebenfalls nur den eigenen Firmenbereich.
- Super-Admin bleibt der einzige globale Zugriff.
- Optional pro Firma eigene Zugangsdomain setzen (Feld "Firmen-Zugangsdomain").
- Wenn "Firmen-Domain erzwingen" aktiv ist, funktionieren Firmen-Logins nur auf ihrer eigenen Domain.
- Optional Admin-IP-Whitelist setzen, damit Admin-Zugriff nur aus erlaubten IP-Bereichen moeglich ist.

## Architektur des MVP

- Frontend: reines HTML, CSS und JavaScript ohne Build-Schritt
- Backend: Flask REST API in [backend/server.py](backend/server.py)
- Datenbank: SQLite in [backend/baupass.db](backend/baupass.db) (wird beim Start automatisch erstellt)
- Authentifizierung: passwort-gehashte Benutzerkonten und serverseitige Sessions mit Ablaufzeit
- Sicherheitsfunktionen: Passwortwechsel, 2FA (Super-Admin), Audit-Logging
- Kamera: `navigator.mediaDevices.getUserMedia()`
- Ausweislogik: Badge-ID pro Mitarbeiter, echte QR-Code-Erzeugung im Frontend
- Zugangskontrolle: API-Endpunkte fuer Check-in/Check-out und Export

## Sinnvolle naechste Ausbaustufen

1. Node.js oder .NET Backend mit echter Datenbank wie PostgreSQL oder SQL Server anbinden.
2. Passwort-Reset-Flow per E-Mail oder SMS fuer Firmen-Admins einbauen.
3. Scanner-Anbindung und Hardware-Webhook fuer reale Drehkreuze erweitern.
4. Hardware-API fuer Drehkreuz, Kartenleser oder Terminal anbinden.
5. PDF-Ausweise, Archivierung, Audit-Log und DSGVO-konforme Datenloeschung ergaenzen.
6. Abrechnung pro Firma, Baustelle oder Mitarbeiter fuer dein Vermietungsmodell einbauen.

## Wichtiger Hinweis

Der aktuelle Stand ist bewusst ohne Node.js umgesetzt und nutzt Python/Flask als Backend. Fuer den produktiven Einsatz solltest du als naechstes HTTPS erzwingen, Session-Store zentralisieren und ein professionelles Identity-Management anbinden.
# baupass-backend
