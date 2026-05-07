# QR/NFC/Wallet Implementation Architecture – Three Tiers

**Document Date:** May 2026  
**Status:** Strategic Recommendation  
**Multi-Platform Goal:** Universal access across iPhone, Android, and Samsung devices

---

## Executive Summary

This document outlines three implementation tiers for digital access cards (badges) and physical NFC integration at turnstiles/gates. Each tier balances:
- **User experience:** How seamlessly workers access the gate
- **Platform coverage:** iPhone, Android, Samsung support
- **Implementation effort:** Backend, frontend, hardware complexity
- **Cost:** Development, maintenance, infrastructure

**Key Principle:** No worker is excluded based on device type or platform choice.

---

## Current State (as of May 2026)

**Database:**
- 110 active workers
- 110 workers with `badge_id` (QR-scannable)
- 0 workers with `physical_card_id` (NFC chip ID)

**Frontend:**
- Worker PWA (`worker-app.js`): QR-only digital badge display
- Turnstile UI (`app.js`): QR scanner + badge matcher
- Service worker: Basic offline support

**Backend:**
- Gate endpoint (`/api/gates/tap`): Accepts `physicalCardId`, `cardId`, or `badgeId`
- Feature gating: `qr_badges` (all plans) vs `nfc_badges` (starter+)
- Normalization: Badge ID, Physical Card ID, Badge PIN functions exist

**Hardware:**
- No physical NFC cards yet issued
- No wallet pass infrastructure (Apple Wallet, Google Wallet)
- QR scanners working for gate access

---

## Architectural Constraints & Platform Realities

### Why Web/PWA Cannot Read Physical NFC

**Constraint:** A standard web or PWA frontend in the browser **cannot freely read physical NFC chips on iPhone** (even with Web NFC API proposals). This is by design:
- Apple restricts NFC access to native apps and Apple Wallet
- Web NFC is experimental and browser-gated
- PWA on iPhone (iOS) runs in UIWebView/WKWebView, not a native container

**Implication:** Wallet pass (Apple Wallet, Google Wallet) is the only way to bring physical NFC into the native wallet UI on iPhone.

### QR as Universal Fallback

**Advantage:** QR codes work everywhere:
- ✅ iPhone (camera + browser)
- ✅ Android (camera + browser)
- ✅ Samsung (camera + browser)
- ✅ Works offline in PWA if cached
- ✅ Works with any gate scanner that reads QR text
- ✅ Requires no platform-specific infrastructure

**Trade-off:** Less convenient than native wallet (extra step: scan with camera app, or open app and scan).

---

## Tier 1: Minimal & Fast – QR + Optional Physical Card

**Timeline:** 4–6 weeks  
**Effort:** Low  
**Cost:** ~€3,000–5,000 (if adding physical NFC cards)

### What It Includes

1. **Digital QR Badge (Already Working)**
   - Worker app displays QR code of their `badge_id`
   - QR scanners at gate read the code
   - Turnstile confirms match against `workers.badge_id_lookup`

2. **Optional Physical NFC Card**
   - Assign `physical_card_id` (UID from NFC chip) to each worker
   - Gate reader detects NFC tap → extracts card UID → matches `workers.physical_card_id`
   - Both QR and NFC work in parallel (choice at gate)

3. **Feature Gating**
   - `qr_badges`: Available on all plans (default)
   - `nfc_badges`: Available on starter+ plans (requires hardware)

### Backend Changes

- ✅ Already done (see recent code commits):
  - `normalize_physical_card_id()` function
  - Gate endpoint accepts `physicalCardId` parameter
  - Feature gating logic in place

- **Database Migration:**
  ```sql
  -- Bulk assign physical_card_id from NFC reader during onboarding
  UPDATE workers SET physical_card_id = ? WHERE id = ?
  ```

### Frontend Changes

- ✅ Already done:
  - Turnstile UI matches both `physicalCardId` and `badgeId`
  - Worker app displays QR for gate scanning

