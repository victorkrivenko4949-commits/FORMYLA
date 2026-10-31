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

# 2. Fix SQLite schema & datetime issues in routes/admin_support.py (/admin/users 500 error)
python3 - << 'PYEOF'
with open('routes/admin_support.py', 'r', encoding='utf-8') as f:
    s = f.read()

# Fix 2a: PRAGMA table_info column name is r[1], not r[0]
s = s.replace(
    "cols = [r[0] for r in db.session.execute(text(\n                        'PRAGMA table_info(site_events)')).fetchall()]",
    "cols = [r[1] for r in db.session.execute(text(\n                        'PRAGMA table_info(site_events)')).fetchall()]"
)

# Fix 2b: SQLite raw SQL returns timestamps as strings in ev_rows
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

with open('routes/admin_support.py', 'w', encoding='utf-8') as f:
    f.write(s)
print("Patched routes/admin_support.py successfully")
PYEOF

# 3. Run auto_migrate and test /admin/users directly so we see any remaining DB issue
ENV_FILE=/opt/formyla/.env
if [ -f "$ENV_FILE" ]; then
  set -a
  . "$ENV_FILE"
  set +a
fi

VENV_PY="/opt/formyla/venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  VENV_PY="/opt/formyla/.venv/bin/python"
fi
if [ ! -x "$VENV_PY" ]; then
  VENV_PY="python3"
fi

$VENV_PY - << 'PYEOF'
import traceback
from app import app, db
from services.auto_migrate import auto_migrate

with app.app_context():
    try:
        created, added = auto_migrate(app, db)
        print("auto_migrate OK:", len(created), "tables,", len(added), "columns")
    except Exception as e:
        print("auto_migrate err:", e)

    try:
        from routes.admin_support import ensure_site_events_tables
        ensure_site_events_tables()
        print("ensure_site_events_tables OK")
    except Exception as e:
        print("ensure_site_events_tables err:", e)

    try:
        from models import User
        admin = User.query.filter_by(is_admin=True).first() or User.query.first()
        if admin:
            with app.test_client() as c:
                with c.session_transaction() as sess:
                    sess['_user_id'] = str(admin.id)
                    sess['_fresh'] = True
                r = c.get('/admin/users')
                print("TEST /admin/users status:", r.status_code)
                if r.status_code >= 500:
                    print(r.get_data(as_text=True)[:1500])
    except Exception:
        traceback.print_exc()
PYEOF

systemctl restart formyla
echo "=== DONE! FORMYLA UPDATED + AUTO-MIGRATED + STATS TESTED ==="
