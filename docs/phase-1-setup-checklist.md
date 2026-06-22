# Phase 1: Setup Checklist (Weeks 1–2)

**Goal:** Establish developer accounts, PassKit infrastructure, and design specifications for wallet pass generation.

---

## Week 1: Developer Accounts & API Keys

### [ ] 1.1 Apple Developer Account Setup
**Owner:** Team Lead  
**Timeline:** 2–3 hours (one-time, day 1)

- [ ] Create Apple Developer Account at https://developer.apple.com
  - Cost: $99/year for Individual or Organization account
  - Requirement: Apple ID + valid credit card
  
- [ ] Enroll in Apple Developer Program
  - Verify company identity (if registering as company)
  - Accept legal agreements
  
- [ ] Create Signing Certificate for PassKit
  - Go to Certificates, Identifiers & Profiles > Certificates
  - Create new "Pass Type ID" (e.g., `pass.baukometra.baupass`)
  - Generate Certificate Signing Request (CSR) from Keychain
  - Download .cer file and import to Keychain
  
- [ ] Generate Team ID
  - Found in Membership > Team ID (used in all pass files)
  - Note: `TEAM_ID` = UUID (e.g., `ABCD1EF2GH`)
  
- [ ] Download Intermediate Certificate
  - Required for pass signing: "Apple Worldwide Developer Relations Certification Authority"
  
- [ ] Create Pass Type ID Secret
  - Generate in Certificates, Identifiers & Profiles > Pass Type IDs
  - Note: `PASS_TYPE_ID` = `pass.baukometra.baupass`

**Deliverable:** Apple Developer credentials documented
- [ ] Team ID
- [ ] Pass Type ID
- [ ] Signing Certificate (stored securely)
- [ ] Private key from Keychain exported (.p12 file)

**Storage:** Create `backend/wallet/apple-credentials.json` (Git-ignored, with instructions for local setup)

---

### [ ] 1.2 Google Play Developer Account Setup
**Owner:** Team Lead  
**Timeline:** 2–3 hours (one-time, day 1)

- [ ] Create Google Play Developer Account at https://play.google.com/console/signup
  - Cost: $25 one-time registration fee
  - Requirement: Google Account + valid payment method
  
- [ ] Enable Google Wallet API
  - Go to Google Cloud Console > New Project (e.g., "WorkPass Wallet")
  - Enable APIs: Wallet API (formerly Google Pay API)
  - Create OAuth 2.0 Client ID
    - Application type: Service Account
    - Generate new JSON key file
  
- [ ] Create Issuer Account
  - Go to Google Wallet > Issuer Setup
  - Issuer ID = Project number from Google Cloud
  - Copy Issuer ID and Service Account Email
  
- [ ] Grant Permissions
  - Share Google Cloud project with team members (if needed)
  - Set up service account key with appropriate permissions

**Deliverable:** Google Wallet credentials documented
- [ ] Issuer ID
- [ ] Service Account Email
- [ ] Service Account JSON Key (stored securely)
- [ ] OAuth 2.0 credentials

**Storage:** Create `backend/wallet/google-credentials.json` (Git-ignored, with instructions for local setup)

---

### [ ] 1.3 Environment Configuration
**Owner:** DevOps / Tech Lead  
**Timeline:** 1 hour (day 1)

- [ ] Document credentials in `.env.local` (not committed)
  ```
  APPLE_TEAM_ID=ABCD1EF2GH
  APPLE_PASS_TYPE_ID=pass.baukometra.baupass
  APPLE_CERT_PATH=backend/wallet/apple-cert.p12
  APPLE_CERT_PASSWORD=<secure-password>
  
  GOOGLE_ISSUER_ID=123456789
  GOOGLE_SERVICE_ACCOUNT_EMAIL=wallet@baupass-project.iam.gserviceaccount.com
  GOOGLE_SERVICE_ACCOUNT_JSON_PATH=backend/wallet/google-service-account.json
  ```

- [ ] Create example `.env.local.example` for documentation
  
- [ ] Validate credentials by testing pass generation locally (see Phase 2)

---

## Week 2: PassKit Library & Pass Design

### [ ] 2.1 PassKit Python Library Research & Selection
**Owner:** Backend Engineer  
**Timeline:** 4–6 hours (cumulative across week 2)

**Research Goal:** Identify the best Python PassKit library for generating Apple Wallet and Google Wallet passes.

**Candidates to Evaluate:**
1. **pypasskit** (Python 3.8+)
   - Pros: Pure Python, Apple Wallet native support, active maintenance
   - Cons: Limited Google Wallet support
   - Repo: https://github.com/walletpass/pypasskit

