# PassKit Python Library Evaluation

**Goal:** Select the best Python library for generating Apple Wallet (`.pkpass`) and Google Wallet passes.

---

## Comparison Matrix

| Criteria | pypasskit | passkit-python | google-wallet-python | Hybrid (pypasskit + REST API) |
|----------|-----------|------------------|----------------------|-------------------------------|
| **Apple Wallet Support** | ✅ Excellent | ✅ Good | ❌ None | ✅ Excellent |
| **Google Wallet Support** | ❌ None | ✅ SDK | ⚠️ REST API only | ✅ Good (REST API) |
| **Pass Signing** | ✅ Native | ✅ SDK | N/A | ✅ Native (Apple) |
| **Barcode/QR Support** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Pass Updates/Versioning** | ✅ Good | ✅ Good | ✅ Yes | ✅ Good |
| **Documentation** | ✅ Good | ⚠️ Limited | ✅ Excellent | ⚠️ Need to combine docs |
| **Community Activity** | ✅ Active | ⚠️ Moderate | ✅ Active | - |
| **License** | ✅ MIT | ⚠️ Proprietary | ✅ Apache 2.0 | - |
| **Cost** | 🆓 Free | 💰 $$$ | 🆓 Free | 🆓 Free |
| **Python 3.8+ Support** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Implementation Complexity** | 🟢 Low | 🟢 Low | 🟡 Medium | 🟡 Medium |
| **Maintenance Burden** | 🟢 Low | 🟢 Low | 🟡 Medium | 🟡 Medium |

---

## Candidate Evaluation

### 1. pypasskit (Recommended for Phase 1)

**Repository:** https://github.com/walletpass/pypasskit  
**License:** MIT (Open Source)  
**Installation:** `pip install pypasskit`  

#### Strengths:
- ✅ **Pure Python implementation** — no external dependencies
- ✅ **Apple Wallet native support** — industry standard for `.pkpass` generation
- ✅ **Simple API** — generates passes in 5–10 lines of code
- ✅ **Barcode/QR embedding** — native support for badge codes
- ✅ **Pass signing** — handles cryptographic signing automatically
- ✅ **Active development** — regularly maintained
- ✅ **Great documentation** — examples and tutorials available
- ✅ **MIT Licensed** — permissive open-source license

#### Weaknesses:
- ❌ **No Google Wallet support** — requires separate integration
- ⚠️ **Limited pass updates** — works for single-version passes

#### Best For:
- Apple Wallet passes (primary use case for Phase 1)
- Developers who prefer simplicity

#### Code Example:
```python
from pypasskit import PKPass

# Create pass
p = PKPass()
p.addMetaData(
    name="BauPass Badge",
    organizationName="Baukometra",
    teamIdentifier="ABCD1EF2GH",
    passTypeIdentifier="pass.baukometra.baupass"
)
p.addPrimaryField(
    key="name",
    label="Worker Name",
    value="Max Müller"
)
p.addSecondaryField(
    key="badge_id",
    label="Badge ID",
    value="W-12345"
)
p.addBarcode(
    message="W-12345",
    format="PKBarcodeFormatQR"
)

# Sign and export
p.create(
    certificates=["path/to/cert.p12"],
    password="cert-password",
    outputFile="pass.pkpass"
)
```

#### Recommendation: ⭐ **Use for Apple Wallet (Phase 1)**

---

### 2. passkit-python (Passkit SDK)

**Repository:** https://developer.passkit.io/  
**License:** Proprietary  
**Installation:** Contact Passkit for SDK  

#### Strengths:
- ✅ **Official Passkit SDK** — vendor-backed
- ✅ **Both Apple + Google support** — unified API
- ✅ **Pass management** — lifecycle tracking, updates, revocation
- ✅ **Analytics** — usage metrics and engagement
- ✅ **Cloud storage** — passes managed server-side

#### Weaknesses:
- ❌ **Proprietary cost** — $$$, commercial licensing
- ❌ **Vendor lock-in** — requires Passkit service
- ❌ **Limited documentation** — requires SDK tutorials
- ⚠️ **Overkill for BauPass** — more features than needed

#### Best For:
- Enterprise pass management
- Organizations needing advanced analytics

#### Recommendation: ❌ **Not recommended for Phase 1 (cost, complexity)**

---

### 3. google-wallet-python (Google Samples)

**Repository:** https://github.com/google-pay/google-wallet-samples/tree/main/python  
**License:** Apache 2.0  
**Installation:** Not a pip package; custom integration  

#### Strengths:
- ✅ **Official Google samples** — authoritative implementation
- ✅ **Google Wallet native** — uses official REST API
- ✅ **Well documented** — Google's documentation
- ✅ **Flexible** — pure REST API calls

#### Weaknesses:
- ❌ **No Apple Wallet support** — Google-only
- ❌ **Not packaged as library** — requires custom integration
- ❌ **Lower-level API** — more boilerplate code
- ⚠️ **Manual pass creation** — less abstraction

#### Best For:
- Google Wallet-only solutions
- Developers comfortable with REST APIs

