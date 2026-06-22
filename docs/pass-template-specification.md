# Pass Template Specification (Apple Wallet + Google Wallet)

**Goal:** Define visual design and data structure for worker badge passes on both platforms.

---

## Overview

A wallet pass contains:
- **Visual elements** (logos, colors, images)
- **Data fields** (worker name, badge ID, company, validity)
- **Barcode/QR code** (for gate access fallback)
- **Metadata** (issuer, valid dates, type)

This document specifies the design for both Apple Wallet (`.pkpass`) and Google Wallet.

---

## Apple Wallet Pass Specification

### Pass Type: Generic Card

**Format:** Generic card (horizontal layout, similar to boarding pass)

```
┌────────────────────────────────────────────────────┐
│ [LOGO]  Suppix Technologie UG WorkPass  [COMPANY ICON]        │
├────────────────────────────────────────────────────┤
│ PRIMARY FIELD:                                     │
│ Max Müller                                         │
├────────────────────────────────────────────────────┤
│ Badge ID: W-12345   |   Valid Until: 31.12.2026  │
│ Company: Bau GmbH   |   Status: Active             │
├────────────────────────────────────────────────────┤
│                                                    │
│  ┌──────────────────┐                             │
│  │  ████████████    │   QR Code for fallback      │
│  │  ████████████    │   (Badge ID + checksum)     │
│  │  ████████████    │                             │
│  └──────────────────┘                             │
│                                                    │
└────────────────────────────────────────────────────┘
```

### Visual Assets (Apple Wallet)

#### 1. Logo
- **Purpose:** Top-left corner of pass
- **Filename:** `logo.png`
- **Size:** 320×320 pixels
- **Format:** PNG with transparency (RGBA)
- **Color:** Suppix Technologie UG brand color (primary color from `invoice_primary_color`, default `#c78652`)
- **Content:** Suppix Technologie UG logo, centered, white background

#### 2. Thumbnail
- **Purpose:** Small preview (lock screen, notification)
- **Filename:** `thumbnail.png`
- **Size:** 86×86 pixels
- **Format:** PNG with transparency (RGBA)
- **Content:** Simplified logo or badge icon

#### 3. Icon
- **Purpose:** Very small icon (Apple Watch, lock screen corner)
- **Filename:** `icon.png`
- **Size:** 29×29 pixels
- **Format:** PNG with transparency (RGBA)
- **Content:** Letter "W" or badge symbol

#### 4. Strip Image (Optional)
- **Purpose:** Top header band behind company name
- **Filename:** `strip.png`
- **Size:** 812×228 pixels
- **Format:** PNG
- **Content:** Company branding background (e.g., construction site photo)

#### 5. Background Color
- **Primary Color:** `#c78652` (Suppix Technologie UG orange)
- **Secondary Color:** `#8a5230` (Darker brown)
- **Text Color:** White (`#FFFFFF`) or light gray (`#f6efe2`)

### Apple Pass JSON Structure

**File:** `pass.json` (inside `.pkpass` bundle)

```json
{
  "formatVersion": 1,
  "passTypeIdentifier": "pass.baukometra.baupass",
  "serialNumber": "W-12345-v1",
  "teamIdentifier": "ABCD1EF2GH",
  "organizationName": "Suppix Technologie UG",
  "description": "WorkPass Worker Badge",
  "logoText": "WorkPass",
  
  "generic": {
    "primaryFields": [
      {
        "key": "worker_name",
        "label": "Worker",
        "value": "Max Müller",
        "textAlignment": "PKTextAlignmentCenter"
      }
    ],
    "secondaryFields": [
      {
        "key": "company",
        "label": "Company",
        "value": "Bau GmbH",
        "textAlignment": "PKTextAlignmentLeft"
      },
      {
        "key": "status",
        "label": "Status",
        "value": "Active",
        "textAlignment": "PKTextAlignmentRight"
      }
    ],
    "auxiliaryFields": [
      {
        "key": "badge_id",
        "label": "Badge ID",
        "value": "W-12345",
        "textAlignment": "PKTextAlignmentLeft"
      },
      {
        "key": "valid_until",
        "label": "Valid Until",
        "value": "31.12.2026",
        "textAlignment": "PKTextAlignmentRight",
        "dateStyle": "PKDateStyleShort"
      }
    ],
    "footerFields": [
      {
        "key": "instructions",
        "label": "",
        "value": "Present this pass at any gate for access"
      }
    ]
  },
  
  "barcodes": [
    {
      "format": "PKBarcodeFormatQR",
      "message": "W-12345-CHECKSUM",
      "messageEncoding": "iso-8859-1",
      "label": "Badge ID"
    }
  ],
  
  "backgroundColor": "rgb(199, 134, 82)",
  "foregroundColor": "rgb(255, 255, 255)",
  "labelColor": "rgb(246, 239, 226)",
  
  "relevantDate": "2026-12-31T23:59:59Z",
  "expirationDate": "2026-12-31T23:59:59Z",
  "voided": false,
  
  "webServiceURL": "https://baupass.example.com/api/passes/apple/",
  "authenticationToken": "{PASS_AUTH_TOKEN}",
  
  "associatedStoreIdentifiers": []
}
```