2. **passkit-python** (Passkit SDK)
   - Pros: Official Passkit SDK, supports both Apple and Google formats
   - Cons: Requires API key, commercial service
   - Docs: https://developer.passkit.io/

3. **google-pass** (Google Wallet Python samples)
   - Pros: Official Google samples, direct API integration
   - Cons: Requires Google Wallet SDK, less documented
   - Repo: https://github.com/google-pay/google-wallet-samples

4. **custom hybrid** (pypasskit + Google Wallet REST API)
   - Pros: Best of both worlds, full control
   - Cons: More complex implementation, manual integration

**Evaluation Criteria:**
- [ ] Apple Wallet pass generation support
- [ ] Google Wallet pass generation support
- [ ] Barcode/QR code embedding capability
- [ ] Pass signing (cryptographic)
- [ ] Pass versioning / updates
- [ ] Documentation quality
- [ ] Community & maintenance activity
- [ ] License compatibility (open-source preferred)

**Recommendation Process:**
1. Create comparison matrix in `docs/passkit-library-evaluation.md`
2. Create proof-of-concept test with top 2 candidates
3. Document decision rationale

**Deliverable:** `docs/passkit-library-evaluation.md` with:
- [ ] Comparison matrix of 4+ libraries
- [ ] Recommendation with rationale
- [ ] Installation instructions for chosen library
- [ ] Code samples for basic pass generation (Apple + Google)

---

### [ ] 2.2 Pass Template Design Specification
**Owner:** Designer / Product Lead  
**Timeline:** 6–8 hours (cumulative across week 2)

**Design Goal:** Create professional pass templates for Suppix Technologie UG/WorkPass brand.

**Apple Wallet Pass (`.pkpass`) Structure:**
- [ ] Define pass layout (boarding pass, generic, event, or store card style)
  - Recommendation: **Generic card** or **Event ticket** style for badges
  
- [ ] Design visual elements:
  - [ ] Background color: Primary brand color (from `invoice_primary_color` in DB)
  - [ ] Logo image: 320×320 px minimum (PNG, RGBA)
  - [ ] Thumbnail image: 86×86 px (PNG, RGBA)
  - [ ] Icon: 29×29 px (PNG, RGBA)
  - [ ] Strip image (optional): 812×228 px for header strip
  
- [ ] Define pass fields (primary, secondary, auxiliary):
  ```
  Primary:   Worker Name (e.g., "Max Müller")
  Secondary: Badge ID (e.g., "W-12345")
  Auxiliary: Company Name, Valid Until Date
  ```
  
- [ ] Define barcode/QR code placement
  - Code type: QR code (for fallback)
  - Size: 150×150 px
  - Position: Bottom of pass
  - Content: Badge ID + validation checksum
  
- [ ] Text formatting
  - Font: System default (iOS handles automatically)
  - Color: White on primary color background
  - Labels: "Badge ID", "Valid Until", "Company"

**Google Wallet Pass (JWT Token) Structure:**
- [ ] Define pass class format (generic class or custom)
  - Google Wallet classes: `genericClass`, `eventTicketClass`
  - Recommendation: **genericClass** for worker badge
  
- [ ] Define pass object (instance):
  - [ ] Class ID: `baukometra.baupass.worker`
  - [ ] Pass ID: Unique per worker (e.g., `W-12345`)
  
- [ ] Visual elements (similar to Apple):
  - [ ] Logo: 512×512 px minimum (PNG, RGBA)
  - [ ] Hero image: 1200×628 px (optional)
  - [ ] Text color: White on dark background
  
- [ ] QR code integration
  - Google Wallet natively supports barcode field
  - Format: Same QR structure as Apple

**Common Fields (Both Platforms):**
- [ ] Worker ID (primary identifier)
- [ ] Worker Name (display)
- [ ] Company Name
- [ ] Validity Period (valid_until date)
- [ ] QR/Badge barcode
- [ ] Issuer name (WorkPass)

**Deliverable:** `docs/pass-template-specification.md` with:
- [ ] Apple Wallet pass design spec (JSON example)
- [ ] Google Wallet pass design spec (JWT example)
- [ ] Asset requirements (images, sizes, formats)
- [ ] Brand color/logo guidelines
- [ ] Barcode placement and encoding spec
- [ ] Sample pass JSON payloads

---

### [ ] 2.3 Pass Lifecycle State Machine
**Owner:** Backend Engineer  
**Timeline:** 2–3 hours (day 4–5)

**Define:** How passes transition between states from issuance to expiration/revocation.

**States:**
```
issued → active → {revoked | expired}

Details:
- issued: Pass created but not yet delivered to user
- active: User has added pass to wallet, can use for access
- revoked: Admin manually revoked access (user removed from system)
- expired: Pass validity_date reached
```

