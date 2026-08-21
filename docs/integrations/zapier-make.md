# Zapier / Make integration

Enable with `BAUPASS_ZAPIER_ENABLED=1`.

## Triggers

Subscribe via `POST /api/integrations/ipaas/subscriptions`:

```json
{
  "provider": "zapier",
  "eventType": "worker.created",
  "targetUrl": "https://hooks.zapier.com/..."
}
```

Deliveries are HMAC-SHA256 signed (`X-Baupass-Signature`).

## Actions

Use existing public API keys (`bp_live_…`) for worker upsert / leave create.

## Catalog

`GET /api/integrations/ipaas/catalog`