### Barcode Format (Apple Wallet)

**Type:** QR Code  
**Content:** Badge ID + validation checksum

```
Format: {BADGE_ID}-{CHECKSUM}
Example: W-12345-AB7C

Checksum Algorithm (Luhn):
  - Take badge ID numeric part (12345)
  - Apply Luhn algorithm → checksum
  - Append to QR code message
```

**Implementation (Python):**
```python
def luhn_checksum(badge_id):
    """Generate Luhn checksum for badge ID"""
    digits = str(badge_id).replace("W-", "")
    def digits_of(n):
        return [int(d) for d in str(n)]
    digits = digits_of(digits)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d*2))
    return ((10 - (checksum % 10)) % 10)

# Usage:
badge_id = "W-12345"
checksum = luhn_checksum(badge_id)
qr_content = f"{badge_id}-{checksum:02d}"  # "W-12345-23"
```

---

## Google Wallet Pass Specification

### Pass Type: Generic Class

**Format:** Generic pass (flexible layout)

### Google Wallet Pass Class (Template)

**File:** `genericClass.json` (created once, used for all worker passes)

```json
{
  "id": "3388655000022476551.baukometra_worker",
  "issuerName": "Suppix Technologie UG",
  "displayName": "WorkPass Worker Badge",
  "reviewStatus": "UNDER_REVIEW",
  "multipleDevicesAndHoldersAllowedStatus": "MULTIPLE_USERS",
  
  "hexBackgroundColor": "#c78652",
  "textModulesData": [
    {
      "id": "instructions",
      "header": "Instructions",
      "body": "Present this pass at any gate for access. You can also scan your QR code as a fallback."
    }
  ],
  
  "imageModulesData": [
    {
      "id": "badge_logo",
      "mainImage": {
        "kind": "walletobjects#image",
        "sourceUri": {
          "uri": "https://baupass.example.com/static/wallet/logo.png"
        }
      }
    }
  ],
  
  "fields": {
    "worker_name": {
      "label": "Worker Name"
    },
    "badge_id": {
      "label": "Badge ID"
    },
    "company": {
      "label": "Company"
    },
    "valid_until": {
      "label": "Valid Until"
    },
    "status": {
      "label": "Status"
    }
  }
}
```

### Google Wallet Pass Object (Instance)

**Generated per worker**

```json
{
  "id": "3388655000022476551.W-12345-v1",
  "classId": "3388655000022476551.baukometra_worker",
  "state": "ACTIVE",
  
  "textModulesData": [
    {
      "id": "worker_name",
      "header": "Worker",
      "body": "Max Müller"
    },
    {
      "id": "badge_id",
      "header": "Badge ID",
      "body": "W-12345"
    },
    {
      "id": "company",
      "header": "Company",
      "body": "Bau GmbH"
    },
    {
      "id": "valid_until",
      "header": "Valid Until",
      "body": "31.12.2026"
    },
    {
      "id": "status",
      "header": "Status",
      "body": "Active"
    }
  ],
  
  "barcode": {
    "type": "QR_CODE",
    "value": "W-12345-CHECKSUM"
  },
  
  "hexBackgroundColor": "#c78652",
  "heroImage": {
    "sourceUri": {
      "uri": "https://baupass.example.com/static/wallet/hero.png"
    }
  },
  
  "validTimeInterval": {
    "start": {
      "date": "2024-01-01T00:00:00.000Z"
    },
    "end": {
      "date": "2026-12-31T23:59:59.000Z"
    }
  },
  
  "hasUsers": true
}
```

---

## Data Field Mapping

### Fields Used in Passes

| Field | Source | Format | Example |
|-------|--------|--------|---------|
| **Worker Name** | `workers.first_name + last_name` | String | "Max Müller" |
| **Badge ID** | `workers.badge_id` | String | "W-12345" |
| **Company Name** | `companies.name` | String | "Bau GmbH" |
| **Valid Until** | `workers.valid_until` | ISO Date | "31.12.2026" |
| **Status** | Derived from `workers.status` | String | "Active" / "Inactive" |
| **QR Code** | Badge ID + checksum | QR/Barcode | "W-12345-23" |

### Color Scheme

| Element | Color | Hex | RGB |
|---------|-------|-----|-----|
| **Background** | Suppix Technologie UG Orange | `#c78652` | (199, 134, 82) |
| **Secondary** | Dark Brown | `#8a5230` | (138, 82, 48) |
| **Text** | White | `#FFFFFF` | (255, 255, 255) |
| **Labels** | Light Cream | `#f6efe2` | (246, 239, 226) |

**Note:** Use `settings.invoice_primary_color` from database as primary color (default: `#06b6d4` if not set). Suppix Technologie UG's brand color is `#c78652`.

---

## Pass Lifecycle & Updates

