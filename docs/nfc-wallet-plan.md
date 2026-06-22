# NFC- und Wallet-Plan fuer WorkPass

## Zielbild

Der Mitarbeiter soll seinen Ausweis auf drei Wegen nutzen koennen:

1. Badge-ID plus PIN in der WorkPass-App
2. QR am Drehkreuz als Fallback
3. Echter Tap mit physischer Karte oder Wallet-Pass

## Wichtige Realitaet vorab

Ein echter Chip-Flow ist nicht dasselbe wie die heute gezeichnete Chip-Optik auf der Karte.

- Ein normales Web-Frontend im Browser kann physische NFC-Karten auf dem iPhone praktisch nicht frei auslesen.
- Apple Wallet und Google Wallet arbeiten ueber signierte Passes, nicht ueber beliebige Web-NFC-Zugriffe.
- Viele einfache RFID-/NFC-Karten liefern nur eine UID. Diese UID allein ist kein sicheres Login-Merkmal und sollte nie als einziges Geheimnis verwendet werden.

## Empfohlene Zielarchitektur

### Option A: Physische NFC-Karte fuer Drehkreuz und App getrennt

Empfehlung fuer den schnellen Start.

- Physische NFC-/RFID-Karte dient nur am Lesegeraet oder Drehkreuz.
- Mobile App bleibt bei Badge-ID plus PIN oder Link-Token.
- Drehkreuz-Reader sendet Karten-ID an das Backend.
- Backend mappt Karten-ID auf Mitarbeiter und prueft Status, Gueltigkeit, Sperre und Baustelle.

Vorteile:

- Schnell umsetzbar
- Robust mit guenstiger Hardware
- Kein Apple-/Google-Wallet-Programm noetig

### Option B: Apple Wallet / Google Wallet Pass

Empfehlung fuer das hochwertige Mobile-Erlebnis.

- Jeder Mitarbeiter bekommt einen signierten Wallet-Pass.
- Der Pass enthaelt sichtbare Daten, Foto/Branding und einen Barcode oder eine Wallet-kompatible NFC-Struktur.
- Check-in erfolgt ueber Wallet-Pass statt ueber Browserseite.
- Die WorkPass-App bleibt fuer Profil, Baustelle, Foto, Route und Updates da.

Vorteile:

- Sehr gutes User-Erlebnis
- Native Sperrbildschirm-/Wallet-Integration
- Kein manuelles Oeffnen der Web-App fuer jeden Scan

### Option C: Secure NFC-Karte mit Challenge-Response

Das ist die beste, aber aufwaendigste Variante.

- Karte mit sicherem Secure Element statt einfacher UID-Karte
- Leser fragt kryptografische Challenge an
- Karte signiert oder chiffriert die Antwort
- Backend validiert Antwort gegen hinterlegte Schluessel

Vorteile:

- Deutlich sicherer als UID-basierte Karten

Nachteile:

- Hoher Hardware-, Provisionierungs- und Integrationsaufwand

## Empfohlene Umsetzungsreihenfolge

### Phase 1: Jetzt

- Badge-ID plus PIN fuer App-Login aktivieren
- QR als Fallback behalten
- Karten-Login im Backend auditierbar machen

### Phase 2: Physische Karte am Eingang

- Reader-Hardware festlegen
- Karten-ID-Feld in `workers` erweitern, getrennt von `badge_id`
- Neues Backend-Endpoint fuer Reader anlegen, z. B. `/api/gates/tap`
- Reader authentifizieren, damit nicht jeder Client beliebige Karten-IDs schicken kann

### Phase 3: Wallet-Pass

- Apple Wallet PassKit und Google Wallet Objects evaluieren
- Pass-Generierung auf dem Backend bauen
- Revoke-/Update-Strategie festlegen
- Optional Push-/Pass-Update bei Sperrung oder Baustellenwechsel

## Technische Anforderungen fuer Phase 2

### Backend

- Neues Feld `physical_card_id` oder `nfc_card_uid`
- Optional separates Feld `wallet_pass_id`
- Audit-Log fuer Tap-Ereignisse
- Rate Limiting fuer Gate-Endpunkte
- Reader-Authentifizierung per API-Key oder mTLS

### Hardware

- USB- oder Netzwerk-Reader am Gate oder Drehkreuz
- Reader darf nicht nur Tastatur-Emulation machen, wenn echte Sicherheitspruefung gewuenscht ist
- Bevorzugt: Reader -> lokaler Gate-Service -> WorkPass-Backend

### Sicherheit

- UID nie unverschluesselt als alleiniges Geheimnis behandeln
- Kartenverlust braucht sofortige Sperrung
- Jeder Tap muss serverseitig gegen Status und Gueltigkeit geprueft werden

## Technische Anforderungen fuer Phase 3

### Apple Wallet

- Apple Developer Program
- Pass Type ID, Zertifikate und Signierung
- `.pkpass`-Erzeugung im Backend

### Google Wallet

- Google Wallet Objects API
- Issuer Account
- JWT- oder API-basierte Pass-Ausgabe

### Datenmodell

- `wallet_platform`
- `wallet_pass_id`
- `wallet_serial`
- `wallet_status`
- `wallet_last_pushed_at`

## Produktentscheidung, die jetzt getroffen werden sollte

Wenn ihr in den naechsten Wochen schnell live gehen wollt, ist diese Reihenfolge am sinnvollsten:

1. Badge-ID plus PIN fuer App-Login
2. Physische NFC-/RFID-Karte nur fuer Drehkreuz
3. Spaeter Apple Wallet / Google Wallet als Premium-Ausbau

## Offene Entscheidungen

1. Soll die physische Karte nur am Gate funktionieren oder auch direkt die App aktivieren?
2. Gibt es schon Reader-Hardware oder muessen wir die erst auswaehlen?
3. Wollt ihr eher guenstige RFID-Karten oder ein hochwertiges Wallet-/NFC-Erlebnis?
4. Soll Apple Wallet / Google Wallet nur anzeigen oder auch echten Zugang ausloesen?