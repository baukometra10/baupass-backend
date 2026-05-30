# BauPass — Go-Live für Firmen-Miete (SaaS)

Kurz-Checkliste, damit ihr die Plattform an andere Bauunternehmen vermieten könnt.

## 1. Mandant & Pläne

- Pro Kunde eine **Firma** in BauPass anlegen (`companies`).
- **Plan** setzen: `starter` | `professional` | `enterprise` (steuert Features).
- **Superadmin**: Firmen-Vorschau nutzen, um den Kundenplan zu testen.

## 2. Zugänge

| Rolle | Zugang |
|--------|--------|
| Betrieb / HR | Control Pass (`index.html`) oder Admin v2 |
| Baustelle / Pförtner | Turnstile-Login |
| Mitarbeiter | Worker-App (`emp-app.html`) + Badge/PIN |

## 3. Dokumente & Lohnabrechnung

1. **Dokumenten-E-Mail** (IMAP) in den Einstellungen konfigurieren.
2. Eingehende PDFs im Posteingang einem Mitarbeiter zuordnen.
3. Dokumenttyp **Lohnabrechnung** (oder **Gehaltsabrechnung**) wählen — der Posteingang schlägt den Typ bei DATEV-/Lohn-Stichwörtern automatisch vor.
4. Der Mitarbeiter sieht die Abrechnung unter **Dokumente** in der App, kann **PDF öffnen**, und erhält optional eine **Push-Benachrichtigung**.

Alternativ: Direkt-Upload am Mitarbeiterprofil (Dokumente → Upload).

**DATEV-Handoff:** Im Posteingang **DATEV-CSV** exportieren (`GET /api/documents/payroll/datev-export`) — Stunden/Check-ins + zugeordnete Abrechnungen pro Mitarbeiter.

## 4. White-Label pro Firma

Unter **Firmen → Design speichern**:

- **Portal-Titel** (ersetzt BauPass/ControlPass-Anzeige in der Worker-App)
- **Akzentfarbe** (CSS `--accent`)
- **Logo** (PNG/JPG/WebP, Data-URL)

Plan **Enterprise** für volles White-Label laut Feature-Matrix.

## 5. KI & Enterprise

- Plan **Professional+** für Enterprise-Navigation, Ops, BauPass KI.
- OpenAI/API-Key nur in Railway/Server-Umgebung, nie im Frontend.
- Sprache: UI DE/EN/AR; Spracheingabe nutzt Browser-Sprache + UI-Sprache.

## 6. Technischer Betrieb

- Deploy: Railway `baupass-production` (Git `main`).
- Cache-Busting: `?v=20260531a` nach Releases.
- Health: `GET /api/health`
- Backups: DB + `DOCS_UPLOAD_DIR` regelmäßig sichern.

## 7. Vertraglich / Support

- SLA und Support-Kanal definieren (E-Mail/Telefon).
- AV-Vertrag / DSGVO: Auftragsverarbeitung, Speicherort EU.
- Onboarding: 1× Admin-Schulung, Worker-App QR/Link verteilen.

## Noch sinnvolle Erweiterungen (nach Go-Live)

- DATEV LODAS Live-API (OAuth) statt CSV-Export
- OCR-Klassifikation für gescannte Lohn-PDFs ohne Stichwörter
- Mehrsprachige Worker-App (TR/PL/FR vollständig)
- Eigene Domain pro Mandant (`access_host`)
