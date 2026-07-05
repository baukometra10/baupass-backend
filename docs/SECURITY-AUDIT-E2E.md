# SUPPIX E2E Security Audit Checklist

Stand: 2026-07-05 — Phase 1–4 Härtung implementiert.

## Automatisierte Tests

- `backend/tests/test_e2e_identity_routes.py` — Public-Key-API, Private-Key-Ablehnung
- `backend/tests/test_e2e_policy_enforcement.py` — Erzwungenes E2E für Chat-Nachrichten

```bash
pytest backend/tests/test_e2e_identity_routes.py backend/tests/test_e2e_policy_enforcement.py
```

## Manuelle Pen-Test-Punkte

### API
- [ ] `PUT /api/e2e/identity/me` mit `privateKey` → 403
- [ ] Chat-POST ohne E2E-Envelope → 400 `e2e_required`
- [ ] Attachment ohne `e2e_meta` → 400 `e2e_attachment_required`
- [ ] Leave-Note Klartext → 400 `e2e_required_note`
- [ ] Contract `final_text` Klartext → 400 `e2e_required_final_text`

### Client
- [ ] Private Keys nicht in Network-Tab / Logs
- [ ] XSS kann IndexedDB/Secure Storage auslesen → CSP prüfen
- [ ] Gerätewechsel: Recovery-Phrase exportieren/importieren
- [ ] Key-Rotation: alte Nachrichten via Archive-Keys lesbar

### Betrieb
- [ ] `BAUPASS_E2E_CHAT_REQUIRED=1` (Default)
- [ ] `BAUPASS_E2E_ATTACHMENTS_REQUIRED=1` (Default)
- [ ] `BAUPASS_E2E_SENSITIVE_REQUIRED=1` (Default)
- [ ] DB-Backup enthält nur Ciphertext
- [ ] Push/Email ohne Klartext-Inhalt

## Bekannte Grenzen (kein „100%“)

- Metadaten (Thread, Zeit, Sender) bleiben serverlesbar
- Kompromittiertes Endgerät = Keys lesbar (Phishing/XSS/Malware)
- Admin-PDF-Generierung aus Verträgen kann Entschlüsselung am Client erfordern
- Externer Pen-Test empfohlen vor regulierten Rollouts