- **Possible enhancement:**
  - Worker app: Show "Physical card registered" status badge

### Hardware / Gate Reader

- Install NFC reader at gate (if physical cards used)
- Reader sends `physicalCardId` (or `cardId` field) to backend
- Backend gate endpoint routes based on `scan_mode` parameter

### Worker Experience

**QR Path:**
1. Worker opens BauPass Worker app
2. Gate page shows QR code
3. Worker holds up phone to scanner
4. ✅ Gate opens

**Physical Card Path (if NFC cards distributed):**
1. Worker taps card on NFC reader at gate
2. ✅ Gate opens

### Platform Coverage

- ✅ iPhone (QR via camera/app)
- ✅ Android (QR via camera/app, NFC tap if card issued)
- ✅ Samsung (QR via camera/app, NFC tap if card issued)
- **No wallet integration yet** – not visible in native wallet UI

### Success Metrics

- QR gate access: 100% uptime
- Physical NFC (if deployed): <2% failure rate on tap
- User training time: <5 min per worker

### Rollout

1. **Week 1–2:** Physical card supplier agreement (if pursuing)
2. **Week 2–3:** Card printing & enrollment (assign `physical_card_id`)
3. **Week 3–4:** Install gate NFC reader; test with backend
4. **Week 4–6:** Pilot with subset of workers; full rollout

---

## Tier 2: Mid-Tier – Apple Wallet + Google Wallet

**Timeline:** 12–16 weeks  
**Effort:** Medium  
**Cost:** ~€15,000–25,000 (includes dev, PKI, services)

### What It Adds to Tier 1

1. **Apple Wallet Pass (iPhone)**
   - Worker taps phone on NFC reader (or shows pass + QR)
   - Native wallet UI displays employee card pass
   - Looks like bank card in Wallet app
   - **Requires:** Backend to generate PassKit `.pkpass` files, signed with company certificate

2. **Google Wallet Pass (Android)**
   - Similar to Apple Wallet on Android
   - Worker receives digital pass; adds to Wallet
   - Tap or display in native UI

3. **Unified Digital Card Experience**
   - Worker app no longer primary interface
   - Wallet is the single source of truth
   - Real-time updates (status, expiry, revocation)

### Backend Changes

**New Infrastructure:**

1. **Pass Generation Service**
   - Generate `.pkpass` files (Apple PassKit format)
   - Generate Google Wallet JWT tokens
   - Sign with company/operator certificate (PKI setup required)

2. **Pass Distribution**
   - Endpoint: `POST /api/worker-app/wallet/pass`
   - Returns PassKit or Google Wallet deeplink
   - Webhook for pass expiry/revocation

3. **Pass State Tracking**
   - Track which workers have activated pass in wallet
   - Expire/revoke passes when worker leaves
   - Real-time update notifications

**New Database Columns:**
```sql
ALTER TABLE workers ADD COLUMN wallet_pass_issued_at TEXT;
ALTER TABLE workers ADD COLUMN wallet_pass_revoked_at TEXT;
ALTER TABLE workers ADD COLUMN nfc_wallet_uid TEXT;  -- UID for NFC chip
```

### Frontend Changes

1. **Worker App:**
   - Add "Add to Wallet" button (Apple + Google)
   - Display pass status (active, expired, revoked)
   - Fallback to QR if wallet unavailable

2. **Admin Panel:**
   - Bulk issue/revoke passes
   - Monitor wallet adoption
   - View pass activation timeline

### Hardware / Gate Reader

- Upgrade to NFC reader that supports:
  - NFC Type 2/3/4 (standard)
  - Mobile wallet tap (if phones have NFC enabled)
  - QR fallback

- Reader integration:
  - Tap → extracts `nfc_wallet_uid` from pass
  - Or: Worker shows pass screen → manually scan QR

### PKI & Certificates

