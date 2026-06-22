# Apple Developer Account & PassKit Setup Guide

**Goal:** Complete Apple Developer enrollment and generate PassKit credentials for signing wallet passes.

---

## Overview

To generate Apple Wallet (`.pkpass`) passes, you need:
1. **Apple Developer Account** ($99/year)
2. **Team ID** (identifies your organization)
3. **Pass Type ID** (identifies your pass type, e.g., `pass.baukometra.baupass`)
4. **Signing Certificate & Private Key** (cryptographically sign each pass)

---

## Step-by-Step Setup

### Step 1: Create Apple Developer Account

1. Go to https://developer.apple.com/
2. Click "Account" (top right) → "Sign In"
3. Use your Apple ID or create one
   - If creating new: Use company email (e.g., `admin@baukometra.de`)
4. Complete the enrollment process:
   - Accept legal agreements
   - Provide tax identification (if applicable)
   - Verify identity via email

**Cost:** $99/year for Individual or Organization membership

**Outcome:** Apple Developer account active, ready for Certificates & Identifiers.

---

### Step 2: Access Certificates, Identifiers & Profiles

1. Sign in to https://developer.apple.com/account/
2. Navigate to **"Certificates, Identifiers & Profiles"** (left sidebar)
3. You'll see sections:
   - Certificates
   - Identifiers
   - Profiles
   - Devices

---

### Step 3: Create a Pass Type ID

1. In **Identifiers** section:
   - Click **"Identifiers"** (left sidebar) → **"+" (top right)**
   - Select **"Pass Type IDs"** → Click **"Continue"**

2. Enter Pass Type ID details:
   - **Description:** "WorkPass Worker Badge" (or your company name)
   - **Identifier:** `pass.baukometra.baupass` 
     - Format: `pass.{reverse-domain}.{pass-type}`
     - Example: `pass.yourcompany.com.worker-badge`

3. Click **"Register"** → Confirm

**Outcome:** 
- Pass Type ID created: `pass.baukometra.baupass`
- This is your `PASS_TYPE_ID` environment variable

---

### Step 4: Generate Team ID

1. Go to **"Membership"** (top navigation, Account menu)
2. Look for **"Team ID"** (e.g., `ABCD1EF2GH`)
3. Note this value — it's required in all pass files

**Outcome:** 
- Team ID: `ABCD1EF2GH` (example)
- This is your `APPLE_TEAM_ID` environment variable

---

### Step 5: Create Signing Certificate

PassKit requires you to sign each `.pkpass` file with a certificate. Here's how:

#### 5a. Generate Certificate Signing Request (CSR)

1. **On your computer**, open **Keychain Access** (macOS) or **Certificate Manager** (Windows)
   - macOS: `/Applications/Utilities/Keychain\ Access.app`
   - Windows: Use OpenSSL or let Xcode handle it

2. **macOS Instructions:**
   - Keychain Access → Certificate Assistant → Request a Certificate from a CA
   - Email: `admin@baukometra.de`
   - Common Name: `WorkPass PassKit`
   - CA Email: Leave blank
   - Request: Saved to disk → Choose a location (e.g., Desktop)
   - **Save as:** `PassKitRequest.certSigningRequest`

3. **Windows Instructions (using OpenSSL):**
   ```powershell
   # If OpenSSL not installed, download from https://slproweb.com/products/Win32OpenSSL.html
   openssl req -new -keyout passkit-key.pem -out PassKitRequest.csr
   # Fill in prompts:
   # Common Name: WorkPass PassKit
   # Organization: Suppix Technologie UG (optional)
   ```

**Outcome:** CSR file saved (to be uploaded to Apple)

#### 5b. Upload CSR to Apple Developer

1. In **Certificates, Identifiers & Profiles**:
   - Go to **"Identifiers"** → Select your **Pass Type ID** → **"Edit"**
   - Under **"Certificates"**, click **"Create Certificate"**

2. Upload your CSR file:
   - Choose the CSR file you just created
   - Click **"Continue"** → **"Download"**

3. **Save the certificate:**
   - File: `pass.cer` (or similar)
   - **Keep this file safe** — needed for signing passes

**Outcome:** `.cer` file downloaded and saved

#### 5c. Import Certificate to Local Keystore

**macOS:**
1. Double-click the downloaded `.cer` file → Keychain Access opens automatically
2. Certificate now appears in Keychain under "Certificates"
3. Right-click → "Export" to get `.p12` file (see next step)

