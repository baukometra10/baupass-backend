#!/usr/bin/env bash
# Einmal-Setup auf Hetzner (Ubuntu). Voraussetzung: Projekt liegt unter /opt/baupass
set -euo pipefail

APP_DIR="/opt/baupass"
DATA_DIR="/opt/baupass/data"
SERVICE_NAME="baupass"

usage() {
  echo "Usage: sudo bash deploy/hetzner-setup.sh --url http://SERVER-IP"
  echo "   or: sudo bash deploy/hetzner-setup.sh --url https://ihre-domain.de --domain ihre-domain.de"
  exit 1
}

PUBLIC_BASE_URL=""
SERVER_NAME="_"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) PUBLIC_BASE_URL="${2%/}"; shift 2 ;;
    --domain) SERVER_NAME="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

if [[ -z "$PUBLIC_BASE_URL" ]]; then
  echo "Bitte oeffentliche URL angeben (ohne Slash am Ende)."
  usage
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Bitte als root ausfuehren: sudo bash deploy/hetzner-setup.sh --url ..."
  exit 1
fi

if [[ ! -f "$APP_DIR/backend/requirements.txt" ]]; then
  echo "FEHLER: $APP_DIR/backend/requirements.txt fehlt."
  echo "Zuerst Projekt nach /opt/baupass hochladen (WinSCP oder ZIP)."
  exit 1
fi

echo "==> Pakete installieren..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3.11 python3.11-venv python3-pip nginx curl

echo "==> Python-Umgebung..."
mkdir -p "$DATA_DIR"
cd "$APP_DIR"
if [[ ! -d .venv ]]; then
  python3.11 -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r backend/requirements.txt

echo "==> systemd Dienst..."
sed "s|__PUBLIC_BASE_URL__|${PUBLIC_BASE_URL}|g" "$APP_DIR/deploy/hetzner/baupass.service" > "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo "==> Nginx..."
sed "s|__SERVER_NAME__|${SERVER_NAME}|g" "$APP_DIR/deploy/hetzner/nginx-baupass.conf" > /etc/nginx/sites-available/baupass
ln -sf /etc/nginx/sites-available/baupass /etc/nginx/sites-enabled/baupass
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH >/dev/null 2>&1 || true
  ufw allow 'Nginx Full' >/dev/null 2>&1 || true
  ufw --force enable >/dev/null 2>&1 || true
fi

echo "==> Health-Check..."
sleep 3
if curl -fsS "http://127.0.0.1:8000/api/health" >/dev/null; then
  echo "OK: Backend antwortet auf Port 8000."
else
  echo "WARNUNG: Health-Check fehlgeschlagen. Logs: journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
fi

echo ""
echo "Fertig."
echo "  Admin:    ${PUBLIC_BASE_URL}/"
echo "  Worker:   ${PUBLIC_BASE_URL}/worker.html?view=card"
echo "  Health:   ${PUBLIC_BASE_URL}/api/health"
echo ""
echo "HTTPS mit Domain: certbot --nginx -d IHRE-DOMAIN.de"
echo "Logs: journalctl -u ${SERVICE_NAME} -f"