**Triggers:**
- `issued → active`: User clicks "Add to Wallet", wallet API confirms receipt
- `active → revoked`: Worker deleted/suspended, manual revocation, access denied
- `active → expired`: scheduled job runs at midnight, checks validity dates
- `issued → expired`: pass created but never added to wallet, validity expired

**Database Tracking:**
- Add to `worker_passes` table (see Schema Design, section 2.4)
- Fields: `status`, `issued_at`, `activated_at`, `revoked_at`, `expired_at`

**Deliverable:** State diagram in `docs/pass-lifecycle-spec.md`
- [ ] State transition flowchart (text or ASCII diagram)
- [ ] Trigger conditions for each transition
- [ ] Error handling (e.g., user removes pass from wallet)

---

### [ ] 2.4 Database Schema Design
**Owner:** Backend Engineer  
**Timeline:** 2–3 hours (day 5)

**New Table: `worker_passes`**

```sql
CREATE TABLE IF NOT EXISTS worker_passes (
    id TEXT PRIMARY KEY,                    -- pass-{uuid}
    worker_id TEXT NOT NULL,                -- FK: workers.id
    company_id TEXT NOT NULL,               -- FK: companies.id (denormalized for queries)
    pass_type TEXT NOT NULL DEFAULT 'badge', -- 'badge' (expandable for future types)
    platform TEXT NOT NULL,                 -- 'apple' | 'google'
    pass_class_id TEXT NOT NULL,            -- apple: class_id, google: classId
    pass_object_id TEXT NOT NULL UNIQUE,    -- apple: serialNumber, google: objectId
    status TEXT NOT NULL DEFAULT 'issued',  -- 'issued' | 'active' | 'revoked' | 'expired'
    pass_data_json TEXT NOT NULL,           -- full pass JSON (for reconstruction/updates)
    pass_url TEXT NOT NULL,                 -- URL to download .pkpass or JWT redirect
    signed_pass_data BLOB,                  -- optional: cached signed .pkpass binary (Apple)
    issued_at TEXT NOT NULL,                -- ISO timestamp
    activated_at TEXT,                      -- ISO timestamp (when user added to wallet)
    revoked_at TEXT,                        -- ISO timestamp (if manually revoked)
    expired_at TEXT,                        -- ISO timestamp (if validity date passed)
    version INTEGER NOT NULL DEFAULT 1,     -- pass version (for updates)
    last_updated_at TEXT NOT NULL,          -- ISO timestamp
    error_log TEXT,                         -- JSON array of recent errors
    FOREIGN KEY(worker_id) REFERENCES workers(id),
    FOREIGN KEY(company_id) REFERENCES companies(id)
);

CREATE INDEX IF NOT EXISTS idx_worker_passes_worker_platform 
    ON worker_passes(worker_id, platform, status);
CREATE INDEX IF NOT EXISTS idx_worker_passes_company_status 
    ON worker_passes(company_id, status);
CREATE INDEX IF NOT EXISTS idx_worker_passes_expired_at 
    ON worker_passes(expired_at, status) WHERE status IN ('active', 'issued');
```

**New Settings Column (optional):**
```sql
ALTER TABLE settings ADD COLUMN IF NOT EXISTS 
    wallet_passes_enabled INTEGER NOT NULL DEFAULT 0;  -- feature flag

ALTER TABLE settings ADD COLUMN IF NOT EXISTS 
    wallet_apple_enabled INTEGER NOT NULL DEFAULT 0;

ALTER TABLE settings ADD COLUMN IF NOT EXISTS 
    wallet_google_enabled INTEGER NOT NULL DEFAULT 0;
```

**Schema Rationale:**
- `pass_data_json`: Store full pass payload for reconstructing/updating passes
- `signed_pass_data`: Cache signed binary to avoid re-signing on every download
- `platform`: Enables multi-platform support (same worker, different passes)
- `version`: Track pass updates (e.g., if company branding changes)
- `status`: Support lifecycle management (revoke, expire, etc.)
- Unique `pass_object_id`: Ensure no duplicate passes in Apple/Google systems

**Deliverable:** `docs/database-schema-phase-1.md` with:
- [ ] Full SQL CREATE TABLE statements
- [ ] Index definitions and rationale
- [ ] Data type justifications
- [ ] Migration strategy for existing database

---

## Week 2: API Endpoint Planning (Draft Specification)

### [ ] 2.5 API Endpoint Specification: `/api/worker-app/wallet/pass`
**Owner:** Backend Engineer  
**Timeline:** 2–3 hours (end of week 2)

**Purpose:** Deliver wallet passes (Apple `.pkpass` or Google JWT) to authenticated workers.

**Endpoint:** 
```
GET /api/worker-app/wallet/pass?platform=apple|google
```