#### Recommendation: ⚠️ **Possibly combine with pypasskit for Phase 2**

---

### 4. Hybrid Approach (Recommended for Full Phase 2)

**Strategy:** Use `pypasskit` for Apple + custom Google Wallet REST API integration

#### Architecture:
```
Backend Service
│
├─ Apple Wallet (pypasskit)
│  ├─ Generate .pkpass file
│  ├─ Sign with Apple certificate
│  └─ Serve to frontend
│
└─ Google Wallet (REST API + JWT)
   ├─ Generate JWT token
   ├─ Sign with Google Service Account private key
   └─ Return wallet URL to frontend
```

#### Strengths:
- ✅ **Best of both worlds** — native for each platform
- ✅ **Full control** — no vendor lock-in
- ✅ **Simple dependencies** — pypasskit + standard Python libs
- ✅ **Scalable** — efficient for 100–1000 workers
- ✅ **Cost-effective** — free tier sufficient

#### Weaknesses:
- ⚠️ **Integration work** — combine two separate approaches
- ⚠️ **Documentation** — need to reference two sources
- ⚠️ **Maintenance** — manage both code paths

#### Implementation (Overview for Phase 2):
```python
# Apple Wallet (pypasskit)
def generate_apple_pass(worker_data):
    p = PKPass()
    # ... populate with worker_data
    return p.create(...)  # Returns .pkpass binary

# Google Wallet (REST API + JWT)
def generate_google_pass(worker_data):
    claims = {
        "iss": service_account_email,
        "aud": "google",
        "origins": ["localhost"],
        "typ": "savetowallet",
        "payload": {
            "genericObjects": [{
                "id": issuer_id + ".W-12345",
                "classId": issuer_id + ".baukometra_worker",
                "classReference": {/* pass class definition */},
                "objectReferences": [{/* object data */}]
            }]
        }
    }
    token = jwt.encode(claims, private_key, algorithm="RS256")
    return f"https://pay.google.com/gp/v/save/{token}"
```

#### Recommendation: ⭐⭐ **Use for Phase 2 (Full implementation)**

---

## Recommendation for Phase 1 & 2

### Phase 1 (Weeks 1–2): Setup Only
**Decision:** Select **pypasskit** for development + testing framework

**Rationale:**
- Simplest to integrate with Flask backend
- Focus Phase 1 on infrastructure (Apple certs, Google API, database)
- Delay Google integration until Phase 2

**Installation:**
```bash
pip install pypasskit
```

### Phase 2 (Weeks 3–6): Backend Implementation
**Decision:** Implement **hybrid approach** (pypasskit + Google REST API)

**Additional Packages:**
```bash
pip install pyjwt cryptography  # For Google JWT signing
```

### Phase 3 (Weeks 7+): Frontend Integration
**Decision:** Add "Add to Wallet" buttons for both platforms

---

## Installation & Testing

### Step 1: Install pypasskit

```bash
# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\Activate.ps1  # Windows

# Install
pip install pypasskit
```

### Step 2: Create Test Pass (Simple Verification)

```python
# test_passkit.py
from pypasskit import PKPass

def test_simple_pass():
    p = PKPass()
    p.addMetaData(
        name="Test Badge",
        organizationName="Baukometra",
        teamIdentifier="ABCD1EF2GH",  # Your Team ID
        passTypeIdentifier="pass.baukometra.baupass"  # Your Pass Type ID
    )
    p.addPrimaryField(key="name", label="Name", value="Test User")
    p.addBarcode(message="12345", format="PKBarcodeFormatQR")
    
    # Note: Actual signing requires certificates (see Phase 2)
    print("✅ Pass structure created successfully")
    return p

if __name__ == "__main__":
    test_simple_pass()
```

**Run:** `python test_passkit.py`  
**Expected:** No errors, confirms library installation

---

## Decision Matrix (Final)

```
Question                          Answer               Implication
─────────────────────────────────────────────────────────────────────
Use one library or hybrid?        Hybrid              Best long-term
Start with what?                  pypasskit (Apple)   Phase 1 focus
Add Google Wallet when?           Phase 2             After Apple proven
Keep in-house or use vendor?      In-house            Control + cost
```

---

## Next Steps

1. **Phase 1:** Install `pypasskit`, set up test environment
2. **Phase 1:** Complete Apple Developer setup (see `docs/apple-wallet-setup-guide.md`)
3. **Phase 1:** Document Google Wallet setup (see `docs/google-wallet-setup-guide.md`)
4. **Phase 2:** Implement pass generation endpoints
5. **Phase 2:** Integrate Google Wallet via REST API + JWT
6. **Phase 3:** Frontend "Add to Wallet" buttons

---

## Additional Resources

- **pypasskit Docs:** https://github.com/walletpass/pypasskit/wiki
- **Apple PassKit Intro:** https://developer.apple.com/wallet/
- **Google Wallet API:** https://developers.google.com/wallet/generic
- **Pass File Format:** https://developer.apple.com/library/archive/documentation/UserExperience/Reference/PassKit_Bundle/Chapters/Introduction.html

