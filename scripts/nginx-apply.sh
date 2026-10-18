#!/bin/sh
# Install the repo's production nginx config and reload safely. Run ON production:
#     ~/np-explorer/scripts/nginx-apply.sh
# Backs up the live files, installs deploy/nginx/*, runs nginx -t, reloads, then checks
# that the reload really took: nginx -t can pass while a reload still fails (e.g. a
# changed limit_req_zone key logs [emerg] and keeps the old config). On any failure the
# backup goes back and nginx is reloaded on it.
set -eu
cd "$(dirname "$0")/.."
FILES="np-limits.conf:/etc/nginx/conf.d/np-limits.conf
gzip.conf:/etc/nginx/conf.d/gzip.conf
np-proxy.conf:/etc/nginx/snippets/np-proxy.conf
np-bad-agents.conf:/etc/nginx/np-bad-agents.conf
strategystudio.org:/etc/nginx/sites-available/strategystudio.org"
BACKUP="/root/nginx-bak-$(date +%Y%m%d%H%M%S)"
sudo mkdir -p "$BACKUP"
echo "$FILES" | while IFS=: read -r src dest; do
    sudo cp -p "$dest" "$BACKUP/$(basename "$dest")"
    sudo cp "deploy/nginx/$src" "$dest"
done

restore() {
    echo "$1: restoring $BACKUP" >&2
    echo "$FILES" | while IFS=: read -r src dest; do sudo cp -p "$BACKUP/$(basename "$dest")" "$dest"; done
    sudo nginx -t >/dev/null 2>&1 && sudo systemctl reload nginx
    exit 1
}

sudo nginx -t 2>/tmp/nginx-t.out || { cat /tmp/nginx-t.out >&2; restore "nginx -t failed"; }
since="$(date '+%Y/%m/%d %H:%M:%S')"
before="$(pgrep -f 'nginx: worker' | sort | tr '\n' ' ')"
sudo systemctl reload nginx || restore "reload failed"
sleep 4
if sudo awk -v t="$since" '$1" "$2 >= t' /var/log/nginx/error.log | grep -E '\[(emerg|alert|crit)\]' >&2; then
    restore "nginx logged an error on reload"
fi
after="$(pgrep -f 'nginx: worker' | sort | tr '\n' ' ')"
[ "$before" != "$after" ] || restore "workers did not restart (the reload did not take)"
echo "nginx config applied and reloaded (backup in $BACKUP)"
