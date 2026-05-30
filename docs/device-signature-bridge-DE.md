# Signatur-Pad / USB-Bridge

## Endpoint

`POST /api/device/signature/capture`

## Authentifizierung (eine Option)

1. **IoT-Gerät:** Header `X-Device-API-Key` (wie Gate-Heartbeat)
2. **Desktop-Agent:** Header `X-BauPass-Signature-Token` = `BAUPASS_SIGNATURE_BRIDGE_TOKEN` (+ optional `X-BauPass-Company-Id`)
3. **Admin-Session:** Cookie/Bearer wie Control Pass

## Body (JSON)

```json
{
  "workerId": "w-abc123",
  "signatureData": "data:image/png;base64,...",
  "deviceId": "pad-desk-01",
  "clearSignature": false
}
```

## Antwort

`200` → `{ "ok": true, "workerId": "...", "deviceId": "..." }`

## Railway / Env

- `BAUPASS_SIGNATURE_BRIDGE_TOKEN` — geheimer Token für den lokalen Agent
