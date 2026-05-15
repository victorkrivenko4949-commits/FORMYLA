# -*- coding: utf-8 -*-
"""Patch app.py: when Yandex is already linked to another account,
silently re-link to current account (unlink from old, link to new).
Uses regex on a unique fingerprint, so works with CRLF or LF.
"""
import os, re, sys

sys.stdout.reconfigure(encoding='utf-8')
APP = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'app.py'))

with open(APP, 'r', encoding='utf-8', newline='') as f:
    src = f.read()

if 'перепривязан с аккаунта' in src:
    print('Already patched.')
    sys.exit(0)

# Find the start of the collision branch and end at "}), 409"
# The 409 response is unique to this branch.
start_pat = re.compile(
    r'^([ \t]+)if existing_oauth and existing_oauth\.user_id != current_user\.id:',
    re.MULTILINE,
)
m = start_pat.search(src)
if not m:
    print('ERROR: could not locate start of collision branch')
    sys.exit(2)

start = m.start()
indent = m.group(1)
# Find end marker `}), 409` after the start
end_marker_re = re.compile(r'\}\)\s*,\s*409\s*\r?\n')
em = end_marker_re.search(src, m.end())
if not em:
    print('ERROR: could not locate "}), 409" end marker')
    sys.exit(3)
end = em.end()

new_block = (
    f'{indent}if existing_oauth and existing_oauth.user_id != current_user.id:\n'
    f'{indent}    # КОЛЛИЗИЯ: Я-ID привязан к ДРУГОМУ аккаунту →\n'
    f'{indent}    # ПЕРЕПРИВЯЗАТЬ его на текущего пользователя (по требованию).\n'
    f'{indent}    old_user_id = existing_oauth.user_id\n'
    f'{indent}    existing_oauth.user_id = current_user.id\n'
    f'{indent}    try:\n'
    f'{indent}        db.session.commit()\n'
    f'{indent}    except Exception as _re_link_err:\n'
    f'{indent}        db.session.rollback()\n'
    f'{indent}        print(f"[YANDEX] re-link failed: {{_re_link_err}}")\n'
    f'{indent}        return jsonify({{\n'
    f'{indent}            "success": False,\n'
    f'{indent}            "error": "Не удалось перепривязать Яндекс ID. Попробуйте ещё раз."\n'
    f'{indent}        }}), 500\n'
    f'{indent}    return jsonify({{\n'
    f'{indent}        "success": True,\n'
    f'{indent}        "redirect_url": url_for("profile"),\n'
    f'{indent}        "message": f"Яндекс ID перепривязан с аккаунта #{{old_user_id}} на текущий. Теперь вход через Яндекс ведёт в этот аккаунт.",\n'
    f'{indent}    }})\n'
)

new_src = src[:start] + new_block + src[end:]
with open(APP, 'w', encoding='utf-8', newline='') as f:
    f.write(new_src)

print(f'Patched: replaced {end - start} bytes with {len(new_block)} bytes.')
