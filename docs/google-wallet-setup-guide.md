# Google Wallet Setup Guide

**Goal:** Enable Google Wallet API and generate credentials for issuing digital passes to Android users.

---

## Overview

To generate Google Wallet passes, you need:
1. **Google Play Developer Account** ($25 one-time)
2. **Google Cloud Project** (free)
3. **Wallet API enabled** (free, rate-limited)
4. **Service Account** (for backend API calls)
5. **OAuth 2.0 credentials** (for authentication)

---

## Step-by-Step Setup

### Step 1: Create Google Play Developer Account

1. Go to https://play.google.com/console/
2. Click **"Sign up for Google Play Console"**
3. Sign in with your Google account (or create one)
4. Enter Developer Profile info:
   - Name: Company name (e.g., "Suppix Technologie UG")
   - Email: Company email
   - Country: Germany (or your location)
5. Accept Developer Agreement
6. **Pay $25 registration fee** (one-time)
7. Verify identity (may require identity document)

**Outcome:** Google Play Developer account active

---

### Step 2: Create Google Cloud Project

1. Go to **Google Cloud Console**: https://console.cloud.google.com/
2. Sign in with your Google account (same as Play Developer account)
3. Create a new project:
   - Click **"Select a Project"** (top left) → **"NEW PROJECT"**
   - Name: `WorkPass Wallet` (or similar)
   - Organization: Select if available
   - Click **"CREATE"**
4. Wait for project creation (may take 1–2 minutes)

**Outcome:** Google Cloud Project created, selected in console

---

### Step 3: Enable Google Wallet API

1. In Google Cloud Console, go to **"APIs & Services"** (left sidebar)
2. Click **"Enable APIs and Services"** (top)
3. Search for **"Google Wallet API"** (formerly "Google Pay API for Passes")
4. Select it → Click **"ENABLE"**
5. Wait for enablement to complete

**Outcome:** Google Wallet API active for your project

---

### Step 4: Create Service Account

Service Account = backend authentication for your Flask app to create passes.

1. In Google Cloud Console: **"APIs & Services"** → **"Credentials"** (left sidebar)
2. Click **"+ CREATE CREDENTIALS"** (top) → **"Service Account"**
3. Fill Service Account details:
   - **Service account name:** `baupass-wallet`
   - **Service account ID:** (auto-populated, e.g., `baupass-wallet@baupass-project.iam.gserviceaccount.com`)
   - **Description:** "Backend service for issuing wallet passes"
4. Click **"CREATE AND CONTINUE"**

5. Grant roles:
   - Click **"Select a role"** → Search for **"Editor"**
   - Select **"Editor"** role (or more restrictive: "Wallet API Editor")
   - Click **"CONTINUE"**

6. Click **"DONE"**

**Outcome:** Service Account created

---

### Step 5: Generate Service Account Key

Service Account Key = JSON file with credentials for your backend to authenticate.

1. In Google Cloud Console: **"APIs & Services"** → **"Service Accounts"**
2. Click on the service account you just created (`baupass-wallet@...`)
3. Go to **"KEYS"** tab
4. Click **"ADD KEY"** → **"Create new key"**
5. Key type: **"JSON"** → Click **"CREATE"**
6. File downloads automatically: `baupass-project-[ID].json`
7. **Rename & save:**
   - Rename to: `google-service-account.json`
   - Move to: `backend/wallet/google-service-account.json`
   - **Do NOT commit to Git**

**File contents (example):**
```json
{
  "type": "service_account",
  "project_id": "baupass-project",
  "private_key_id": "abc123...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...",
  "client_email": "baupass-wallet@baupass-project.iam.gserviceaccount.com",
  "client_id": "123456789...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  ...
}
```

**Outcome:** 
- JSON key file saved to `backend/wallet/`
- Extract and note:
  - `project_id` → `GOOGLE_PROJECT_ID`
  - `client_email` → `GOOGLE_SERVICE_ACCOUNT_EMAIL`
  - Entire file path → `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`

---

### Step 6: Get Issuer ID

Issuer ID = unique identifier for your organization in Google Wallet system.

1. In Google Cloud Console: **"APIs & Services"** → **"Credentials"**
2. Look at your Service Account (`baupass-wallet@...`)
3. Copy the **Project Number** (found at top of console, or in Service Account details)
   - Example: `123456789` (12-digit number)
4. This is your **Issuer ID**

**Outcome:** 
- Issuer ID noted: `123456789`
- This is your `GOOGLE_ISSUER_ID` environment variable

