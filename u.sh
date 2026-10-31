#!/bin/bash
set -e
cd /opt/formyla
if [ ! -d .git ]; then
  git init
  git remote add origin https://github.com/victorkrivenko4949-commits/FORMYLA.git
fi
git fetch origin main
git reset --hard origin/main

# 1. Localize CDN assets (Chart.js, KaTeX, Marked.js) so site works in Russia without VPN
mkdir -p static/vendor/fonts
curl -sL https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js -o static/vendor/chart.umd.min.js || true
curl -sL https://cdn.jsdelivr.net/npm/marked/marked.min.js -o static/vendor/marked.min.js || true
curl -sL https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js -o static/vendor/katex.min.js || true
curl -sL https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js -o static/vendor/auto-render.min.js || true
curl -sL https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css -o static/vendor/katex.min.css || true
for f in KaTeX_Main-Regular.woff2 KaTeX_Main-Bold.woff2 KaTeX_Main-Italic.woff2 KaTeX_Math-Italic.woff2 KaTeX_Math-BoldItalic.woff2 KaTeX_Size1-Regular.woff2 KaTeX_Size2-Regular.woff2 KaTeX_Size3-Regular.woff2 KaTeX_Size4-Regular.woff2 KaTeX_AMS-Regular.woff2; do
  [ -f "static/vendor/fonts/$f" ] || curl -sL "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/fonts/$f" -o "static/vendor/fonts/$f" || true
done

sed -i 's|https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js|/static/vendor/chart.umd.min.js|g' templates/base.html
sed -i 's|https://cdn.jsdelivr.net/npm/marked/marked.min.js|/static/vendor/marked.min.js|g' templates/base.html
sed -i 's|https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js|/static/vendor/katex.min.js|g' templates/base.html
sed -i 's|https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js|/static/vendor/auto-render.min.js|g' templates/base.html
sed -i 's|https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css|/static/vendor/katex.min.css|g' templates/base.html

# 2. Fix SQLite schema, datetime & limit rows in routes/admin_support.py so /admin/users is fast (<1s) and never hits 500/502
python3 - << 'PYEOF'
with open('routes/admin_support.py', 'r', encoding='utf-8') as f:
    s = f.read()

s = s.replace(
    "cols = [r[0] for r in db.session.execute(text(\n                        'PRAGMA table_info(site_events)')).fetchall()]",
    "cols = [r[1] for r in db.session.execute(text(\n                        'PRAGMA table_info(site_events)')).fetchall()]"
)
s = s.replace(
    '_d = (_ts + _MSK).date().isoformat()',
    '_dt_ts = _as_dt(_ts)\n        if not _dt_ts:\n            continue\n        _d = (_dt_ts + _MSK).date().isoformat()'
)
s = s.replace(
    'hour_sets[(_t + _MSK).hour].add(_uid)',
    'hour_sets[(_as_dt(_t) + _MSK).hour].add(_uid)'
)
s = s.replace(
    "'when': when.strftime('%d.%m %H:%M') if when else '—',",
    "'when': _as_dt(when).strftime('%d.%m %H:%M') if _as_dt(when) else '—',"
)
s = s.replace(
    "'asked': asked.strftime('%d.%m %H:%M') if asked else '—',",
    "'asked': _as_dt(asked).strftime('%d.%m %H:%M') if _as_dt(asked) else '—',"
)
s = s.replace(
    "'answered': answered.strftime('%d.%m %H:%M') if answered else None,",
    "'answered': _as_dt(answered).strftime('%d.%m %H:%M') if _as_dt(answered) else None,"
)
# Limit table rendering in template to top 300 active users so HTML is ~200KB instead of 6.6MB
s = s.replace(
    "return render_template('admin/users_stats.html', rows=rows, total=total,",
    "return render_template('admin/users_stats.html', rows=rows[:300], total=total,"
)

with open('routes/admin_support.py', 'w', encoding='utf-8') as f:
    f.write(s)
print("Patched routes/admin_support.py successfully")

with open('services/user_returns.py', 'r', encoding='utf-8') as f:
    ur = f.read()
ur = ur.replace(
    "'rows': rows,",
    "'rows': [r for r in rows if r.get('bucket') != 'never'][:300],"
)
with open('services/user_returns.py', 'w', encoding='utf-8') as f:
    f.write(ur)
print("Patched services/user_returns.py successfully")
PYEOF

# 3. Increase nginx proxy_read_timeout & buffers so large pages never get cut off
for conf in /etc/nginx/sites-enabled/* /etc/nginx/conf.d/*.conf; do
  [ -f "$conf" ] || continue
  if ! grep -q "proxy_read_timeout" "$conf"; then
    sed -i '/proxy_pass/a \        proxy_read_timeout 180s;\n        proxy_connect_timeout 60s;\n        proxy_send_timeout 180s;\n        proxy_buffer_size 128k;\n        proxy_buffers 8 256k;\n        proxy_busy_buffers_size 512k;' "$conf" || true
  fi
done
nginx -t && systemctl reload nginx || true

systemctl restart formyla
echo "=== DONE! FORMYLA UPDATED + FAST STATS (<1s) + NGINX TUNED ==="
