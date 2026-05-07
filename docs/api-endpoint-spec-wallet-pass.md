# API Endpoint Specification: Wallet Pass Generation

**Goal:** Define the API endpoint for workers to request and download wallet passes (Apple Wallet, Google Wallet).

---

## Endpoint Overview

**Purpose:** Deliver wallet passes to authenticated worker users.

**Base URL:** `https://baupass.local/api/worker-app/`

**Endpoints:**
- `GET /api/worker-app/wallet/pass` — Request a wallet pass
- `POST /api/worker-app/wallet/pass/webhook` — Webhook from Apple/Google (Phase 2+)

---

## Endpoint 1: GET `/api/worker-app/wallet/pass`

### Request

**Method:** `GET`

**URL:**
```
/api/worker-app/wallet/pass?platform=apple
```

**Query Parameters:**

| Parameter | Type | Required | Values | Description |
|-----------|------|----------|--------|-------------|
| `platform` | string | ✅ Yes | `apple`, `google` | Which wallet platform |
| `force_regenerate` | boolean | ❌ No | `true`, `false` | Force rebuild pass from current worker data |

**Headers:**

```
Authorization: Bearer {WORKER_SESSION_TOKEN}
Content-Type: application/json
```

**Body:** None (GET request)

### Response: Success (200 OK)

#### Apple Wallet Response

```json
{
  "status": "success",
  "platform": "apple",
  "pass_url": "https://baupass.local/passes/apple/W-12345-v1.pkpass",
  "pass_id": "pass-550e8400-e29b-41d4-a716-446655440000",
  "object_id": "W-12345-v1",
  "state": "issued",
  "message": "Pass ready. Click button below to add to Apple Wallet."
}
```

#### Google Wallet Response

```json
{
  "status": "success",
  "platform": "google",
  "pass_url": "https://baupass.local/passes/google/redirect?pass_id=W-12345-v1",
  "add_to_wallet_url": "https://pay.google.com/gp/v/save/eyJhbGciOiJSUzI1NiIs...",
  "pass_id": "pass-660f9511-f40c-52e5-b827-557776551111",
  "object_id": "W-12345-v1",
  "state": "issued",
  "message": "Pass ready. Click button below to add to Google Wallet."
}
```

**Response Headers:**

```
Content-Type: application/json
Cache-Control: private, max-age=60
```

### Response: Errors

#### 401 Unauthorized
**When:** Worker session token missing, invalid, or expired

```json
{
  "status": "error",
  "code": "unauthorized",
  "message": "Worker session expired. Please log in again."
}
```

**HTTP Status:** `401 Unauthorized`

---

#### 403 Forbidden
**When:** Company doesn't have wallet feature enabled

```json
{
  "status": "error",
  "code": "feature_not_available",
  "message": "Wallet passes are not enabled for your company. Contact support.",
  "feature": "wallet_passes",
  "plan": "starter"
}
```

**HTTP Status:** `403 Forbidden`

---

#### 400 Bad Request
**When:** Invalid query parameter

```json
{
  "status": "error",
  "code": "invalid_platform",
  "message": "Platform must be 'apple' or 'google'.",
  "provided": "windows"
}
```

**HTTP Status:** `400 Bad Request`

---

#### 404 Not Found
**When:** Worker record not found (deleted or invalid)

```json
{
  "status": "error",
  "code": "worker_not_found",
  "message": "Worker account not found or has been deleted."
}
```

**HTTP Status:** `404 Not Found`

---

#### 422 Unprocessable Entity
**When:** Worker data invalid (e.g., missing badge_id)

```json
{
  "status": "error",
  "code": "invalid_worker_data",
  "message": "Cannot generate pass: worker missing badge ID.",
  "details": {
    "missing_fields": ["badge_id"]
  }
}
```

**HTTP Status:** `422 Unprocessable Entity`

---

#### 500 Internal Server Error
**When:** Pass generation fails (certificate error, signing failure, etc.)

```json
{
  "status": "error",
  "code": "pass_generation_failed",
  "message": "Failed to generate wallet pass. The system administrator has been notified.",
  "error_id": "err-2024-05-06-14:30:00-abc123",
  "details": {
    "platform": "apple",
    "step": "signing",
    "reason": "Certificate expired"
  }
}
```

**HTTP Status:** `500 Internal Server Error`

---

## Implementation Details (Backend Logic)

### Step-by-Step Processing

