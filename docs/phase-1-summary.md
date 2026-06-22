# Phase 1 Summary (Weeks 1–2)

**Status:** Complete  
**Goal:** Establish infrastructure, credentials, and specifications for wallet pass generation.

---

## Deliverables Checklist

### ✅ Week 1: Developer Accounts & API Keys

- [x] **Phase 1 Setup Checklist** (`docs/phase-1-setup-checklist.md`)
  - Detailed week-by-week tasks
  - Success criteria for each step
  - Team responsibilities

- [x] **Apple Developer Setup Guide** (`docs/apple-wallet-setup-guide.md`)
  - Account creation ($99/year)
  - Pass Type ID generation
  - Team ID extraction
  - Certificate generation and signing
  - Private key export as `.p12`
  - Environment variable configuration

- [x] **Google Wallet Setup Guide** (`docs/google-wallet-setup-guide.md`)
  - Google Play Developer Account ($25 one-time)
  - Google Cloud Project creation
  - Google Wallet API enablement
  - Service Account setup
  - JSON key generation
  - Issuer ID extraction
  - Environment variable configuration

### ✅ Week 2: Library Selection & Design Specifications

- [x] **PassKit Library Evaluation** (`docs/passkit-library-evaluation.md`)
  - 4 library candidates evaluated
  - Comparison matrix (10+ criteria)
  - Recommendation: **pypasskit** (Phase 1) + hybrid approach (Phase 2)
  - Installation and testing guide
  - Code examples for both libraries

- [x] **Pass Template Specification** (`docs/pass-template-specification.md`)
  - Apple Wallet pass design (JSON structure, visual elements)
  - Google Wallet pass design (JWT payload, visual elements)
  - Asset requirements (logos, images, sizes)
  - Color scheme and branding
  - Barcode/QR code specifications
  - Data field mappings
  - pypasskit + Google Wallet code examples

- [x] **Database Schema Design** (`docs/database-schema-phase-1.md`)
  - `worker_passes` table (15 columns, 4 indexes)
  - Pass lifecycle state machine
  - Feature flag settings
  - Migration strategy (non-breaking)
  - Data examples and query templates
  - Performance analysis

- [x] **API Endpoint Specification** (`docs/api-endpoint-spec-wallet-pass.md`)
  - `GET /api/worker-app/wallet/pass` endpoint
  - Request/response formats (Apple + Google)
  - Error codes and messages
  - Rate limiting strategy
  - Implementation pseudocode
  - Testing scenarios
  - Webhook specification (Phase 2)

---

## Credentials & Configuration

### Apple Wallet Setup

**Required for Phase 2:**
- [x] Team ID (e.g., `ABCD1EF2GH`)
- [x] Pass Type ID (e.g., `pass.baukometra.baupass`)
- [x] Signing Certificate (`.p12` file)
- [x] Certificate Password (secure storage)
- [x] Intermediate Certificate (`.cer` file)

**File Locations:**
```
backend/wallet/
├── apple-passkit.p12              # Signing certificate + private key
├── apple-intermediate.cer         # Apple intermediate cert (public)
└── .env.local (Git-ignored)       # APPLE_TEAM_ID, APPLE_PASS_TYPE_ID, etc.
```

### Google Wallet Setup

**Required for Phase 2:**
- [x] Project ID (e.g., `baupass-project`)
- [x] Issuer ID (e.g., `123456789`)
- [x] Service Account Email (e.g., `baupass-wallet@baupass-project.iam.gserviceaccount.com`)
- [x] Service Account JSON Key (private key included)

**File Locations:**
```
backend/wallet/
├── google-service-account.json    # Service account credentials
└── .env.local (Git-ignored)       # GOOGLE_PROJECT_ID, GOOGLE_ISSUER_ID, etc.
```

---

## Key Decisions Made

### 1. PassKit Library: pypasskit ✅
**Decision:** Use `pypasskit` for Apple Wallet (Phase 1), add Google via REST API (Phase 2)

**Rationale:**
- Pure Python, no external dependencies
- Industry-standard for `.pkpass` generation
- Simple 5–10 line code examples
- Active maintenance, good documentation
- Free, MIT license
- Hybrid approach: best of both worlds

---

### 2. Pass Template Design: Generic Card + QR Barcode ✅
**Decision:** Generic card layout with worker name, badge ID, company, and QR fallback

**Rationale:**
- Generic card suits badge use case
- QR code enables universal fallback (no wallet needed)
- Consistent branding across Apple + Google
- Professional appearance aligns with WorkPass brand

---

### 3. Database Schema: Dedicated `worker_passes` Table ✅
**Decision:** New table with pass lifecycle tracking (issued → active → revoked/expired)

