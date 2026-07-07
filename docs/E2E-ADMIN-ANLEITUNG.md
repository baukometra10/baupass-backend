# E2E-Sicherheit — Admin-Kurzanleitung

## Was passiert automatisch?

Nach dem Login erzeugt der Browser ein **Schlüsselpaar** (X25519).  
**Nur der Public Key** wird an den Server gesendet. Der **Private Key bleibt auf Ihrem Gerät** (IndexedDB, verschlüsselt).

Damit funktionieren ohne Extra-Klicks:

- Chat (lesen/schreiben)
- Urlaubsnotizen (entschlüsselt in der Admin-Ansicht)
- Dokument-Upload/Download
- Vertragstexte in `contracts.html`

Server-Variablen (`BAUPASS_E2E_*=1`) erzwingen: **ohne Verschlüsselung speichert der Server nichts**.

## Wo finde ich das Panel?

**Admin-Platform** → Konto / Passwort-Bereich → unter **2FA** → Karte **E2E-Sicherheit**

**Mitarbeiter-App** → **Schnellzugriff** → unten **E2E-Sicherheit**

Die Sprache folgt der UI-Sprachwahl (DE, EN, AR, TR, FR, ES, IT, PL).

## Buttons im Panel

| Button | Zweck |
|--------|--------|
| **Geräte-PIN setzen** | Extra-Sperre: Master-Key nur nach PIN (310.000 PBKDF2-Iterationen) |
| **PIN entsperren** | Pro Browser-Sitzung einmal nötig, wenn PIN aktiv |
| **Recovery-Phrase** | 12 Wörter — **offline sichern** (Gerätewechsel) |
| **Schlüssel rotieren** | Neues Schlüsselpaar; alte Nachrichten via Archiv-Schlüssel |
| **QR export/import** | Schlüssel auf zweites Gerät übertragen (5 Min. gültig) |

## Was der Server niemals sieht

- Private Keys
- Recovery-Phrase
- Geräte-PIN
- Klartext von Chat, Notizen, Verträgen, Dokumenten

## Was ein Angreifer trotzdem nicht lesen kann

| Angriff | Schutz |
|---------|--------|
| Server-/DB-Hack | Nur Ciphertext + Public Keys |
| Netzwerk-Mithören (HTTPS) | E2E zusätzlich |
| Private Key per API senden | Server antwortet **403** |

## Was technisch nicht 100 % ausgeschlossen ist

- **Malware oder XSS auf dem entsperrten Gerät** — solange die App läuft und die PIN eingegeben ist, kann Schadcode theoretisch im Browser lesen.
- **Phishing** (Recovery-Phrase oder PIN preisgeben)

**Empfehlung:** Geräte-PIN setzen, Recovery-Phrase auf Papier, nach Verdacht **Schlüssel rotieren**.

Siehe auch: [`E2E-VERSCHLUESSELUNG.md`](E2E-VERSCHLUESSELUNG.md), [`E2E-RECOVERY-MITARBEITER.md`](E2E-RECOVERY-MITARBEITER.md)
