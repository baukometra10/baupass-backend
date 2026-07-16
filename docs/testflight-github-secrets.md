# TestFlight — GitHub Secrets Schritt für Schritt

Diese Anleitung ergänzt [testflight-internal-distribution.md](./testflight-internal-distribution.md) und führt durch die Secrets für `.github/workflows/ios-testflight.yml`.

**Voraussetzungen:** Apple Developer Program, App in App Store Connect (`com.baupass.worker`), Distribution-Zertifikat + App-Store-Provisioning-Profile.

---

## 1. App Store Connect API Key

1. [App Store Connect](https://appstoreconnect.apple.com) → **Users and Access** → **Integrations** → **App Store Connect API**
2. **+** → Name z. B. `GitHub Actions TestFlight` → Rolle **App Manager** (oder Admin)
3. **Generate** → `.p8` herunterladen (nur einmal verfügbar)
4. Notieren: **Key ID** und **Issuer ID** (oben auf der API-Seite)

**GitHub Secrets:**

| Secret | Wert |
|--------|------|
| `APP_STORE_CONNECT_API_KEY_ID` | Key ID (z. B. `AB12CD34EF`) |
| `APP_STORE_CONNECT_ISSUER_ID` | Issuer UUID |
| `APP_STORE_CONNECT_API_KEY_P8` | Kompletter Inhalt der `.p8` inkl. `-----BEGIN PRIVATE KEY-----` |

---

## 2. Distribution Certificate (.p12)

**Auf dem Mac (Keychain):**

1. [developer.apple.com](https://developer.apple.com/account) → **Certificates** → **+** → **Apple Distribution**
2. CSR aus Keychain Assistant erstellen, Zertifikat herunterladen, doppelklicken
3. Keychain → **My Certificates** → `Apple Distribution: …` → Rechtsklick → **Export** → `.p12` + Passwort setzen

**Base64 encodieren:**

```bash
base64 -i YourDistCert.p12 | pbcopy
```

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\path\dist.p12")) | Set-Clipboard
```

**GitHub Secrets:**

| Secret | Wert |
|--------|------|
| `IOS_DISTRIBUTION_CERT_P12_BASE64` | Base64-String |
| `IOS_DISTRIBUTION_CERT_PASSWORD` | Export-Passwort |

---

## 3. Provisioning Profile (App Store)

1. **Profiles** → **+** → **App Store Connect** → App `com.baupass.worker` → Distribution-Cert wählen
2. `.mobileprovision` herunterladen
3. Base64 wie oben

| Secret | Wert |
|--------|------|
| `IOS_PROVISIONING_PROFILE_BASE64` | Base64 der `.mobileprovision` |

Optional:

| Secret | Wert |
|--------|------|
| `IOS_TEAM_ID` | Apple Team ID (10 Zeichen, unter Membership) |

---

## 4. Workflow starten

1. GitHub Repo → **Actions** → **iOS TestFlight** → **Run workflow**
2. Oder: Push nach `main` mit Änderungen unter `mobile/**`
3. Job **skipped**? → In der Job-Summary fehlt mindestens ein Secret (Workflow warnt pro fehlendem Namen)

**Erfolg:** Artifact `baupass-worker-ios-ipa` + Upload via `xcrun altool` → App Store Connect → **TestFlight** (Verarbeitung 5–30 Min.)

---

## 5. Nach dem Upload

1. App Store Connect → **TestFlight** → Build `0.1.12+33` (oder neuer) → **Internal Testing**
2. Tester hinzufügen (gleiches Team)
3. Öffentlichen Invite-Link kopieren → Railway:

```env
BAUPASS_TESTFLIGHT_URL=https://testflight.apple.com/join/XXXXXXXX
```

4. [chat-qa-testplan.md](./chat-qa-testplan.md) auf dem iPhone + Admin-Web durchgehen

---

## Fallback ohne Secrets

```bash
cd mobile
flutter pub get
flutter build ipa --release \
  --dart-define=BAUPASS_API_URL=https://baupass-production.up.railway.app
```

Upload `build/ios/ipa/*.ipa` mit **Transporter** (Mac) oder Xcode Organizer.

---

## Häufige Fehler

| Symptom | Lösung |
|---------|--------|
| Workflow skipped | Alle 6 Pflicht-Secrets prüfen |
| `altool` auth failed | `.p8` vollständig, Key ID/Issuer korrekt, API-Key nicht widerrufen |
| Code signing failed | Profile passt zu Bundle ID; `IOS_TEAM_ID` setzen |
| NFC capability | `Runner.entitlements` + Profile mit Core NFC (siehe Haupt-Doku) |
