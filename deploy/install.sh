#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 24.04 server for Bike Log (run as root). See deploy/README.md.
#   git clone https://<github-token>@github.com/dirksn74/bike_log /opt/bikelog
#   bash /opt/bikelog/deploy/install.sh
# It asks for your domain, the Google sign-in details and the allowed e-mail addresses, installs Docker,
# opens only the ports 22/80/443, writes deploy/.env, starts Bike Log and (if you want) updates it nightly.
# Running it again is safe: it keeps existing answers unless you type new ones.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Please run as root (sudo bash $0)."; exit 1; }
REPO="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
ENV_FILE="$REPO/deploy/.env"
chmod 700 "$REPO"

current() { [ -f "$ENV_FILE" ] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 || true; }
ask() {  # ask VAR "question" [secret]
  local var="$1" q="$2" old ans; old="$(current "$var")"
  if [ -n "$old" ]; then
    if [ "${3:-}" = secret ]; then q="$q [keep saved value]"; else q="$q [$old]"; fi
  fi
  while true; do
    if [ "${3:-}" = secret ]; then read -r -s -p "$q: " ans; echo; else read -r -p "$q: " ans; fi
    ans="${ans:-$old}"
    [ -n "$ans" ] && break
    echo "  Please enter a value."
  done
  printf -v "$var" '%s' "$ans"
}

echo "== Bike Log server setup =="
ask BIKELOG_DOMAIN "Your domain for Bike Log (e.g. bikelog.example.com)"
BIKELOG_DOMAIN="${BIKELOG_DOMAIN#https://}"; BIKELOG_DOMAIN="${BIKELOG_DOMAIN%%/*}"
ask BIKELOG_GOOGLE_CLIENT_ID "Google OAuth Client ID (ends with .apps.googleusercontent.com)"
ask BIKELOG_GOOGLE_CLIENT_SECRET "Google OAuth Client secret (not shown while typing)" secret
ask BIKELOG_ALLOWED_EMAILS "Google account(s) allowed to sign in, comma separated"
read -r -p "Update Bike Log automatically every night at 04:00? [Y/n]: " auto; auto="${auto:-Y}"

umask 077
cat > "$ENV_FILE" <<CONF
# Written by deploy/install.sh on $(date -I). Change values by running install.sh again.
BIKELOG_DOMAIN=$BIKELOG_DOMAIN
BIKELOG_PUBLIC_URL=https://$BIKELOG_DOMAIN
BIKELOG_GOOGLE_CLIENT_ID=$BIKELOG_GOOGLE_CLIENT_ID
BIKELOG_GOOGLE_CLIENT_SECRET=$BIKELOG_GOOGLE_CLIENT_SECRET
BIKELOG_ALLOWED_EMAILS=$BIKELOG_ALLOWED_EMAILS
CONF
umask 022
echo "Settings saved in $ENV_FILE (only root can read it)."

echo "== Installing Docker and the firewall (takes a few minutes) =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq docker.io docker-compose-v2 git ufw unattended-upgrades >/dev/null
systemctl enable --now docker >/dev/null
ufw allow OpenSSH >/dev/null; ufw allow 80/tcp >/dev/null; ufw allow 443 >/dev/null
ufw --force enable >/dev/null

ln -sf "$REPO/deploy/update.sh" /usr/local/bin/bikelog-update
chmod +x "$REPO/deploy/update.sh" "$REPO/deploy/install.sh"
if [[ "$auto" =~ ^[YyJj] ]]; then
  cat > /etc/systemd/system/bikelog-update.service <<UNIT
[Unit]
Description=Update Bike Log to the newest version
After=docker.service network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/bin/bikelog-update
UNIT
  cat > /etc/systemd/system/bikelog-update.timer <<UNIT
[Unit]
Description=Nightly Bike Log update
[Timer]
OnCalendar=*-*-* 04:00:00
RandomizedDelaySec=15min
Persistent=true
[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload
  systemctl enable --now bikelog-update.timer >/dev/null
  echo "Nightly updates are on (turn off: systemctl disable --now bikelog-update.timer)."
else
  systemctl disable --now bikelog-update.timer >/dev/null 2>&1 || true
fi

echo "== Building and starting Bike Log (the first build takes 3-6 minutes) =="
bikelog-update --force
echo
echo "Done. Open https://$BIKELOG_DOMAIN in your browser and sign in with Google."
echo "If the page does not load yet: the domain's DNS may still be on its way (up to an hour)."
