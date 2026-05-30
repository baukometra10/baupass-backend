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
3. Dokumenttyp **Lohnabrechnung** (oder **Gehaltsabrechnung**) wählen.
4. Der Mitarbeiter sieht die Abrechnung unter **Dokumente** in der App, kann **PDF öffnen**, und erhält optional eine **Push-Benachrichtigung**.

Alternativ: Direkt-Upload am Mitarbeiterprofil (Dokumente → Upload).

## 4. KI & Enterprise

- Plan **Professional+** für Enterprise-Navigation, Ops, BauPass KI.
- OpenAI/API-Key nur in Railway/Server-Umgebung, nie im Frontend.
- Sprache: UI DE/EN/AR; Spracheingabe nutzt Browser-Sprache + UI-Sprache.

## 5. Technischer Betrieb

- Deploy: Railway `baupass-production` (Git `main`).
- Cache-Busting: `?v=20260530b` nach Releases.
- Health: `GET /api/health`
- Backups: DB + `DOCS_UPLOAD_DIR` regelmäßig sichern.

## 6. Vertraglich / Support

- SLA und Support-Kanal definieren (E-Mail/Telefon).
- AV-Vertrag / DSGVO: Auftragsverarbeitung, Speicherort EU.
- Onboarding: 1× Admin-Schulung, Worker-App QR/Link verteilen.

## Noch sinnvolle Erweiterungen (nach Go-Live)

- DATEV/Lohn-API statt manueller PDF-Zuordnung
- White-Label (Logo/Farben pro Firma) — teilweise über Branding-Einstellungen
- Mehrsprachige Worker-App (TR/PL/FR vollständig)
- Automatische Erkennung Lohn-PDF per OCR im Posteingang
