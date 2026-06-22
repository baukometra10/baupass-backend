# إدارة التغيير والإصدارات — WorkPass

## Release channels

| قناة | فرع / بيئة | جمهور |
|------|------------|--------|
| Production | `main` → Railway | كل العملاء |
| Staging | `staging` أو preview | فريق + UAT |
| Enterprise dedicated | عميل كبير (بند 20) | UAT منفصل |

## سجل التغييرات

- **Git tags** `vYYYY.MM.patch` مع ملاحظات في GitHub Releases
- **Migrations** مرقمة في `backend/app/migrations/` — لا تخطّ رقم migration
- **Frontend cache bust** `?v=` في `index.html` / `admin-v2`

## موافقات التغيير (حوكمة)

| نوع | موافقة |
|-----|--------|
| Hotfix أمني P1 | Tech lead + إشعار عملاء متأثرين |
| Schema migration | مراجعة + backup قبل النشر |
| SSO / RBAC | UAT + وثيقة `sso-roadmap-AR.md` |

## Rollback

1. Railway: redeploy إصدار سابق
2. DB: migrations **لا rollback تلقائي** — استعادة من backup (`enterprise-backup-restore-runbook.md`)
3. Feature flags: `BAUPASS_*` env

## CI gates

- `backend/tests/`
- smoke: `ops/e2e_production_smoke.py`
- pre-deploy: `GET /api/health/ready`
