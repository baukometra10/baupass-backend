# Physical Operations OS — الـ 12 قدرة

نقطة دخول موحّدة:

```http
GET /api/ops-os/overview?company_id=1
```

## 1 Digital Twin
`GET /api/ops-os/digital-twin` — عمال، بوابات، معدات، مناطق خطرة، حركة 15 دقيقة.

## 2 AI Security Engine
`GET /api/ops-os/security-engine?persist=1` — احتيال، ساعات غريبة، تعدد بوابات، بطاقات مكررة.

## 3 Smart Site Intelligence
`GET /api/ops-os/site-intelligence` — ازدحام بوابات، مواقع ضعيفة، ذروة، مشاكل تشغيل.

## 4 Workforce Reputation
`GET /api/ops-os/reputation` · `GET /api/ops-os/reputation/{workerId}`

## 5 Smart Emergency
`POST /api/ops-os/emergency` · `GET /api/ops-os/emergency/{id}` · roll-call · missing persons

## 6 AI Video & Camera
`POST /api/ops-os/cameras/analyze` · `GET /api/ops-os/cameras/events`

## 7 IoT Infrastructure
`GET /api/ops-os/iot` · `POST /api/ops-os/iot/devices` · telemetry

## 8 Command Center
`GET /api/ops-os/command-center` · واجهة: `/ops-command-center.html`

## 9 Autonomous Operations
`/api/automation/rules` — إجراءات: `lock_worker`, `unlock_worker`, `run_security_scan`, `generate_ops_report`

## 10 Workforce Graph
`GET /api/ops-os/workforce-graph?days=14`

## 11 Digital Identity Hub
`GET /api/ops-os/identity?worker_id=`

## 12 AI Operations Copilot
`POST /api/ops-os/copilot` · `GET /api/ops-os/copilot/context` · أيضاً `POST /api/ai/query` (سياق تلقائي)

## Migration
```bash
python -m backend.app.migrations.runner --migrate
```
إصدار **018** — جداول طوارئ، سمعة، كاميرات، IoT، معدات، مخاطر.

## معدات ومخاطر
`POST /api/ops-os/equipment` · `POST /api/ops-os/hazard-zones`
