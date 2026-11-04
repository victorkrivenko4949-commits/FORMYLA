#!/bin/bash
# Автообновление FORMYLA (cron каждые 5 минут).
# Если в origin/main есть новый коммит — обновляет сервер через u.sh.
# Если после обновления сайт не ожил — откат на предыдущий коммит.
set -u
exec 9>/tmp/formyla-autoupdate.lock
flock -n 9 || exit 0

cd /opt/formyla || exit 1
LOG=/var/log/formyla-autoupdate.log
HEALTH_URL=http://127.0.0.1:8000/login

git fetch -q origin main || exit 0
OLD_HEAD=$(git rev-parse HEAD)
NEW_HEAD=$(git rev-parse origin/main)
[ "$OLD_HEAD" = "$NEW_HEAD" ] && exit 0

echo "[$(date '+%F %T')] auto-update: ${OLD_HEAD:0:7} -> ${NEW_HEAD:0:7}" >> "$LOG"
bash u.sh >> "$LOG" 2>&1

check() {
    systemctl is-active --quiet formyla.service || return 1
    curl -sf -m 10 -o /dev/null "$HEALTH_URL" || return 1
    return 0
}

sleep 5
for i in 1 2 3 4 5 6; do
    if check; then
        echo "[$(date '+%F %T')] auto-update OK: ${NEW_HEAD:0:7} live" >> "$LOG"
        exit 0
    fi
    sleep 5
done

echo "[$(date '+%F %T')] health check FAILED, rollback to ${OLD_HEAD:0:7}" >> "$LOG"
git reset -q --hard "$OLD_HEAD"
sed 's|origin/main|HEAD|g' u.sh > /tmp/u_rollback.sh
bash /tmp/u_rollback.sh >> "$LOG" 2>&1
sleep 5
if check; then
    echo "[$(date '+%F %T')] rollback OK" >> "$LOG"
else
    echo "[$(date '+%F %T')] rollback STILL FAILING — требуется ручной разбор" >> "$LOG"
fi