```
1. Validate Request
   ├─ Check Authorization header (Bearer token)
   ├─ Verify worker session exists and not expired
   ├─ Load worker from database
   └─ Verify worker not deleted

2. Check Permissions
   ├─ Get company from worker.company_id
   ├─ Verify company not suspended
   ├─ Check if wallet_passes_enabled for company
   ├─ Check if platform-specific feature enabled
   │   (wallet_apple_enabled or wallet_google_enabled)
   └─ Verify worker.status is 'aktiv' (active)

3. Check Existing Pass
   ├─ Query worker_passes table
   ├─ Find pass with (worker_id, platform)
   └─ If exists:
       ├─ If force_regenerate: delete old, create new
       └─ Else: return cached pass

4. Generate Pass
   ├─ If platform == 'apple':
   │   ├─ Call generate_apple_pass(worker, company)
   │   ├─ Sign with Apple certificate
   │   └─ Save .pkpass binary to temp storage
   │
   └─ If platform == 'google':
       ├─ Call generate_google_pass(worker, company)
       ├─ Sign JWT token with Service Account key
       └─ Generate redirect URL

5. Store in Database
   ├─ Create worker_passes record
   ├─ Set status = 'issued'
   ├─ Store pass_url
   ├─ Store pass_data_json (for auditing)
   └─ Set issued_at = now()

6. Return Response
   ├─ If Apple: return .pkpass download URL
   ├─ If Google: return JWT token + add-to-wallet URL
   └─ Send 200 OK with pass details
```

### Code Skeleton (Flask)

```python
@app.get("/api/worker-app/wallet/pass")
@require_worker_session
def get_wallet_pass():
    # 1. Parse query parameters
    platform = request.args.get("platform", "").strip().lower()
    force_regenerate = request.args.get("force_regenerate", "false").lower() == "true"
    
    # Validate platform
    if platform not in ["apple", "google"]:
        return jsonify({
            "status": "error",
            "code": "invalid_platform",
            "message": "Platform must be 'apple' or 'google'."
        }), 400
    
    # 2. Get worker from g (set by @require_worker_session)
    worker = g.worker
    db = get_db()
    
    # 3. Check company & feature enabled
    company = db.execute(
        "SELECT * FROM companies WHERE id = ?",
        (worker["company_id"],)
    ).fetchone()
    
    if not company:
        return jsonify({
            "status": "error",
            "code": "company_not_found"
        }), 404
    
    # Check feature flags
    settings = db.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if not settings or not settings["wallet_passes_enabled"]:
        return feature_not_available_response("wallet_passes", ...)
    
    # 4. Check existing pass (unless force regenerate)
    if not force_regenerate:
        existing_pass = db.execute(
            "SELECT * FROM worker_passes WHERE worker_id = ? AND platform = ? AND status IN ('issued', 'active')",
            (worker["id"], platform)
        ).fetchone()
        
        if existing_pass:
            return jsonify({
                "status": "success",
                "platform": platform,
                "pass_url": existing_pass["pass_url"],
                "state": existing_pass["status"],
                ...
            }), 200
    
    # 5. Generate new pass
    try:
        if platform == "apple":
            pass_data = generate_apple_pass(worker, company, settings)
            pass_url = store_apple_pass(pass_data, worker)
        elif platform == "google":
            jwt_token = generate_google_pass_jwt(worker, company, settings)
            pass_url = f"https://pay.google.com/gp/v/save/{jwt_token}"
    except Exception as e:
        # Log error
        return jsonify({
            "status": "error",
            "code": "pass_generation_failed",
            "message": "Failed to generate wallet pass."
        }), 500
    
    # 6. Store in database
    pass_id = f"pass-{uuid.uuid4()}"
    pass_obj_id = f"{worker['badge_id']}-v1"
    
    db.execute("""
        INSERT INTO worker_passes
        (id, worker_id, company_id, pass_type, platform, pass_class_id,
         pass_object_id, status, pass_data_json, pass_url, issued_at, last_updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        pass_id, worker["id"], company["id"], "badge", platform,
        "pass.baukometra.baupass" if platform == "apple" else "3388655000022476551.baukometra_worker",
        pass_obj_id, "issued", json.dumps(pass_data), pass_url,
        now_iso(), now_iso()
    ))
    db.commit()
    
    # 7. Return success response
    response = {
        "status": "success",
        "platform": platform,
        "pass_url": pass_url,
        "pass_id": pass_id,
        "state": "issued"
    }
    
    if platform == "google":
        response["add_to_wallet_url"] = pass_url  # Google Wallet add button
    
    return jsonify(response), 200
```

---

## Pass Delivery Methods

### Apple Wallet (`.pkpass` Binary)

