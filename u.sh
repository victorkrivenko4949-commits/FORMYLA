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

# 2. Fix SQLite datetime string crash in routes/admin_support.py (/admin/users 500 error)
python3 - << 'PYEOF'
with open('routes/admin_support.py', 'r', encoding='utf-8') as f:
    s = f.read()

s = s.replace(
    '_d = (_ts + _MSK).date().isoformat()',
    '_dt_ts = _as_dt(_ts)\n        if not _dt_ts:\n            continue\n        _d = (_dt_ts + _MSK).date().isoformat()'
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
with open('routes/admin_support.py', 'w', encoding='utf-8') as f:
    f.write(s)
print("Patched routes/admin_support.py successfully")
PYEOF

systemctl restart formyla
echo "=== DONE! FORMYLA UPDATED + VPN-FREE ASSETS + STATS FIXED ==="