- **Apple:** Obtain WWDR certificate, create Team Identifier
- **Google:** Google Play services integration, API key setup
- **Company:** Create branded pass template (logo, colors)

### Worker Experience

**Apple Wallet (iPhone):**
1. Worker opens BauPass Worker app
2. Taps "Add to Wallet"
3. Pass appears in native Wallet app alongside bank cards
4. At gate: Tap phone on NFC reader (or double-tap screen)
5. ✅ Gate opens

**Google Wallet (Android):**
1. Worker opens BauPass Worker app
2. Taps "Add to Wallet"
3. Pass added to Google Wallet
4. At gate: Tap phone on NFC reader
5. ✅ Gate opens

**Fallback (QR if wallet unavailable):**
1. Worker opens BauPass Worker app
2. Shows QR code
3. Tap "Scan" at gate (manual QR)
4. ✅ Gate opens

### Platform Coverage

- ✅ iPhone: Native Apple Wallet + QR fallback
- ✅ Android: Native Google Wallet + QR fallback
- ✅ Samsung: Google Wallet (Samsung uses Android) + QR fallback
- **All workers have choice:** Native wallet or QR

### Database & Backend Effort

- **Tier 2 Backend:** ~400–600 hours
  - PassKit generation library integration
  - Google Wallet API client
  - Pass lifecycle management
  - Webhook & push notification setup
  - Database migrations

- **Testing:** E2E with real iPhone/Android devices

### Success Metrics

- Wallet pass adoption: >70% within 1 month
- NFC gate tap success rate: >95%
- QR fallback usage: <5% after 2 weeks
- Support tickets (pass issues): <2% of active users

### Rollout

1. **Week 1–4:** Set up PKI, Apple/Google API accounts, create pass templates
2. **Week 5–8:** Implement PassKit + Google Wallet backend; testing
3. **Week 9–12:** Beta with 20% of workers; refine based on feedback
4. **Week 12–16:** Full rollout; monitor pass activation & gate success

---

## Tier 3: Enterprise – Full Platform Coverage & Advanced Security

**Timeline:** 20–28 weeks  
**Effort:** High  
**Cost:** ~€40,000–70,000

### What It Adds to Tier 2

1. **Samsung Wallet (Samsung devices)**
   - Samsung devices running OneUI use their own Wallet
   - PassKit support varies; may require custom Samsung Pass integration
   - Or: Use Google Wallet (most Android users already use it)

2. **Advanced NFC Security**
   - Challenge-response authentication (ECDSA)
   - Time-bounded tokens (card UID changes hourly or per tap)
   - Encrypted NFC payload
   - Tamper detection on physical cards

3. **Hardware Integration (Optional)**
   - Biometric gate readers (fingerprint + NFC)
   - OSDP Controller integration (multi-reader gate systems)
   - IP-based gate devices (networked access control)

4. **Real-Time Access Control**
   - Dynamic pass revocation via push notification
   - Geofencing (gate only accessible during work hours)
   - Multi-factor at gate (NFC + PIN or biometric)

5. **Offline Mode**
   - Workers can authenticate even if gate reader loses connectivity
   - Local cache of valid UIDs + expiry
   - Periodic sync when connection restored

6. **Audit & Compliance**
   - Detailed access logs (timestamp, card UID, gate location, success/failure)
   - Tamper alerts (invalid card, duplicate UID)
   - Compliance reports (GDPR, data retention)

### Backend Changes

1. **Token Generation & Rotation**
   - Tokens expire after each use or fixed interval
   - Gate reader validates signature + timestamp
   - Revocation blacklist for immediate access denial

2. **Geofencing & Presence Detection**
   - Worker GPS during badge scan
   - Reject access outside work site + buffer zone

3. **Multi-Factor Authentication at Gate**
   - NFC + PIN (worker enters PIN on gate keypad)
   - NFC + Biometric (fingerprint reader)

