# Runbooks تشغيلية — BauPass

| Runbook | ملف |
|---------|-----|
| نشر Railway | `railway-production-setup-AR.md` |
| Postgres cutover | `postgres-cutover-runbook.md` |
| Backup / Restore | `enterprise-backup-restore-runbook.md` |
| DR | `enterprise-security/disaster-recovery-AR.md` |
| BCP | `enterprise-security/business-continuity-AR.md` |
| حوادث أمن | `enterprise-security/incident-response-AR.md` |
| SSO Entra | `sso-entra-AR.md` |
| Staging | `staging-railway-AR.md` |
| Air-gap | `deploy/air-gapped-playbook-AR.md` |

## فحص يومي

```http
GET /api/health/ready
GET /api/platform/database-status
```

## on-call

1. تحقق من logs Railway / Sentry
2. `GET /api/health/dr`
3. إن DB: راجع migration runner
4. إن SSO: `GET /api/auth/sso/catalog`
