# Signatur-Pad / USB-Bridge

## Herstellerunabhängig (Browser)

WorkPass erkennt automatisch installierte lokale Bridges:

| Anbieter | Software auf dem Admin-PC | Datei im Projekt |
|----------|---------------------------|------------------|
| **Signotec** | signoPAD-API/Web (Port 49494) | `vendor/signotec/STPadServerLib.js` |
| **Wacom STU** | Wacom STU SigCaptX | `vendor/wacom/q.js` + `wgssStuSdk.js` |
| **StepOver** | Pad Connector | — (WebSocket) |
| **Topaz** | SigWeb | `vendor/topaz/SigWebTablet.js` |
| **Beliebig** | — | Unterschrift auf der **Canvas** (USB-Stift als Maus) |

WorkPass → Mitarbeiter → **Signaturgerät**

Details: [signature-pad-setup-AR.md](./signature-pad-setup-AR.md) · Signotec: [signotec-setup-AR.md](./signotec-setup-AR.md)

## Endpoint (alternativ: Desktop-Agent)

`POST /api/device/signature/capture`

## Authentifizierung (eine Option)

1. **IoT-Gerät:** Header `X-Device-API-Key` (wie Gate-Heartbeat)
2. **Desktop-Agent:** Header `X-WorkPass-Signature-Token` = `BAUPASS_SIGNATURE_BRIDGE_TOKEN` (+ optional `X-WorkPass-Company-Id`)
3. **Admin-Session:** Cookie/Bearer wie WorkPass

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
