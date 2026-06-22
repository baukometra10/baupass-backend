# WorkPass auf Hetzner – Einrichtung (Start hier)

## Phase 1 – Jetzt (Sie im Browser)

1. https://console.hetzner.cloud → Konto / Projekt
2. **Server hinzufügen**
   - Image: **Ubuntu 24.04**
   - Typ: **CX22**
   - Standort: **Nürnberg** oder **Falkenstein**
   - SSH-Key **oder** Root-Passwort (E-Mail)
3. Server starten → **IPv4** notieren, z. B. `123.45.67.89`

Schreiben Sie die **IP hier in den Chat**, dann passen wir die Befehle an.

---

## Phase 2 – ZIP auf dem PC erstellen

PowerShell im Projektordner:

```powershell
cd C:\Users\u4363\Desktop\baustelle
powershell -ExecutionPolicy Bypass -File .\deploy\hetzner-pack.ps1
```

Ergebnis: `baupass-hetzner-upload.zip`

---

## Phase 3 – Hochladen (WinSCP)

1. https://winscp.net
2. Neu: **SFTP**, Host = **Server-IP**, Benutzer `root`, Passwort aus Hetzner-E-Mail
3. ZIP nach `/opt/` hochladen (`baupass-hetzner-upload.zip`)

---

## Phase 4 – Auf dem Server (SSH)

Windows-Terminal oder PuTTY:

```bash
ssh root@IHRE-SERVER-IP
```

Dann:

```bash
apt update && apt install -y unzip
mkdir -p /opt/baupass
unzip -o /opt/baupass-hetzner-upload.zip -d /opt/baupass
cd /opt/baupass
chmod +x deploy/hetzner-setup.sh
bash deploy/hetzner-setup.sh --url http://IHRE-SERVER-IP
```

Ersetzen `IHRE-SERVER-IP` durch die echte IP (ohne Slash am Ende).

Test im Browser:

- `http://IHRE-SERVER-IP/` (Admin)
- `http://IHRE-SERVER-IP/api/health`
- `http://IHRE-SERVER-IP/worker-build.json`

---

## Phase 5 – Domain + HTTPS (optional, später)

1. Domain kaufen (z. B. bei Hetzner DNS, IONOS, …)
2. **A-Record** → Server-IP
3. Auf dem Server:

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d ihre-domain.de
```

4. URL in systemd anpassen und neu starten:

```bash
sed -i 's|PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://ihre-domain.de|' /etc/systemd/system/baupass.service
systemctl daemon-reload && systemctl restart baupass
```

---

## Updates

1. Dateien lokal ändern
2. `hetzner-pack.ps1` → ZIP neu
3. WinSCP → `/opt/baupass` überschreiben (oder nur geänderte Dateien)
4. SSH: `systemctl restart baupass`

---

## Datenbank von Railway retten (optional)

Falls Sie die alte DB haben: Datei `baupass.db` nach `/opt/baupass/data/baupass.db` kopieren, dann `systemctl restart baupass`.

---

## Hilfe bei Fehlern

```bash
systemctl status baupass
journalctl -u baupass -n 80 --no-pager
curl -s http://127.0.0.1:8000/api/health
```
