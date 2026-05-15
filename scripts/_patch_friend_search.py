# -*- coding: utf-8 -*-
"""Fix friend search:
  1. Backend: search by nickname/name/email; exclude guests; return email.
  2. Frontend: avatar initial fallback so it doesn't crash on missing name."""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_PY = os.path.join(ROOT, "app.py")
FRIENDS_HTML = os.path.join(ROOT, "templates", "friends.html")

# ---------- 1. Patch app.py search_users ----------
with open(APP_PY, "r", encoding="utf-8") as f:
    app_src = f.read()

# Find the function body precisely by regex.
m = re.search(
    r'(@app\.route\("/api/social/search-users"\)\s*\n@login_required\s*\ndef search_users\(\):\s*\n)'
    r'(.*?)(?=\n@app\.route)',
    app_src, re.DOTALL,
)
if not m:
    print("[ERROR] search_users function not found")
    sys.exit(1)

prefix = m.group(1)
old_body = m.group(2)

if "SEARCH_USERS_V2" in old_body:
    print("[skip] search_users already patched")
else:
    new_body = '''    """Search users by nickname / name / email (SEARCH_USERS_V2)."""
    try:
        query = (request.args.get('q', '') or '').strip()
        limit = min(int(request.args.get('limit', 10) or 10), 50)

        if not query or len(query) < 2:
            return jsonify({'success': False, 'users': [], 'error': 'Query too short (min 2 characters)'}), 400

        like = f"%{query}%"
        q = User.query.filter(
            User.id != current_user.id,
            db.or_(
                User.nickname.ilike(like),
                User.name.ilike(like),
                User.email.ilike(like),
            ),
        )
        # Exclude guest accounts from search results.
        try:
            q = q.filter(db.or_(User.is_guest == False, User.is_guest.is_(None)))
        except Exception:
            pass

        users = q.limit(limit).all()

        results = []
        for u in users:
            results.append({
                'id': u.id,
                'nickname': u.nickname or '',
                'name': u.name or '',
                'email': u.email or '',
                'avatar_url': u.avatar_url or '',
                'display_name': u.display_name,
            })

        return jsonify({'success': True, 'users': results})

    except Exception as e:
        import traceback as _tb
        print("[search_users] error:", e)
        print(_tb.format_exc())
        return jsonify({'success': False, 'users': [], 'error': str(e)}), 500

'''
    app_src = app_src[:m.start()] + prefix + new_body + app_src[m.end():]
    with open(APP_PY, "w", encoding="utf-8") as f:
        f.write(app_src)
    print("[ok] app.py search_users patched")

# ---------- 2. Patch templates/friends.html safe initial ----------
with open(FRIENDS_HTML, "r", encoding="utf-8") as f:
    fr_src = f.read()

if "FRIEND_SEARCH_FE_V2" in fr_src:
    print("[skip] friends.html already patched")
    sys.exit(0)

OLD_RENDER = """        data.users.forEach(function(u) {
          var div = document.createElement('div');
          div.className = 'search-result-item';
          div.innerHTML = '<div class="sr-avatar-ph">' + (u.name || u.email)[0].toUpperCase() + '</div>' +
            '<div class="sr-info"><div class="sr-name">' + (u.name || u.email) + '</div>' +
            (u.nickname ? '<div class="sr-nick">@' + u.nickname + '</div>' : '') + '</div>' +
            '<button class="sr-btn" data-uid="' + u.id + '" onclick="sendRequest(this)">Добавить</button>';
          res.appendChild(div);
        });"""

NEW_RENDER = """        // FRIEND_SEARCH_FE_V2
        data.users.forEach(function(u) {
          var label = u.display_name || u.name || u.nickname || u.email || 'Аноним';
          var safeLabel = String(label).replace(/[&<>\"]/g, function(c){
            return ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'})[c];
          });
          var initial = (safeLabel[0] || '?').toUpperCase();
          var avatarHtml = u.avatar_url
            ? '<img class="sr-avatar" src="' + u.avatar_url + '" alt="">'
            : '<div class="sr-avatar-ph">' + initial + '</div>';
          var nickHtml = u.nickname
            ? '<div class="sr-nick">@' + String(u.nickname).replace(/[<>\"]/g,'') + '</div>'
            : '';
          var div = document.createElement('div');
          div.className = 'search-result-item';
          div.innerHTML = avatarHtml +
            '<div class="sr-info"><div class="sr-name">' + safeLabel + '</div>' +
            nickHtml + '</div>' +
            '<button class="sr-btn" data-uid="' + u.id + '" onclick="sendRequest(this)">Добавить</button>';
          res.appendChild(div);
        });"""

if OLD_RENDER in fr_src:
    fr_src = fr_src.replace(OLD_RENDER, NEW_RENDER)
    with open(FRIENDS_HTML, "w", encoding="utf-8") as f:
        f.write(fr_src)
    print("[ok] friends.html render patched")
else:
    print("[WARN] friends.html OLD_RENDER block not found verbatim (check CRLF/LF)")
    # Fallback: regex-replace
    pattern = re.compile(
        r"data\.users\.forEach\(function\(u\) \{.*?\}\);",
        re.DOTALL,
    )
    if pattern.search(fr_src):
        fr_src = pattern.sub(NEW_RENDER, fr_src, count=1)
        with open(FRIENDS_HTML, "w", encoding="utf-8") as f:
            f.write(fr_src)
        print("[ok] friends.html render patched (via regex fallback)")
    else:
        print("[ERROR] could not patch friends.html")
        sys.exit(1)