4. **Samsung Wallet Integration**
   - Evaluate: PassKit support vs custom Samsung Pass API
   - Likely fallback to Google Wallet for Android (covers >90%)

### Database & Backend Effort

- **Tier 3 Backend:** ~600–1,000 hours
  - Token generation & rotation logic
  - Geofencing algorithms
  - Tamper detection & alerting
  - Offline cache synchronization
  - Compliance audit log engine

### Hardware Ecosystem

- OSDP-compatible gate controllers (e.g., Salto, Kaba, Allegion)
- Biometric readers (if multi-factor required)
- Encrypted NFC cards (DESFire, MIFARE Classic) instead of standard UID

### Worker Experience

**Premium Tier 3 Gate:**
1. Worker approaches gate
2. Holds up phone or card
3. NFC reader detects + validates signature
4. Multi-factor prompt if configured (e.g., "Enter PIN or scan fingerprint")
5. Real-time notification: ✅ "Access granted" or "❌ Access denied"
6. Gate opens (or biometric fails → deny)

**Geofencing:**
- Worker at home: Tap badge → "❌ Not at work site"
- Worker at site: Tap badge → ✅ Access granted

### Platform Coverage

- ✅ iPhone: Apple Wallet + advanced NFC + QR fallback
- ✅ Android: Google Wallet + optional Samsung Wallet + advanced NFC + QR fallback
- ✅ Samsung: Samsung Wallet (if implemented) + Google Wallet + advanced NFC + QR fallback
- **All workers supported; no exclusions**

### Success Metrics

- NFC gate success rate: >98%
- Token validity: 100% (no replay attacks)
- Offline mode uptime: 99.9%
- Tamper detection accuracy: >99%
- Compliance audit log completeness: 100%

### Rollout

1. **Week 1–4:** Evaluate Samsung Wallet feasibility; design token rotation scheme
2. **Week 5–12:** Implement backend (token gen, geofencing, multi-factor)
3. **Week 13–16:** Integrate OSDP controllers or biometric readers
4. **Week 17–20:** Comprehensive testing (all platforms, all gate types)
5. **Week 21–28:** Beta with enterprise customer; full rollout + training

---

## Implementation Roadmap & Sequencing

### Phase 1: Solidify Tier 1 (Weeks 1–6)

**Goals:**
- Confirm QR gate access 100% reliable
- Issue physical NFC cards to subset (pilot: 20 workers)
- Test NFC reader integration with backend

**Deliverables:**
- Physical cards to 20 workers
- NFC reader at pilot gate
- `physical_card_id` assigned in database
- Backend gate tests passing

**Go/No-Go Decision:** If NFC success rate >90%, proceed to Tier 2.

---

### Phase 2: Launch Tier 1 Fully (Weeks 6–12)

**Goals:**
- Issue physical cards to remaining workers (if applicable)
- Train all workers on QR + physical card access
- Establish 24/7 gate uptime

**Deliverables:**
- 100% of workers have access option (QR or NFC)
- Support playbook for common issues
- Metrics dashboard (gate success rate, failure modes)

---

### Phase 3: Begin Tier 2 Development (Weeks 8–24, parallel with Phase 2)

**Goals:**
- Set up Apple + Google wallet infrastructure
- Implement PassKit generation
- Beta with iPhone + Android users

**Deliverables:**
- Tier 2 backend (PassKit + Google Wallet)
- Worker app "Add to Wallet" button
- Beta results report

**Go/No-Go Decision:** If wallet adoption >60% in beta, proceed to full Tier 2 rollout.

---

### Phase 4: Deploy Tier 2 (Weeks 24–40)

**Goals:**
- Roll out wallet passes to all workers
- Monitor adoption curve
- Reduce QR usage

**Deliverables:**
- >70% wallet adoption
- <5% QR fallback usage
- Minimal support tickets

---

### Phase 5: Plan Tier 3 (Weeks 30–50, optional)

