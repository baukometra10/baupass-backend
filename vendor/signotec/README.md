# Signotec signoPAD-API/Web — JS library for WorkPass

WorkPass loads Signotec's official JavaScript library from this folder.

## Setup (Windows, one-time per PC)

1. Download **signotec signoPAD-API/Web** from  
   [signotec Developer Tools](https://en.signotec.com/portal/seiten/download-developer-tools-api-sdk--900000510-10002.html)

2. Install on the **same PC** where WorkPass runs in the browser (USB pad connected).

3. Ensure **STPadServer** is running (Windows service or `STPadServer.exe 49494`).

   Browser bridge: `wss://localhost:49494` — trust once: **https://localhost:49494/**

4. Copy automatically (recommended):
   ```powershell
   npm run vendor:signotec
   ```
   Or set `BAUPASS_SIGNOTEC_LIB_SRC` to the full path of `STPadServerLib.js`, then run the same command.

   Manual copy from (typical path):
   ```
   C:\Program Files\signotec\signoPAD-API Web\STPadServerLib.js
   ```
   to:
   ```
   vendor/signotec/STPadServerLib.js
   ```

5. Commit `vendor/signotec/STPadServerLib.js` once so Railway serves it, **or** set Railway env `BAUPASS_SIGNOTEC_LIB_BASE64` (base64 of the file).

**Direct installer (signoPAD-API/Web 3.5.0 — not signoPADTools):**  
https://backend.signotec.com/wp-content/uploads/2025/11/signotec_signoPAD-API_Web_3.5.0.exe

6. Hard-refresh WorkPass (`Ctrl+Shift+R`) → Workers → **Signotec Pad** button.

## Notes

- The pad LCD shows "Please sign" when capture starts — not the browser canvas.
- `STPadServerLib.js` is **not** redistributed in git by default (Signotec license). Use `npm run vendor:signotec` on a PC with signoPAD installed, then commit or set `BAUPASS_SIGNOTEC_LIB_BASE64` on Railway.
- For 50+ devices in production, signotec requires a commercial agreement.

See also: `docs/signotec-setup-AR.md`