### Scenario 1: New Worker
1. Worker created in admin UI
2. Badge ID assigned: `W-12345`
3. Pass generated and stored in `worker_passes` table
4. Worker downloads/adds pass to wallet
5. Gate access enabled via `/api/gates/tap` endpoint

### Scenario 2: Worker Edited
1. Worker details changed (name, valid_until, company)
2. Existing pass marked as "needs_update"
3. New version generated (version++, e.g., v1 → v2)
4. Users receive push notification: "Badge updated, re-add to wallet"
5. Old pass becomes invalid

### Scenario 3: Worker Deleted
1. Worker marked as deleted
2. Pass status → "revoked"
3. Pass push notification: "Access revoked"
4. Gate system rejects pass ID
5. QR fallback still works (requires admin verification)

---

## Visual Design Assets (To Be Created)

**Priority 1 (Required for Phase 1):**
- [ ] Logo PNG (320×320, brand color background)
- [ ] Thumbnail PNG (86×86, simplified logo)
- [ ] Icon PNG (29×29, letter "W" or badge)

**Priority 2 (Nice to Have for Phase 2):**
- [ ] Strip image (812×228, construction site photo)
- [ ] Hero image (1200×628, company branding)
- [ ] Alternate color schemes (light/dark mode)

---

## Implementation Notes for Phase 2

### pypasskit Code Example (Apple):

```python
from pypasskit import PKPass

def create_apple_pass(worker, company, settings):
    p = PKPass()
    p.addMetaData(
        name="WorkPass Badge",
        organizationName=company['name'],
        teamIdentifier=os.getenv("APPLE_TEAM_ID"),
        passTypeIdentifier=os.getenv("APPLE_PASS_TYPE_ID"),
        description="Worker badge for WorkPass gate access"
    )
    
    # Primary: Worker name
    p.addPrimaryField(
        key="worker_name",
        label="Worker",
        value=f"{worker['first_name']} {worker['last_name']}",
        textAlignment="PKTextAlignmentCenter"
    )
    
    # Secondary: Company and Status
    p.addSecondaryField(
        key="company",
        label="Company",
        value=company['name']
    )
    p.addSecondaryField(
        key="status",
        label="Status",
        value="Active"
    )
    
    # Auxiliary: Badge ID and Validity
    p.addAuxiliaryField(
        key="badge_id",
        label="Badge ID",
        value=worker['badge_id']
    )
    p.addAuxiliaryField(
        key="valid_until",
        label="Valid Until",
        value=worker['valid_until'][:10]  # "2026-12-31"
    )
    
    # Barcode: QR code with badge ID
    checksum = luhn_checksum(worker['badge_id'])
    barcode_value = f"{worker['badge_id']}-{checksum:02d}"
    p.addBarcode(
        message=barcode_value,
        format="PKBarcodeFormatQR"
    )
    
    # Colors
    p.backgroundColor = settings['invoice_primary_color']  # "#c78652"
    p.foregroundColor = "#FFFFFF"
    
    return p
```

### Google Wallet Code Example (Python JWT):

```python
import jwt
import json
from datetime import datetime, timedelta

def create_google_pass_jwt(worker, company, settings):
    issuer_id = os.getenv("GOOGLE_ISSUER_ID")
    
    claims = {
        "iss": os.getenv("GOOGLE_SERVICE_ACCOUNT_EMAIL"),
        "aud": "google",
        "origins": ["localhost", "baupass.example.com"],
        "typ": "savetowallet",
        "payload": {
            "genericObjects": [{
                "id": f"{issuer_id}.{worker['badge_id']}-v1",
                "classId": f"{issuer_id}.baukometra_worker",
                "classReference": {
                    "id": f"{issuer_id}.baukometra_worker",
                    "issuerName": "Suppix Technologie UG",
                    "displayName": "WorkPass Worker Badge",
                    "hexBackgroundColor": "#c78652"
                },
                "genericObject": {
                    "id": f"{issuer_id}.{worker['badge_id']}",
                    "textModulesData": [
                        {"header": "Worker", "body": f"{worker['first_name']} {worker['last_name']}"},
                        {"header": "Badge ID", "body": worker['badge_id']},
                        {"header": "Company", "body": company['name']},
                        {"header": "Valid Until", "body": worker['valid_until'][:10]}
                    ],
                    "barcode": {
                        "type": "QR_CODE",
                        "value": f"{worker['badge_id']}-{luhn_checksum(worker['badge_id']):02d}"
                    }
                }
            }]
        }
    }
    
    # Sign with service account private key
    with open(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH")) as f:
        key_data = json.load(f)
    
    token = jwt.encode(
        claims,
        key_data['private_key'],
        algorithm='RS256'
    )
    
    return token
```

---

## Next Steps

1. **Phase 1:** Confirm visual design with team (colors, layout)
2. **Phase 1:** Create placeholder PNG images (or use stock images)
3. **Phase 2:** Integrate pass template into Flask backend
4. **Phase 2:** Generate test passes and verify rendering
5. **Phase 3:** Polish design, collect user feedback

