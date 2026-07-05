# E2E-Schlüssel — Anleitung für Mitarbeitende

Stand: 2026-07-05

## Was ist das?

Deine Nachrichten, Urlaubsnotizen und Dokumente sind **Ende-zu-Ende verschlüsselt**. Der Schlüssel zum Entschlüsseln liegt **nur auf deinem Gerät** — nicht auf dem Server.

## Neues Handy oder zweites Gerät

1. **Altes Gerät noch verfügbar?**
   - App öffnen → **Schnellzugriff** → unten **E2E-Sicherheit**
   - **QR exportieren** → QR-Text kopieren oder dem neuen Gerät zeigen
   - Auf neuem Gerät: einloggen → **QR importieren** → Text einfügen

2. **Nur Recovery-Phrase gesichert?**
   - Auf neuem Gerät einloggen → **Recovery-Phrase** eingeben (12 Wörter)
   - Danach **Schlüssel erneuern**, falls die App es anbietet

3. **Weder altes Gerät noch Recovery-Phrase?**
   - Alte verschlüsselte Inhalte sind **nicht wiederherstellbar** (by design)
   - App erzeugt neue Schlüssel beim nächsten Login
   - Admin/Firma kann weiter chatten — alte Nachrichten erscheinen als „Entschlüsselung fehlgeschlagen“

## Recovery-Phrase sichern

- Einmal unter **Schnellzugriff → Recovery-Phrase** anzeigen lassen
- Die 12 Wörter **offline** notieren (Papier, Tresor — nicht per E-Mail/WhatsApp)
- Niemals an Kollegen oder „Support“ senden — niemand außer dir braucht sie

## Schlüssel erneuern (Rotation)

- Nach Verdacht auf Gerätezugriff: **Schlüssel erneuern**
- Neue Nachrichten nutzen den neuen Schlüssel
- Alte Nachrichten bleiben mit archivierten Schlüsseln lesbar (wenn noch auf dem Gerät)

## Was du nicht tun solltest

- Private Keys oder Recovery-Phrase in Chats, E-Mails oder Tickets posten
- Screenshots der Recovery-Phrase in der Cloud speichern
- Auf fremden oder öffentlichen PCs einloggen ohne danach Schlüssel zu rotieren

## Hilfe

Technische Probleme (App startet nicht, Login): an **Firmen-Admin** oder Suppix Support.

Inhaltliche Entschlüsselungsfehler nach Gerätewechsel ohne Backup: kein Server-Reset möglich — neuer Schlüssel + ggf. Admin bittet um erneute Zustellung sensibler Dokumente.

Siehe auch: [`docs/E2E-VERSCHLUESSELUNG.md`](E2E-VERSCHLUESSELUNG.md)
