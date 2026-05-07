# Database Schema Design (Phase 1)

**Goal:** Define the `worker_passes` table and related schema for wallet pass lifecycle management.

---

## Overview

Current database tracks:
- Workers (name, badge_id, physical_card_id, valid_until)
- Access logs (tap events, gate history)

**New requirement:** Track wallet passes (issued, active, revoked, expired).

---

## New Table: `worker_passes`

### Purpose
Store one record per worker per platform (Apple, Google) to track:
- Pass issuance date (when created)
- Pass activation date (when user added to wallet)
- Pass revocation/expiration dates
- Pass status (issued, active, revoked, expired)
- Pass metadata (JSON for reconstruction)

### SQL Schema

```sql
CREATE TABLE IF NOT EXISTS worker_passes (
    id TEXT PRIMARY KEY,                      -- Format: "pass-{uuid}" (UUID v4)
    worker_id TEXT NOT NULL,                  -- FK: workers.id
    company_id TEXT NOT NULL,                 -- FK: companies.id (denormalized for quick filtering)
    
    pass_type TEXT NOT NULL DEFAULT 'badge',  -- 'badge' (extensible for future types)
    platform TEXT NOT NULL,                   -- 'apple' | 'google'
    
    pass_class_id TEXT NOT NULL,              -- Template identifier
                                              -- Apple: pass.baukometra.baupass (constant)
                                              -- Google: 3388655000022476551.baukometra_worker
    
    pass_object_id TEXT NOT NULL UNIQUE,      -- Instance identifier
                                              -- Apple: serialNumber (e.g., W-12345-v1)
                                              -- Google: objectId (e.g., W-12345-v1)
                                              -- UNIQUE: Prevent duplicate passes
    
    status TEXT NOT NULL DEFAULT 'issued',    -- 'issued' | 'active' | 'revoked' | 'expired'
    
    pass_data_json TEXT NOT NULL,             -- Full pass JSON payload
                                              -- Stores: all field values, metadata
                                              -- Used for: reconstruction, updates, auditing
    
    pass_url TEXT NOT NULL,                   -- Download/redirect URL for user
                                              -- Apple: https://baupass.local/passes/apple/W-12345-v1.pkpass
                                              -- Google: https://baupass.local/passes/google/jwt?id=W-12345-v1
    
    signed_pass_data BLOB,                    -- Optional: cached signed .pkpass binary
                                              -- Apple only: pre-signed pass data
                                              -- Optimization: avoid re-signing on each download
                                              -- Nullable: can regenerate from pass_data_json
    
    issued_at TEXT NOT NULL,                  -- ISO timestamp: when pass created
                                              -- Format: 2024-05-06T14:30:00Z
    
    activated_at TEXT,                        -- ISO timestamp: when user added to wallet
                                              -- Nullable: NULL if not yet added
    
    revoked_at TEXT,                          -- ISO timestamp: when admin revoked
                                              -- Nullable: NULL if not revoked
    
    expired_at TEXT,                          -- ISO timestamp: when validity expired
                                              -- Nullable: NULL if not yet expired
                                              -- Scheduled job sets this at midnight
    
    version INTEGER NOT NULL DEFAULT 1,       -- Pass version number
                                              -- Incremented when pass data changes
                                              -- Used in: pass_object_id (e.g., W-12345-v1, W-12345-v2)
    
    last_updated_at TEXT NOT NULL,            -- ISO timestamp: last modification
                                              -- Used for: sorting, cleanup queries
    
    error_log TEXT,                           -- JSON array of recent errors
                                              -- Format: [{"error": "...", "at": "...", "count": 1}, ...]
                                              -- Used for: debugging, retry logic
    
    FOREIGN KEY(worker_id) REFERENCES workers(id),
    FOREIGN KEY(company_id) REFERENCES companies(id)
);
```

### Indexes (Performance Optimization)

```sql
-- Query: Find all passes for a worker on a specific platform
CREATE INDEX IF NOT EXISTS idx_worker_passes_worker_platform 
    ON worker_passes(worker_id, platform, status);

-- Query: Find all active/pending passes for a company
CREATE INDEX IF NOT EXISTS idx_worker_passes_company_status 
    ON worker_passes(company_id, status);

-- Query: Scheduled job to find expired passes
CREATE INDEX IF NOT EXISTS idx_worker_passes_expired_at 
    ON worker_passes(expired_at, status) 
    WHERE status IN ('active', 'issued');

-- Query: Find passes by object ID (direct lookup for Google Wallet)
CREATE INDEX IF NOT EXISTS idx_worker_passes_object_id_unique 
    ON worker_passes(pass_object_id);

-- Query: Find passes for a worker to revoke/delete
CREATE INDEX IF NOT EXISTS idx_worker_passes_worker_id 
    ON worker_passes(worker_id);
```

---

