# وثائق الهندسة المعمارية

| وثيقة | المحتوى |
|-------|---------|
| [domains README](../../backend/app/domains/README.md) | تفكيك server.py |
| [server decomposition](../engineering/server-decomposition-roadmap.md) | مراحل النقل |
| [security architecture](../enterprise-security/security-architecture-AR.md) | طبقات الأمن |
| [enterprise roadmap 2026](../enterprise-roadmap-2026-AR.md) | الخطة الشاملة |

## مخطط مكونات (مبسّط)

```
backend/
  server.py          # legacy monolith (يُصغَّر تدريجياً)
  app/
    domains/         # auth, workers, access, billing, reporting, …
    platform/        # enterprise layers, SSO, reports, AI
    api/             # worker_app, shift, blueprint registry
```

## Runbooks

- `docs/enterprise-backup-restore-runbook.md`
- `docs/postgres-cutover-runbook.md`
- `docs/private-cloud-helm-AR.md`
