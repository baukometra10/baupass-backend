# Android AAB — Keystore & GitHub Secrets

Ziel: signiertes App Bundle für Google Play Internal Testing über  
**Actions → Build worker Android AAB** (`.github/workflows/flutter-worker-aab.yml`).

Ohne diese Secrets skippt der Workflow den Build (APK-Workflow bleibt nutzbar).

## 1. Upload-Keystore einmalig erzeugen (Windows)

In PowerShell (Java `keytool` aus JDK 17):

```powershell
cd $env:USERPROFILE\Downloads
keytool -genkey -v `
  -keystore baupass-upload.jks `
  -keyalg RSA -keysize 2048 -validity 10000 `
  -alias baupass_upload `
  -storepass "HIER_STORE_PASS" `
  -keypass "HIER_KEY_PASS" `
  -dname "CN=Baupass Worker, OU=Mobile, O=YourCompany, L=City, C=DE"
```

- **Datei** `baupass-upload.jks` und Passwörter sicher ablegen (Password-Manager / Firmen-Vault).
- Verlust = neuer Upload-Key + Play Console Reset — nicht in Git committen.

Lokal testen (optional):

```powershell
# mobile/android/key.properties (gitignored — lokal anlegen)
# storePassword=...
# keyPassword=...
# keyAlias=baupass_upload
# storeFile=C:/Users/YOU/Downloads/baupass-upload.jks

cd mobile
flutter build appbundle --release --dart-define=BAUPASS_API_URL=https://YOUR-BACKEND
```

`key.properties` und `*.jks` gehören **nicht** ins Repo.

## 2. Base64 für GitHub

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:USERPROFILE\Downloads\baupass-upload.jks")) |
  Set-Clipboard
```

Das Base64-String in die Zwischenablage — als Secret einfügen.

## 3. GitHub Repository Secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Wert |
|--------|------|
| `ANDROID_KEYSTORE_BASE64` | gesamter Base64-String der `.jks` |
| `ANDROID_KEYSTORE_PASSWORD` | storePassword |
| `ANDROID_KEY_ALIAS` | z. B. `baupass_upload` |
| `ANDROID_KEY_PASSWORD` | keyPassword (oft = store) |

## 4. Workflow starten

1. **Actions → Build worker Android AAB → Run workflow**
2. Optional: `api_base_url` setzen (Default: Production Railway)
3. Artifact **`baupass-worker-aab`** herunterladen → in Play Console **Internal testing** hochladen

Bei fehlenden Secrets: Job Summary „Android AAB skipped“ — Secrets nachziehen und erneut laufen lassen.

## 5. Play App Signing

Beim ersten Upload Play App Signing aktivieren (Google hält den App-Signing-Key; ihr behaltet den Upload-Key = dieses Keystore).

## Siehe auch

- [android-play-tomorrow.md](./android-play-tomorrow.md)
- [app-store-play-store.md](./app-store-play-store.md)
- [store-listing-DE.md](./store-listing-DE.md)