**Goals:**
- Evaluate enterprise add-ons (Samsung Wallet, advanced NFC)
- Design token rotation & geofencing
- Identify early adopters for Tier 3 pilot

**Deliverables:**
- Tier 3 technical specification
- Cost-benefit analysis
- Pilot customer commitment (if pursuing)

---

### Phase 6: Optional Tier 3 Rollout (Weeks 50+)

**Goals:**
- Implement advanced security & platform coverage
- Deploy to enterprise customers
- Establish compliance audit trail

**Deliverables:**
- Tier 3 backend live
- First customers on advanced NFC + geofencing
- Compliance reports (SOC2, GDPR)

---

## Cost Summary by Tier

| Tier | Development | Hardware | Services | Total | Timeline |
|------|-------------|----------|----------|-------|----------|
| **Tier 1** | €3k–5k | €2k–4k (cards) | €0 | €5k–9k | 6 weeks |
| **Tier 2** | €15k–20k | €2k–3k | €3k–7k (Apple/Google/PKI) | €20k–30k | 16 weeks |
| **Tier 3** | €30k–50k | €5k–10k (advanced readers) | €5k–15k (advanced services) | €40k–75k | 28 weeks |

---

## Risk Mitigation

| Risk | Tier 1 | Tier 2 | Tier 3 |
|------|--------|--------|---------|
| **Hardware failure** | QR fallback | QR fallback | QR + offline cache |
| **API downtime (Apple/Google)** | N/A | Pass still works offline | Pass + offline cache |
| **Worker adoption** | Forced (no wallet) | Optional (QR fallback) | Optional (QR fallback) |
| **Security breach** | Card UID exposure | Pass interception risk | Mitigated by token rotation + ECDSA |
| **Platform exclusion** | None (QR universal) | None (QR fallback) | None (QR fallback) |

---

## Recommendation

### For Most Customers: Tier 1 → Tier 2

1. **Start with Tier 1** (6 weeks):
   - Quick win: Operational QR + optional physical cards
   - Low risk, fast delivery
   - Establish baseline metrics

2. **Move to Tier 2** (16 weeks) after Tier 1 stabilizes:
   - Native wallet integration (best UX for iPhone + Android)
   - High adoption expected (users already use Apple/Google Wallet)
   - Minimal additional backend complexity vs. benefit

3. **Evaluate Tier 3** case-by-case:
   - Only if enterprise customer demands advanced security
   - Or if geofencing + biometric are differentiators
   - High cost for modest incremental gain

### For Enterprise Customers: Full Tier 2 + Selective Tier 3

1. **Tier 2 mandatory** (all enterprise):
   - Professional appearance (native wallet)
   - Wide platform coverage
   - Standard for enterprise SaaS

2. **Tier 3 opt-in** (high-security use cases):
   - Government, military, high-security sites
   - Biometric + geofencing justifiable
   - Custom NFC cards (DESFire) for advanced protocol

---

## Principle: No User Exclusion

**This architecture ensures:**

✅ **Every worker can access gates** regardless of device type  
✅ **iPhone users** have Apple Wallet option (best experience)  
✅ **Android users** have Google Wallet option (native experience)  
✅ **Samsung users** covered by Google Wallet (standard on Samsung devices)  
✅ **No phone users** can use physical card (if issued)  
✅ **All users** have QR fallback (universal, offline, works everywhere)  

**Result:** 100% platform coverage; zero user exclusion based on device or OS choice.

---

## Next Steps

1. **Approve Tier 1 continuation** or adjust timeline
2. **Confirm physical card supplier** (if pursuing NFC in Tier 1)
3. **Schedule Tier 2 planning** (Apple/Google PKI setup)
4. **Establish success metrics** for gate uptime, adoption, support load
5. **Set customer communication** plan (explain wallet adoption roadmap)

---

**Document Owner:** Product Architecture  
**Last Updated:** May 2026  
**Review Cycle:** Q3 2026 (post-Tier 2 launch)