**Windows:**
1. Double-click the `.cer` file → Certificate Installation wizard
2. Store location: "Current User"
3. Certificate store: "Personal"
4. Click "Finish"

#### 5d. Export Private Key as `.p12` (PKCS#12 Format)

PassKit requires both the certificate and private key together in `.p12` format.

**macOS:**
1. Open **Keychain Access**
2. Find the certificate you just imported (search for "WorkPass PassKit")
3. Select it → Right-click → **"Export"**
4. Format: **"Personal Information Exchange (.p12)"**
5. Save as: `passkit-cert.p12`
6. Enter a password when prompted (remember this!)
7. Move file to: `backend/wallet/apple-passkit.p12`

**Windows:**
1. Open **Certificate Manager** (search "Manage certificates")
2. Find cert in "Personal" → "Certificates"
3. Right-click → **"Export"**
4. Next → **"Yes, export the private key"**
5. Format: **"Personal Information Exchange – PKCS#12 (.pfx)"**
6. Filename: `passkit-cert.p12`
7. Password: Set one and remember it
8. Finish → File saved
9. Move to: `backend/wallet/apple-passkit.p12`

**Outcome:** 
- `.p12` file created with private key
- Password securely stored (for environment variable)
- File location: `backend/wallet/apple-passkit.p12`

---

### Step 6: Download Apple Intermediate Certificate

PassKit passes are signed with an Apple intermediate certificate. Download it:

1. Go to https://www.apple.com/certificateauthority/
2. Download **"Apple Worldwide Developer Relations Certification Authority"** (`.cer`)
3. Save as: `backend/wallet/apple-intermediate.cer`
4. Keep this file in your backend directory (used by signing library)

**Note:** This certificate is publicly available and not secret.

---

### Step 7: Environment Configuration

Create/update `backend/.env.local` with:

```bash
# Apple PassKit Credentials
APPLE_TEAM_ID=ABCD1EF2GH
APPLE_PASS_TYPE_ID=pass.baukometra.baupass
APPLE_CERT_PATH=backend/wallet/apple-passkit.p12
APPLE_CERT_PASSWORD=your_secure_password_here
APPLE_INTERMEDIATE_CERT_PATH=backend/wallet/apple-intermediate.cer
```

**Security Notes:**
- ✅ Keep `.p12` file in Git-ignored directory (`backend/wallet/`)
- ✅ Use strong password for certificate
- ✅ Never commit `.env.local` to Git
- ✅ In production, use secure secrets manager (e.g., Railway, AWS Secrets Manager)

---

## Verification Checklist

Before moving to Phase 2, verify:

- [ ] Apple Developer Account active (check at https://developer.apple.com/account/)
- [ ] Pass Type ID created and visible in Dashboard
- [ ] Team ID noted and stored
- [ ] `.p12` certificate file generated and saved to `backend/wallet/`
- [ ] Apple Intermediate certificate downloaded and saved
- [ ] Environment variables set in `.env.local`
- [ ] File permissions correct (`.p12` readable by backend process)
- [ ] All files in Git-ignored directory (not tracked by Git)

---

## Testing the Certificate

In Phase 2, we'll test certificate validity by attempting to generate a sample pass. For now, just verify files exist:

```powershell
# From backend/ directory:
ls backend/wallet/
# Should show:
# - apple-passkit.p12
# - apple-intermediate.cer
```

If either file is missing, repeat the corresponding steps above.

---

## Troubleshooting

**Problem:** Can't find Pass Type ID after creating it
- **Solution:** Refresh the browser or log out/in to Apple Developer account

**Problem:** `.p12` file won't open / password rejected
- **Solution:** Regenerate the certificate (delete old one in Keychain, repeat Steps 5b-5d)

**Problem:** "Certificate doesn't match private key" error during pass generation
- **Solution:** Ensure `.p12` file includes both certificate AND private key (not just certificate)

**Problem:** Intermediate certificate download fails
- **Solution:** Try downloading from cached link: https://www.apple.com/certificateauthority/AppleWWDRCAG3.cer

---

## Next Steps

Once Apple setup is complete:

1. **Proceed to Google Wallet Setup** (see `docs/google-wallet-setup-guide.md`)
2. **Document credentials** in a shared secure location
3. **Move to Phase 2:** Implement pass generation logic in Flask backend

