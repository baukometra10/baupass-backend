# BauPass Admin v2

Lightweight enterprise admin dashboard consuming **API v2**.

## URL

- Local: `http://localhost:5000/admin-v2/index.html`
- Production: `https://<your-host>/admin-v2/index.html`

## Login

| Role | Scope in form | Notes |
|------|---------------|--------|
| Company admin | مدير شركة | Uses own `company_id` |
| Superadmin | Superadmin | Pick company from header dropdown |

## Features

- Overview: on-site count, active workers, recent access logs
- Workers: list + **assign NFC card UID** (`PATCH /api/v2/workers/{id}/physical-card`)
- Access: live feed from `/api/v2/access/live`

## Legacy admin

Full features remain in [/index.html](../index.html).
