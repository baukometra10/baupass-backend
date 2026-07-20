# Railway Wallet Setup (Apple + Google)

**Ziel:** Signing-Credentials auf Railway `web` / `production` setzen, ohne Secrets in Git.  
**Prod:** https://suppix-workpass-ai.up.railway.app  
**Voraussetzungen-Accounts:** [Apple](./apple-wallet-setup-guide.md) · [Google](./google-wallet-setup-guide.md)

Railway hat kein dauerhaftes `backend/wallet/` im Image. Deshalb:

| Plattform | Empfohlen auf Railway |
|-----------|------------------------|
| Apple     | `APPLE_CERT_BASE64` (+ optional Intermediate Base64) |
| Google    | `GOOGLE_SERVICE_ACCOUNT_JSON` (kompletter JSON inline) |

Datei-Pfade (`APPLE_CERT_PATH`, `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`) bleiben für lokale Dev.

---

## 1. Lokal vorbereiten (einmal)

### Apple
1. Pass Type ID + Team ID + `.p12` wie in `apple-wallet-setup-guide.md`
2. Intermediate: [Apple CA](https://www.apple.com/certificateauthority/) → WWDR
3. Ablage (nicht committen):
   - `backend/wallet/apple-passkit.p12`
   - `backend/wallet/apple-intermediate.cer`

### Google
1. Wallet API + Service Account + Issuer wie in `google-wallet-setup-guide.md`
2. Ablage: `backend/wallet/google-service-account.json`
3. `GOOGLE_ISSUER_ID` aus Google Pay / Wallet Business Console (nicht Project Number raten)

---

## 2. Variablen auf Railway setzen

### Variante A — Script (empfohlen)

```powershell
# Im Repo-Root, Railway CLI eingeloggt + Projekt gelinkt
powershell -ExecutionPolicy Bypass -File .\deploy\railway-wallet-setup.ps1
```

Das Script liest lokale Wallet-Dateien, encodiert Base64/JSON und setzt:

**Apple**
- `APPLE_TEAM_ID`
- `APPLE_PASS_TYPE_ID`
- `APPLE_CERT_PASSWORD`
- `APPLE_CERT_BASE64`
- `APPLE_INTERMEDIATE_CERT_BASE64` (wenn `.cer` vorhanden)

**Google**
- `GOOGLE_ISSUER_ID`
- `GOOGLE_PROJECT_ID`
- `GOOGLE_SERVICE_ACCOUNT_EMAIL`
- `GOOGLE_SERVICE_ACCOUNT_JSON`
- optional `GOOGLE_WALLET_CLASS_ID`

Dry-run:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\railway-wallet-setup.ps1 -DryRun
```

### Variante B — Dashboard

Service **web** → Variables:

```text
APPLE_TEAM_ID=...
APPLE_PASS_TYPE_ID=pass.example.workpass
APPLE_CERT_PASSWORD=...
APPLE_CERT_BASE64=<base64 des .p12>

GOOGLE_ISSUER_ID=...
GOOGLE_PROJECT_ID=...
GOOGLE_SERVICE_ACCOUNT_EMAIL=...@....iam.gserviceaccount.com
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
```

Base64 lokal erzeugen (PowerShell):

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("backend\wallet\apple-passkit.p12"))
```

---

## 3. Deploy & Verify

1. Nach Variable-Set: Redeploy `web` (Railway startet oft automatisch neu).
2. Als Superadmin: Admin → **Platform** → Wallet-Block (Apple/Google Status).
3. API: `GET /api/admin/wallet/runtime-status` (Auth) → `wallet.runtime.apple.ok` / `google.ok`.
4. Worker-App: „Zu Apple/Google Wallet“ — kein 503 `wallet_not_configured`.
5. iPhone: `.pkpass` öffnet Add-to-Wallet; Android: Save-URL öffnet Google Wallet.

---

## 4. Checkliste

- [ ] Apple Developer Pass Type ID + `.p12`
- [ ] Google Wallet Issuer + Service Account JSON
- [ ] Railway Variables gesetzt (Base64/JSON, nicht Git)
- [ ] Platform-Tab: beide Runtime grün
- [ ] Gerät: Pass installierbar; QR bleibt Fallback

## Sicherheit

- Nie `.p12` / Service-Account-JSON committen (`backend/wallet/` ist gitignored).
- Railway Variables = Secrets; nicht in Screenshots/Logs.
- Keys rotieren bei Verdacht; Pass Type neu ausstellen = neue Base64 setzen.
