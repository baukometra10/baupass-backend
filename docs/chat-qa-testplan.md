# Chat & Calls — QA-Testplan (Admin Web + Worker Flutter)

Vor Promotion auf **Internal TestFlight** oder nach größeren Chat-Releases (`chat39`/`chat40`, Build **0.1.12+33**).

**Geräte:** iPhone mit TestFlight-Build, Desktop-Browser (Chrome/Edge) für Admin v2 Chat.

**Tester:** 1 Admin-Account, 1 Worker mit aktivem Join/Login.

---

## A. Vorbereitung

- [ ] Backend erreichbar (`/api/health/live` = ok)
- [ ] Worker eingeloggt (Flutter **oder** PWA zum Vergleich)
- [ ] Admin in `/admin-v2/chat.html` eingeloggt, gleicher Worker-Thread offen
- [ ] Mikrofon + Benachrichtigungen erlaubt (Browser + iOS Settings)

---

## B. Sprachanrufe (WebRTC / CallKit)

| # | Schritt | Erwartung | ✓ |
|---|---------|-----------|---|
| B1 | Admin → 📞 auf offenen Thread | Overlay: Wählt/Klingelt, Timer läuft | |
| B2 | Worker nimmt an (Flutter/PWA) | Beidseitig Audio, Admin „Verbunden“ | |
| B3 | Admin legt auf | Overlay zu, beide Seiten beendet | |
| B4 | Worker ruft an → Admin lehnt ab | Admin: Abgelehnt (kein „Verpasst“ für Admin-Outbound-Miss) | |
| B5 | Admin ruft an, ~60s keine Annahme | Worker: Verpasst; Admin: **Nicht erreicht** (kein Missed-Bubble für Admin) | |
| B6 | iPhone gesperrt / App im Hintergrund, Worker ruft an | CallKit / Vollbild-Eingehend (nur native IPA) | |
| B7 | Lautsprecher / Stumm im Admin-Overlay | Ton an/aus, Pegelanzeige reagiert | |

---

## C. Chat — Text & Antworten

| # | Schritt | Erwartung | ✓ |
|---|---------|-----------|---|
| C1 | Worker sendet Text | Admin sieht Bubble, Thread-Liste aktualisiert | |
| C2 | Admin antwortet | Worker sieht Nachricht | |
| C3 | Long-Press → Antworten (Flutter) | Zitat-Leiste, Send mit Reply | |
| C4 | In-Chat-Suche (Admin + Flutter) | Treffer gefiltert | |

---

## D. Medien

| # | Schritt | Erwartung | ✓ |
|---|---------|-----------|---|
| D1 | Worker: Sprachnachricht | Admin hört inline (kein Download-Zwang) | |
| D2 | Flutter: Play/Pause in Bubble | Kein System-Mediaplayer übernimmt | |
| D3 | Admin: Foto senden | Worker: Bildvorschau (kein Audio-Player) | |
| D4 | Bild tippen | Vollbild / Galerie | |
| D5 | Standort teilen | Karten-Bubble, Maps-Link | |
| D6 | Medien-Galerie (Admin) | Fotos/Sprache/Dateien, Löschen entfernt Nachricht | |

---

## E. View-once Sprachnachricht

| # | Schritt | Erwartung | ✓ |
|---|---------|-----------|---|
| E1 | Sender: „Einmal anhören“ aktiv, Voice senden | Empfänger sieht View-once-Kennzeichnung | |
| E2 | Empfänger hört einmal zu Ende | Zweiter Play blockiert / „bereits gehört“ | |
| E3 | Gleicher Test Admin ↔ Flutter | Server 410 / lokaler Consume konsistent | |

---

## F. Pin / Stern (Nachricht)

| # | Schritt | Erwartung | ✓ |
|---|---------|-----------|---|
| F1 | Worker Web: Pin + Stern | Badges sichtbar, nach Reload noch da | |
| F2 | Flutter: Long-Press Anheften/Stern | Badges + Angeheftet-Leiste | |
| F3 | Admin: Pin/Stern gleiche Nachricht | Eigene Prefs (nicht cross-user) — nur eigener Account | |

---

## G. Benachrichtigungen

| # | Schritt | Erwartung | ✓ |
|---|---------|-----------|---|
| G1 | Admin auf Dashboard (nicht Chat), Worker schreibt | Browser-Notification + Ton (wenn erlaubt) | |
| G2 | Admin Push-Banner aktiviert | Status „aktiv“, erneuter Test G1 | |
| G3 | Worker FCM bei neuer Nachricht (App Hintergrund) | Push sichtbar | |

---

## H. Regression Kurz

| # | Schritt | Erwartung | ✓ |
|---|---------|-----------|---|
| H1 | E2E verschlüsselte Nachricht | Lesbar nach Entschlüsselung | |
| H2 | Offline Worker sendet (falls Queue aktiv) | Nach Reconnect zugestellt | |
| H3 | Thread-Filter Admin (Ungelesen/Angeheftet) | Listen stimmen | |

---

## Freigabe

| Rolle | Name | Datum | Build |
|-------|------|-------|-------|
| QA | | | 0.1.12+33 |
| Product | | | |

**Blocker dokumentieren:** Schritte-ID, Screenshot, Browser/iOS-Version, `Build`-Tag (Admin `chat40`, Worker SW).

---

Siehe auch: [testflight-internal-distribution.md](./testflight-internal-distribution.md), [testflight-github-secrets.md](./testflight-github-secrets.md)