**Method 1: Direct Download (Recommended)**
- Worker downloads `.pkpass` file
- File opens in Wallet app (iOS/macOS)
- Prompts: "Add to Apple Wallet?"

**URL Format:**
```
https://baupass.local/passes/apple/W-12345-v1.pkpass
```

**Frontend (JavaScript):**
```javascript
async function downloadApplePass() {
    const response = await fetch("/api/worker-app/wallet/pass?platform=apple", {
        method: "GET",
        headers: { "Authorization": `Bearer ${sessionToken}` }
    });
    const data = await response.json();
    
    if (data.status === "success") {
        // Create download link
        const link = document.createElement("a");
        link.href = data.pass_url;
        link.download = "badge.pkpass";
        link.click();
    }
}
```

### Google Wallet (JWT Token)

**Method 1: Add to Wallet Button (Recommended)**
- Click button triggers: `window.location.href = add_to_wallet_url`
- Redirects to Google Wallet app / web
- Prompts: "Add this pass?"

**URL Format:**
```
https://pay.google.com/gp/v/save/{JWT_TOKEN}
```

**Frontend (JavaScript):**
```javascript
async function addToGoogleWallet() {
    const response = await fetch("/api/worker-app/wallet/pass?platform=google", {
        method: "GET",
        headers: { "Authorization": `Bearer ${sessionToken}` }
    });
    const data = await response.json();
    
    if (data.status === "success") {
        // Redirect to Google Wallet
        window.location.href = data.add_to_wallet_url;
    }
}
```

---

## Rate Limiting

**Goal:** Prevent pass generation abuse (e.g., spam requests).

**Limits:**

| Endpoint | Limit | Window |
|----------|-------|--------|
| `/api/worker-app/wallet/pass` | 10 requests | 1 minute per worker |
| (General worker app) | 30 requests | 1 minute per worker |

**Implementation:**

```python
# In Flask middleware
@app.before_request
def check_worker_rate_limit():
    if request.path == "/api/worker-app/wallet/pass":
        worker_id = g.worker.get("id") if hasattr(g, "worker") else None
        if worker_id:
            if not check_rate_limit(f"worker_pass:{worker_id}"):
                return jsonify({"error": "rate_limit_exceeded"}), 429
```

---

## Testing Scenarios (Phase 2)

### Test 1: Happy Path (Apple Wallet)
```
GET /api/worker-app/wallet/pass?platform=apple
→ 200 OK with pass_url
```

### Test 2: Happy Path (Google Wallet)
```
GET /api/worker-app/wallet/pass?platform=google
→ 200 OK with add_to_wallet_url
```

### Test 3: Invalid Platform
```
GET /api/worker-app/wallet/pass?platform=samsung
→ 400 Bad Request
```

### Test 4: Unauthorized (No Token)
```
GET /api/worker-app/wallet/pass?platform=apple
(no Authorization header)
→ 401 Unauthorized
```

### Test 5: Feature Disabled
```
GET /api/worker-app/wallet/pass?platform=apple
(company has wallet_passes_enabled=0)
→ 403 Forbidden
```

### Test 6: Force Regenerate
```
GET /api/worker-app/wallet/pass?platform=apple&force_regenerate=true
→ 200 OK with new pass (version incremented)
```

---

## Webhook Endpoints (Phase 2+)

**Purpose:** Receive notifications from Apple/Google when pass added to wallet.

### Endpoint 2: POST `/api/worker-app/wallet/pass/webhook`

**When:** User adds pass to Apple Wallet or Google Wallet

**Apple Webhook:**
```json
{
  "passTypeIdentifier": "pass.baukometra.baupass",
  "serialNumbers": ["W-12345-v1"],
  "updatedFields": []
}
```

**Google Webhook:**
```json
{
  "eventType": "OBJECT_STATE_CHANGE",
  "objectId": "W-12345-v1",
  "classId": "3388655000022476551.baukometra_worker",
  "state": "ACTIVE"
}
```

**Backend Logic:**
```python
@app.post("/api/worker-app/wallet/pass/webhook")
def handle_pass_webhook():
    # 1. Verify webhook signature (Apple/Google specific)
    # 2. Parse webhook payload
    # 3. Update worker_passes status to 'active'
    # 4. Log in audit trail
    # 5. Return 200 OK
```

**Details:** To be implemented in Phase 2 when Apple/Google integration is live.

---

## Next Steps

1. **Phase 1:** Review spec with team
2. **Phase 2:** Implement endpoint in Flask
3. **Phase 2:** Create test suite (unit + integration)
4. **Phase 2:** Implement webhook receivers
5. **Phase 3:** Create frontend UI (buttons, modals)

