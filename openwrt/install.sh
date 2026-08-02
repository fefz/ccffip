#!/bin/sh
# cfnb OpenWrt installer
set -e

APP_DIR="${APP_DIR:-/opt/cfnb}"
SRC_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

if command -v apk >/dev/null 2>&1; then
    apk update || echo "warning: some apk feeds failed; continuing with available indexes"
    apk add python3 python3-requests python3-aiohttp curl ca-bundle coreutils-base64
elif command -v opkg >/dev/null 2>&1; then
    opkg update
    opkg install python3-light python3-requests python3-aiohttp curl ca-bundle coreutils-base64
else
    echo "no apk or opkg package manager found" >&2
    exit 1
fi

mkdir -p "$APP_DIR" /var/log/cfnb
cp "$SRC_DIR/main.py" "$APP_DIR/"
if [ -f "$SRC_DIR/config.json" ]; then
    cp "$SRC_DIR/config.json" "$APP_DIR/"
elif [ -f "$SRC_DIR/openwrt/config.example.json" ]; then
    cp "$SRC_DIR/openwrt/config.example.json" "$APP_DIR/config.json"
else
    echo "missing config.json or openwrt/config.example.json" >&2
    exit 1
fi
[ -f "$SRC_DIR/github_sync.py" ] && cp "$SRC_DIR/github_sync.py" "$APP_DIR/"
[ -f "$SRC_DIR/git_sync.sh" ] && cp "$SRC_DIR/git_sync.sh" "$APP_DIR/"
chmod 700 "$APP_DIR" "$APP_DIR"/*.sh 2>/dev/null || true
chmod 600 "$APP_DIR/config.json"

install -m 0755 "$SRC_DIR/openwrt/cfnb.init" /etc/init.d/cfnb

CRON_LINE="*/5 * * * * cd $APP_DIR && /usr/bin/python3 $APP_DIR/main.py >> /var/log/cfnb/cron.log 2>&1"
CRON_FILE=/etc/crontabs/root
[ -f "$CRON_FILE" ] || touch "$CRON_FILE"
grep -F "$APP_DIR/main.py" "$CRON_FILE" >/dev/null 2>&1 || echo "$CRON_LINE" >> "$CRON_FILE"
/etc/init.d/cron restart 2>/dev/null || /etc/init.d/cron start 2>/dev/null || true

/etc/init.d/cfnb enable
/etc/init.d/cfnb restart

echo "cfnb installed at $APP_DIR"
echo "log: /var/log/cfnb/cron.log"