---

### Step 7: Create Google Wallet Issuer Account (Optional but Recommended)

This step registers your Issuer ID with Google Wallet system, enabling you to see pass issuance metrics in Google Wallet Dashboard.

1. Go to https://pay.google.com/business/console (requires Google account)
2. Sign in with your Google account
3. Click **"Set up"** or **"Wallet Issuer Account"**
4. Link your Google Cloud project:
   - Use Issuer ID from Step 6
   - Authorize Google Wallet to access your project
5. Add issuer details:
   - Issuer name: "Suppix Technologie UG" or "WorkPass"
   - Logo URL (optional): Link to company logo
6. Click **"Save"**

**Outcome:** Issuer account registered (optional, useful for monitoring)

---

### Step 8: Environment Configuration

Update `backend/.env.local`:

```bash
# Google Wallet API Credentials
GOOGLE_PROJECT_ID=baupass-project
GOOGLE_ISSUER_ID=123456789
GOOGLE_SERVICE_ACCOUNT_EMAIL=baupass-wallet@baupass-project.iam.gserviceaccount.com
GOOGLE_SERVICE_ACCOUNT_JSON_PATH=backend/wallet/google-service-account.json
```

**Security Notes:**
- ✅ Keep JSON key file in Git-ignored directory
- ✅ Never commit `.env.local` to Git
- ✅ In production, use secure secrets manager
- ✅ Rotate service account keys periodically

---

## API Quotas & Rate Limits

Google Wallet API has quotas:

- **Default:** 1,000 creates/updates per day (free tier)
- **Increase:** Contact Google Cloud support to request higher quota if needed

For WorkPass:
- Worker count: ~100–500 (per company)
- Pass creation: Once per worker setup, updates on access changes
- Estimated usage: Well below 1,000/day

---

## Verification Checklist

Before moving to Phase 2, verify:

- [ ] Google Play Developer account active
- [ ] Google Cloud Project created
- [ ] Google Wallet API enabled
- [ ] Service Account created
- [ ] Service Account JSON key downloaded and saved to `backend/wallet/`
- [ ] Issuer ID (Project Number) obtained
- [ ] Environment variables set in `.env.local`:
  - `GOOGLE_PROJECT_ID`
  - `GOOGLE_ISSUER_ID`
  - `GOOGLE_SERVICE_ACCOUNT_EMAIL`
  - `GOOGLE_SERVICE_ACCOUNT_JSON_PATH`

---

## Testing the Credentials

In Phase 2, we'll test by generating a sample pass. For now, verify the JSON file:

```powershell
# From backend/ directory:
Test-Path backend/wallet/google-service-account.json
# Should return: True

# Check file contents:
Get-Content backend/wallet/google-service-account.json | ConvertFrom-Json | Select-Object project_id, client_email
```

If file is missing or invalid, repeat Step 5.

---

## Understanding Google Wallet Pass Structure

Google Wallet passes use **JWT (JSON Web Tokens)** signed with your Service Account private key.

**Pass Class** (template):
- Defines appearance, fields, colors, logo
- Created once per pass type
- Example Class ID: `3388655000022476551.baukometra_worker`

**Pass Object** (instance):
- Actual pass issued to a user
- Unique per worker
- Contains worker data (name, badge ID, valid until)
- Example Object ID: `W-12345`

**Pass URL:**
- User clicks "Add to Google Wallet"
- Redirected to: `https://pay.google.com/gp/v/save/{PASS_JWT}`
- Pass JWT is signed with Service Account private key

---

## Troubleshooting

**Problem:** Service Account JSON key has `type: "service_account"` but still rejected
- **Solution:** Ensure Google Wallet API is enabled (Step 3)

**Problem:** "Issuer ID not found" error
- **Solution:** Use Project Number (not Project ID). In Cloud Console, look for "Project Number" at top.

**Problem:** Quota exceeded
- **Solution:** Request higher quota in Google Cloud Console (APIs & Services → Google Wallet API → Quotas)

**Problem:** JSON key file permissions error (on Linux/Mac)
- **Solution:** Set permissions: `chmod 600 backend/wallet/google-service-account.json`

---

## Next Steps

Once Google Wallet setup is complete:

1. **Apple setup done?** Check `docs/apple-wallet-setup-guide.md`
2. **Both platforms ready?** Proceed to Phase 2
3. **Credentials secure?** All files in Git-ignored directory?
4. **Move to Phase 2:** Implement pass generation in Flask backend

