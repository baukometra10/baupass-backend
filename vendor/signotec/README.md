# Signotec signoPAD-API/Web — JS library for BauPass

BauPass loads Signotec's official JavaScript library from this folder.

## Setup (Windows, one-time per PC)

1. Download **signotec signoPAD-API/Web** from  
   [signotec Developer Tools](https://en.signotec.com/portal/seiten/download-developer-tools-api-sdk--900000510-10002.html)

2. Install on the **same PC** where Control Pass runs in the browser (USB pad connected).

3. Ensure **STPadServer** is running (Windows service or `STPadServer.exe 49494`).

4. Copy from the install folder (typical path):
   ```
   C:\Program Files\signotec\signoPAD-API Web\STPadServerLib.js
   ```
   to:
   ```
   vendor/signotec/STPadServerLib.js
   ```

5. Hard-refresh Control Pass (`Ctrl+Shift+R`) → Workers → **Signotec Pad** button.

## Notes

- The pad LCD shows "Please sign" when capture starts — not the browser canvas.
- `STPadServerLib.js` is **not** redistributed in this repo (Signotec license). Each site copies it locally.
- For 50+ devices in production, signotec requires a commercial agreement.

See also: `docs/signotec-setup-AR.md`
