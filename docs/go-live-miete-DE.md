# WorkPass — Go-Live für Firmen-Miete (SaaS)

Kurz-Checkliste, damit ihr die Plattform an andere Bauunternehmen vermieten könnt.

## 1. Mandant & Pläne

- Pro Kunde eine **Firma** in WorkPass anlegen (`companies`).
- **Plan** setzen: `starter` | `professional` | `enterprise` (steuert Features).
- **Superadmin**: Firmen-Vorschau nutzen, um den Kundenplan zu testen.

## 2. Zugänge

| Rolle | Zugang |
|--------|--------|
| Betrieb / HR | WorkPass (`index.html`) oder Admin v2 |
| Baustelle / Pförtner | Turnstile-Login |
| Mitarbeiter | Worker-App (`emp-app.html`) + Badge/PIN |

## 3. Dokumente & Lohnabrechnung

1. **Dokumenten-E-Mail** (IMAP) in den Einstellungen konfigurieren.
2. Eingehende PDFs im Posteingang einem Mitarbeiter zuordnen.
3. Dokumenttyp **Lohnabrechnung** — Vorschlag per Stichwörter **und** PDF-Text (OCR/pypdf).
4. Mitarbeiter: **Dokumente** in der App, **Glocke** für Benachrichtigungen (Server + Push).

**DATEV**

- **DATEV-CSV** im Posteingang (Stunden + Abrechnungen).
- **DATEV verbinden** (OAuth): Railway-Env setzen:
  - `DATEV_CLIENT_ID`
  - `DATEV_CLIENT_SECRET`
  - `DATEV_REDIRECT_URI` → `https://<host>/api/integrations/datev/oauth/callback`
- Status: `GET /api/integrations/datev/status`

## 4. White-Label pro Firma

Unter **Firmen → Design speichern**: Portal-Titel, Akzentfarbe, Logo.

## 5. KI & Enterprise

- Plan **Professional+** für Enterprise-Navigation, Ops, Suppix AI.
- OpenAI/API-Key nur in Railway/Server-Umgebung.

## 6. Technischer Betrieb

- Deploy: Railway `baupass-production` (Git `main`).
- Cache-Busting: `?v=20260531b` nach Releases.
- Health: `GET /api/health`

## 7. Vertraglich / Support

- AV-Vertrag / DSGVO, Onboarding-Schulung, Worker-QR verteilen.
