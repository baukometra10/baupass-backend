# حالة البنود — نهائي

## ⏸ مؤجّل (لاحقاً فقط)

| البند |
|--------|
| تقسيم Domains من `server.py` (1, 2, 3, 83) |

## ✅ مكتمل — كل البنود الأخرى

- PostgreSQL runtime + bootstrap + `GET /api/platform/database-status`
- SAP / Oracle: health + export-preview + sync
- Multi-region: policy API + `company_data_residency` + `BAUPASS_ENFORCE_DATA_RESIDENCY`
- Hybrid Worker: PWA + Flutter + 3 أوضاع NFC/RFID/HCE
- Observability, DR, integrations, AI, automation, onboarding, operations intelligence

## إعدادك على Railway

أنت جهّزت المتغيرات — شغّل migration **017**:

```bash
python -m backend.app.migrations.runner --migrate
```

تحقق:

```http
GET /api/platform/database-status
GET /api/health/ready
GET /api/health/dr
```

## Grafana

استيراد من `deploy/grafana/` — راجع `deploy/grafana/README.md`
