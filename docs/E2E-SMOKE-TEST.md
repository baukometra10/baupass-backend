# E2E Smoke-Test (ca. 30 Min.)

Kurzcheckliste nach Deploy oder größeren E2E-Änderungen.

## Voraussetzungen

- Production oder Staging mit `BAUPASS_E2E_*=1` (Default)
- Ein Test-Mitarbeiter + Admin-Account derselben Firma
- Beide haben einmal die App geöffnet (Schlüssel erzeugt)

## Worker

| # | Schritt | Erwartung |
|---|---------|-----------|
| 1 | Login, Chat öffnen, Nachricht senden | Kein Fehler „e2e_keys_missing“ |
| 2 | Anhang senden (PDF/JPG) | Upload ok, Admin kann downloaden |
| 3 | Urlaubsantrag mit Notiz | Antrag 201, Notiz nicht Klartext in DB |
| 4 | Dokument herunterladen (falls vorhanden) | Datei öffnet sich korrekt |
| 5 | Schnellzugriff → Recovery-Phrase | 12 Wörter werden angezeigt |

## Admin

| # | Schritt | Erwartung |
|---|---------|-----------|
| 6 | Chat: Worker-Nachricht lesen | Klartext sichtbar |
| 7 | Chat: Antwort senden | Worker sieht Klartext |
| 8 | Urlaubsanträge: Notiz lesen | Entschlüsselter Text (nicht JSON-Envelope) |
| 9 | Mitarbeiter-Dokument hochladen | 200, Worker-Download ok |
| 10 | Konto → E2E-Sicherheit | Recovery / Rotation / QR sichtbar |
| 11 | Vertrag speichern (contracts.html) | Speichern ok, Text nach Reload lesbar |

## API (optional, curl)

```bash
# Chat ohne Envelope → 400 e2e_required
# Leave mit Klartext-Note → 400 e2e_required_note
# Dokument ohne e2e_meta → 400 e2e_attachment_required
```

Automatisiert: `pytest backend/tests/test_e2e_*.py` (Python 3.11 empfohlen).

## Bei Fehlern

- Browser DevTools → Network: kein `privateKey` in Requests
- Admin/Worker einmal ausloggen, neu einloggen (Schlüssel registrieren)
- Public Keys: `GET /api/e2e/identity/me` (Worker) bzw. Admin-Variante

Siehe [`docs/SECURITY-AUDIT-E2E.md`](SECURITY-AUDIT-E2E.md) für Pen-Test-Punkte.