## Related Table: `worker_app_sessions`

**Current state:** Already exists, used for worker app login

**No changes required.** Continue using for authentication.

---

## Optional: Settings Columns (Feature Flags)

```sql
-- In existing settings table (id=1):
ALTER TABLE settings ADD COLUMN IF NOT EXISTS 
    wallet_passes_enabled INTEGER NOT NULL DEFAULT 0;
    -- 0: Feature disabled for all companies
    -- 1: Feature enabled

ALTER TABLE settings ADD COLUMN IF NOT EXISTS 
    wallet_apple_enabled INTEGER NOT NULL DEFAULT 0;
    -- 0: Apple Wallet disabled
    -- 1: Apple Wallet enabled

ALTER TABLE settings ADD COLUMN IF NOT EXISTS 
    wallet_google_enabled INTEGER NOT NULL DEFAULT 0;
    -- 0: Google Wallet disabled
    -- 1: Google Wallet enabled

ALTER TABLE settings ADD COLUMN IF NOT EXISTS 
    wallet_pass_expiry_warning_days INTEGER NOT NULL DEFAULT 14;
    -- Days before expiry to send reminder notification
```

---

## Migration Strategy (For Existing Deployments)

### Phase 1 Migration (No Data Loss)

1. **Add new table** during next deployment
   ```bash
   # migrations/001_add_worker_passes_table.sql
   # Copy schema from above
   ```

2. **Feature flag defaults to OFF**
   - Existing companies: wallet passes disabled until explicitly enabled
   - Prevents breaking changes

3. **No existing data migration**
   - New passes created only when feature enabled
   - Backward compatible with QR badge system

### Phase 2 Migration (Optional Population)

1. **Backfill historical passes** (optional)
   - Admin triggers: "Issue passes for all active workers"
   - Creates `worker_passes` records for existing workers
   - One per worker per platform

---

## Data Relationships

### Worker → Pass (One-to-Many)

```
workers (worker_id)
    ↓
    worker_passes (multiple per worker)
        ├── pass_type='badge' + platform='apple'
        ├── pass_type='badge' + platform='google'
        └── (future: pass_type='invoice', 'certificate', etc.)
```

### Company → Pass (One-to-Many)

```
companies (company_id)
    ↓
    worker_passes (multiple per company)
        └── All passes for all workers in company
```

### Access Control

- **Admin:** Can view all passes for their company
- **Worker:** Can only view own passes
- **System:** Scheduled jobs manage lifecycle (expiration, revocation)

---

## Pass Lifecycle State Transitions

### State Machine Diagram

```
┌─────────┐
│ issued  │ ← Pass created, not yet added to wallet
└────┬────┘
     │
     ├─ [User adds to wallet] ──→ ┌──────────┐
     │                             │ active   │ ← User can use pass
     │                             └────┬─────┘
     │                                  │
     │                                  ├─ [Date passes valid_until] ──→ ┌─────────┐
     │                                  │                               │ expired │
     │                                  │                               └─────────┘
     │                                  │
     │                                  └─ [Admin revokes] ──→ ┌──────────┐
     │                                                         │ revoked  │
     │                                                         └──────────┘
     │
     └─ [Never added, valid_until passes] ──→ ┌─────────┐
                                             │ expired │
                                             └─────────┘
```

### Transition Details

| From | To | Trigger | Condition | Notes |
|------|-----|---------|-----------|-------|
| **issued** | **active** | User action | Manually in wallet app | Webhook from Apple/Google (Phase 2) |
| **issued** | **expired** | Scheduled job | valid_until date passed, status still 'issued' | Runs nightly at midnight |
| **active** | **expired** | Scheduled job | valid_until date passed | Similar job as above |
| **active** | **revoked** | Admin action | Worker deleted / manually revoked | Via API endpoint or batch job |
| **issued** | **revoked** | Admin action | Worker deleted before pass added | Cleanup of unused passes |

---

## Data Examples

### Example 1: New Worker Pass (Apple Wallet)

**Scenario:** Max Müller (worker ID `W-12345`) just created his pass.

```sql
INSERT INTO worker_passes VALUES (
    'pass-550e8400-e29b-41d4-a716-446655440000',  -- id (UUID)
    'W-12345',                                     -- worker_id
    'bausite-001',                                 -- company_id
    'badge',                                        -- pass_type
    'apple',                                        -- platform
    'pass.baukometra.baupass',                     -- pass_class_id
    'W-12345-v1',                                  -- pass_object_id
    'issued',                                      -- status
    '{"worker_name":"Max Müller","badge_id":"W-12345","company":"Bau GmbH","valid_until":"2026-12-31"}',  -- pass_data_json
    'https://baupass.local/passes/apple/W-12345-v1.pkpass',  -- pass_url
    x'<binary data>',                              -- signed_pass_data (raw .pkpass file)
    '2024-05-06T14:30:00Z',                        -- issued_at
    NULL,                                          -- activated_at (waiting for user)
    NULL,                                          -- revoked_at
    NULL,                                          -- expired_at
    1,                                             -- version
    '2024-05-06T14:30:00Z',                        -- last_updated_at
    '[]'                                           -- error_log
);
```