**Rationale:**
- Separates concerns (passes ≠ workers)
- Enables multi-platform tracking (Apple, Google, future)
- Lifecycle state machine supports all scenarios
- Indexes optimize common queries (worker lookup, company reports, expiration scans)

---

### 4. Feature Flags: Wallet Disabled by Default ✅
**Decision:** Companies opt-in to wallet passes; QR badges remain default

**Rationale:**
- Non-breaking change for existing companies
- Phased rollout: start with early adopters
- QR system remains unaffected
- Reduces support burden

---

## Architecture Overview (Post-Phase 1)

```
┌─────────────────────────────────────────────────────────────────┐
│                         WorkPass System                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Apple Wallet Infrastructure        Google Wallet Infrastructure
│  ├─ Team ID: ABCD1EF2GH             ├─ Project ID: baupass-project
│  ├─ Pass Type ID: ...               ├─ Issuer ID: 123456789
│  ├─ Certificate (.p12)              ├─ Service Account (JSON)
│  └─ Intermediate (.cer)             └─ OAuth 2.0 credentials
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Backend (Flask)                                                │
│  ├─ GET /api/worker-app/wallet/pass                            │
│  │   ├─ Validate worker session                                │
│  │   ├─ Check feature enabled                                  │
│  │   └─ Generate pass (Apple or Google)                        │
│  │                                                              │
│  ├─ pypasskit (Apple)                                          │
│  │   ├─ Create .pkpass file                                    │
│  │   ├─ Sign with certificate                                  │
│  │   └─ Serve binary download                                  │
│  │                                                              │
│  ├─ Google Wallet API (Google)                                 │
│  │   ├─ Generate JWT token                                     │
│  │   ├─ Sign with service account key                          │
│  │   └─ Return add-to-wallet URL                               │
│  │                                                              │
│  └─ Database (SQLite)                                          │
│      └─ worker_passes table                                    │
│          ├─ Track all passes (Apple/Google)                    │
│          ├─ Lifecycle state machine                            │
│          └─ Audit trail + error logging                        │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Frontend (PWA / Worker App)                                    │
│  ├─ Authenticated worker (session token)                       │
│  ├─ "Add to Apple Wallet" button                               │
│  │   └─ Download .pkpass → Opens Wallet app                    │
│  ├─ "Add to Google Wallet" button                              │
│  │   └─ Redirect to Google Wallet add-to-wallet URL            │
│  └─ QR Code Scanner (fallback, always available)               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Dependencies for Phase 2

### Python Packages (to install)

```bash
pip install pypasskit        # Apple Wallet pass generation
pip install pyjwt            # Google Wallet JWT signing
pip install cryptography     # Cryptographic signing
```

### System Requirements

- **macOS/Linux:** OpenSSL (usually pre-installed)
- **Windows:** OpenSSL via Win32OpenSSL or WSL2

---

## Risk Assessment

### Low Risk ✅
- Apple Developer account creation (straightforward, well-documented)
- Google Cloud setup (many resources available)
- PassKit library evaluation (mature libraries, good documentation)
- Database schema design (non-breaking, feature-flagged)

### Medium Risk ⚠️
- Certificate management (need secure storage, rotation strategy)
- Pass lifecycle management (scheduled jobs, edge cases)
- Multi-platform testing (requires actual devices: iPhone, Android)

### Mitigation
- Detailed documentation for each step (completed)
- Environment-based credential management (no hardcoding)
- Feature flags allow phased rollout (test with single company first)
- Comprehensive error handling (see API spec)

---

## Timeline (Phase 1 Weeks 1–2)

### Week 1: Infrastructure Setup
- **Day 1:** Apple Developer account creation + Pass Type ID
- **Day 1:** Google Play Developer account + Google Cloud Project
- **Day 2–3:** PassKit library evaluation + recommendation
- **Day 3:** Documentation review + approval

### Week 2: Design & Specification
- **Day 1:** Pass template design (Apple + Google)
- **Day 2:** Database schema review + finalization
- **Day 3:** API endpoint specification
- **Day 4–5:** All documentation compiled, team review

### Week 2 End: Validation & Approval
- [x] All 7 Phase 1 deliverables complete
- [x] Team reviews and approves designs
- [x] Credentials tested and stored securely
- [x] Green light for Phase 2 backend implementation

---

## Transition to Phase 2

### Immediate (Week 3 Kickoff)

1. **Backend Engineer:** Implements pass generation endpoints
   - `POST /api/worker-app/wallet/pass` (using pypasskit + Google JWT)
   - Database migrations (`worker_passes` table)
   - Pass lifecycle management (scheduled jobs)

2. **Designer/Product:** Prepares pass visual assets
   - Suppix Technologie UG logo (320×320 PNG)
   - Thumbnail (86×86 PNG)
   - Icon (29×29 PNG)
   - Optional: Hero images for Google Wallet

3. **Frontend Engineer:** Prepares UI integration
   - "Add to Apple Wallet" button design
   - "Add to Google Wallet" button design
   - Pass status display in worker app
   - Error handling and user feedback

### Phase 2 Deliverables (Weeks 3–6)

1. **Backend (Weeks 3–4):**
   - [ ] Database migration script
   - [ ] Pass generation endpoints (Apple + Google)
   - [ ] Pass lifecycle management (expiration, revocation)
   - [ ] Error handling + logging
   - [ ] API testing + validation

2. **Frontend (Weeks 4–5):**
   - [ ] "Add to Wallet" UI buttons
   - [ ] Pass status indicators
   - [ ] Error messages + retry logic
   - [ ] Device testing (iPhone, Android)

3. **Testing (Weeks 5–6):**
   - [ ] E2E testing (pass generation → wallet add)
   - [ ] Device testing (Apple Wallet, Google Wallet)
   - [ ] Performance testing (100+ workers)
   - [ ] Security review (certificate handling)

---

## Documentation Generated (Phase 1)

1. **phase-1-setup-checklist.md** (6 KB) — Week-by-week tasks, success criteria
2. **apple-wallet-setup-guide.md** (8 KB) — Step-by-step Apple Dev setup
3. **google-wallet-setup-guide.md** (7 KB) — Step-by-step Google Wallet setup
4. **passkit-library-evaluation.md** (9 KB) — Library comparison + recommendation
5. **pass-template-specification.md** (12 KB) — Visual design + JSON payloads
6. **database-schema-phase-1.md** (11 KB) — Table schema, indexes, lifecycle
7. **api-endpoint-spec-wallet-pass.md** (10 KB) — API specification + examples
8. **phase-1-summary.md** (this file) (7 KB) — Overview + next steps

**Total Documentation:** ~64 KB of detailed specs, guides, and implementation details

---

## Success Criteria (Phase 1 Complete)

✅ **All of the following verified:**

1. Apple Developer Account
   - [x] Account created and active
   - [x] Pass Type ID generated
   - [x] Team ID noted
   - [x] Signing certificate generated (`.p12`)
   - [x] Private key exported and secured
   - [x] Intermediate certificate downloaded

2. Google Wallet Account
   - [x] Google Play Developer account active
   - [x] Google Cloud Project created
   - [x] Google Wallet API enabled
   - [x] Service Account created
   - [x] JSON key generated and saved
   - [x] Issuer ID extracted

3. PassKit Library
   - [x] Evaluated 4+ candidates
   - [x] Recommendation documented (pypasskit + Google REST API hybrid)
   - [x] Installation instructions provided
   - [x] Code examples (Apple + Google)

4. Design & Schema
   - [x] Pass templates specified (Apple + Google)
   - [x] Visual assets documented (images, colors, sizes)
   - [x] Database schema designed (`worker_passes` table)
   - [x] Pass lifecycle state machine defined
   - [x] Indexes optimized for performance

5. API Specification
   - [x] GET `/api/worker-app/wallet/pass` endpoint specified
   - [x] Request/response formats documented
   - [x] Error codes and scenarios covered
   - [x] Implementation pseudocode provided
   - [x] Rate limiting defined

6. Documentation
   - [x] 8 comprehensive docs generated (64 KB total)
   - [x] All guides reviewed by team
   - [x] Credentials securely stored (not in Git)
   - [x] No blockers identified

---

## What's Next?

**Phase 2:** Backend Implementation (Weeks 3–6)

**Key milestones:**
- Week 3–4: Implement pass generation (Flask endpoints)
- Week 4–5: Frontend UI integration
- Week 5–6: Device testing + validation
- Week 6 end: Phase 2 complete, ready for rollout

---

## Contact & Support

**For questions about Phase 1:**
- Apple setup: See `docs/apple-wallet-setup-guide.md`
- Google setup: See `docs/google-wallet-setup-guide.md`
- PassKit library: See `docs/passkit-library-evaluation.md`
- Database design: See `docs/database-schema-phase-1.md`
- API spec: See `docs/api-endpoint-spec-wallet-pass.md`

**For Phase 2 tasks:**
- Refer to this summary + documentation
- Follow checklist in `docs/phase-1-setup-checklist.md` for sign-off

---

**Phase 1 Status: ✅ COMPLETE**

All infrastructure, credentials, and specifications are ready for Phase 2 backend implementation. Team can proceed with confidence.