**Request:**
- Authentication: Worker session token (Bearer)
- Query params:
  - `platform`: 'apple' or 'google' (required)
  - `force_regenerate`: 'true' (optional, rebuild pass from worker data)

**Response (Apple):**
```json
{
  "status": "success",
  "platform": "apple",
  "pass_url": "https://baupass.local/passes/apple/W-12345-v1.pkpass",
  "added_to_wallet_soon": false
}
```

**Response (Google):**
```json
{
  "status": "success",
  "platform": "google",
  "pass_url": "https://baupass.local/passes/google/redirect?pass_id=W-12345",
  "add_to_wallet_url": "https://pay.google.com/gp/v/save/abc123..."
}
```

**Error Cases:**
- 401: Worker session expired or invalid
- 403: Company doesn't have wallet feature enabled
- 404: Worker not found
- 500: Pass generation failed

**Backend Logic:**
1. Validate worker session token
2. Load worker data from DB
3. Check if pass exists for (worker_id, platform)
   - If exists and status='active': return cached URL
   - If missing or status='issued': generate new pass
4. Sign pass (Apple) / Generate JWT (Google)
5. Store in database with status='issued'
6. Return download URL
7. Frontend will call "Add to Wallet" → triggers status='active'

**Implementation Details (TBD in Phase 2):**
- [ ] Pass generation library integration
- [ ] Signing/JWT token generation
- [ ] File storage (temporary vs persistent)
- [ ] Rate limiting (prevent pass spam)

**Deliverable:** `docs/api-endpoint-spec-wallet-pass.md` with:
- [ ] Full OpenAPI/Swagger spec (or detailed JSON schema)
- [ ] Request/response examples
- [ ] Error codes and messages
- [ ] Authentication flow diagram

---

## Week 2: Documentation & Validation

### [ ] 2.6 Create Phase 1 Summary Document
**Owner:** Tech Lead  
**Timeline:** 1 hour (end of week 2)

**File:** `docs/phase-1-summary.md`

Content:
- [ ] Apple Developer Account credentials (Team ID, Pass Type ID)
- [ ] Google Wallet credentials (Issuer ID, Service Account)
- [ ] PassKit library selection and installation instructions
- [ ] Pass template designs (Apple + Google specs)
- [ ] Database schema SQL (ready for Phase 2)
- [ ] API endpoint specification (draft)
- [ ] Environment configuration template
- [ ] Known blockers or decisions for Phase 2

---

### [ ] 2.7 Validation Checklist
**Owner:** Tech Lead  
**Timeline:** 1–2 hours (end of week 2)

Before moving to Phase 2, verify:

- [ ] Apple Developer account created and PassKit certificate generated
- [ ] Google Wallet API enabled and service account key obtained
- [ ] PassKit library chosen and documented with installation steps
- [ ] Pass template spec complete (Apple + Google designs)
- [ ] Database schema validated (no conflicts with existing tables)
- [ ] API endpoint spec drafted and reviewed
- [ ] All credentials securely stored in `.env` (not committed)
- [ ] Team has access to all developer accounts and credentials
- [ ] Documentation complete and shared with team
- [ ] No blockers identified for Phase 2 Backend work

---

## Success Criteria (End of Week 2)

✅ **All of the following must be true:**

1. **Developer Accounts**: Apple + Google accounts active, credentials documented
2. **API Keys**: All required keys generated and securely stored
3. **Library Selection**: PassKit Python library chosen, evaluated, documented
4. **Pass Design**: Apple Wallet + Google Wallet templates designed and specified
5. **Database Schema**: `worker_passes` table design approved, ready for implementation
6. **API Spec**: `/api/worker-app/wallet/pass` endpoint spec drafted
7. **Documentation**: All Phase 1 deliverables documented in `docs/`
8. **Team Alignment**: Design reviewed and approved by tech lead + product
9. **No Blockers**: Identified any showstoppers for Phase 2 (blocking issues resolved)

---

## Transition to Phase 2

Once Phase 1 is complete:

1. **Phase 2 Kickoff**: Backend engineer implements:
   - Database migrations (`worker_passes` table)
   - PassKit library integration
   - `/api/worker-app/wallet/pass` endpoint
   - Pass signing/generation logic (Apple + Google)

2. **Parallel Work**: Designer prepares pass images and branding assets

3. **Frontend Prep**: Frontend engineer prepares "Add to Wallet" UI (buttons, logic)

---

## Key Contacts & Resources

- **Apple Developer Support**: https://developer.apple.com/support/
- **Google Wallet API Docs**: https://developers.google.com/wallet
- **PassKit Library Docs**: (Link to chosen library)
- **Internal Team**: [List team members with roles]