### Example 2: Active Google Wallet Pass

**Scenario:** Pass already added to wallet (status='active').

```sql
INSERT INTO worker_passes VALUES (
    'pass-660f9511-f40c-52e5-b827-557776551111',
    'W-12345',
    'bausite-001',
    'badge',
    'google',
    '3388655000022476551.baukometra_worker',
    'W-12345-v1',
    'active',  ← Status changed to active
    '{"worker_name":"Max Müller",...}',
    'https://baupass.local/passes/google/jwt?id=W-12345-v1',
    NULL,  ← Google doesn't cache binary
    '2024-05-06T14:45:00Z',
    '2024-05-07T09:15:00Z',  ← User added to wallet
    NULL,
    NULL,
    1,
    '2024-05-07T09:15:00Z',
    '[]'
);
```

### Example 3: Revoked Pass

**Scenario:** Worker deleted; pass revoked.

```sql
INSERT INTO worker_passes VALUES (
    'pass-770g0622-g51d-63f6-c938-668887662222',
    'W-12346',
    'bausite-001',
    'badge',
    'apple',
    'pass.baukometra.baupass',
    'W-12346-v1',
    'revoked',  ← Status changed to revoked
    '{"worker_name":"Anna Schmidt",...}',
    'https://baupass.local/passes/apple/W-12346-v1.pkpass',
    x'<binary>',
    '2024-04-15T10:00:00Z',
    '2024-04-16T08:30:00Z',
    '2024-05-06T16:45:00Z',  ← Revoked timestamp
    NULL,
    1,
    '2024-05-06T16:45:00Z',
    '[{"error":"Worker deleted","at":"2024-05-06T16:45:00Z"}]'
);
```

---

## Query Examples (For Phase 2 Implementation)

### Find Active Passes for a Worker

```sql
SELECT * FROM worker_passes
WHERE worker_id = 'W-12345'
  AND status IN ('issued', 'active');
```

### Find Expired Passes (Scheduled Job)

```sql
SELECT * FROM worker_passes
WHERE status IN ('issued', 'active')
  AND expired_at IS NULL
  AND valid_until < datetime('now');
  -- Update status to 'expired'
```

### Find All Passes for a Company

```sql
SELECT * FROM worker_passes
WHERE company_id = 'bausite-001'
  AND status NOT IN ('revoked', 'expired')
ORDER BY last_updated_at DESC;
```

### Revoke All Passes for a Deleted Worker

```sql
UPDATE worker_passes
SET status = 'revoked',
    revoked_at = datetime('now'),
    last_updated_at = datetime('now')
WHERE worker_id = 'W-12345'
  AND status NOT IN ('expired', 'revoked');
```

---

## Implementation Checklist (For Phase 2)

- [ ] Create `worker_passes` table in `init_db()` function
- [ ] Add indexes for performance
- [ ] Create migration script for existing databases
- [ ] Add feature flag columns to `settings` table
- [ ] Implement pass generation endpoints (Flask)
- [ ] Implement pass lifecycle management (scheduled jobs)
- [ ] Add audit logging for pass lifecycle events
- [ ] Write SQL queries for common operations
- [ ] Test with sample data (100+ workers)

---

## Performance Considerations

### Table Size Estimate

**Scenario:** 500 companies, 10,000 total workers, both Apple + Google

```
Records: 10,000 workers × 2 platforms = 20,000 rows
Columns: ~15 columns, mostly TEXT/small integers
Average row size: ~2–3 KB
Total table size: 20,000 rows × 2.5 KB = ~50 MB
Indexes: ~10 MB
Total: ~60 MB (negligible for SQLite/PostgreSQL)
```

### Query Performance

- **Worker lookup:** O(1) with worker_id index
- **Company reports:** O(n) where n = passes in company (acceptable, <1s for 1000 passes)
- **Expiration scan:** O(n) monthly/weekly, background job (acceptable)

### Optimization Notes

- Indexes on (worker_id, platform) + (company_id, status) cover 95% of queries
- `signed_pass_data` BLOB optional — regenerate if space is concern
- Regular cleanup of old 'expired'/'revoked' passes (archive to backup table)

---

## Next Steps

1. **Phase 1:** Review schema with team, confirm structure
2. **Phase 1:** Create migration script
3. **Phase 2:** Implement `create_worker_passes()` endpoint
4. **Phase 2:** Implement lifecycle management (expiration job)
5. **Phase 3:** Add admin UI for pass management (view, revoke, resend)

