# -*- coding: utf-8 -*-
"""Fix Yandex link button in profile.html to use /link_yandex route."""

with open('templates/profile.html', 'r', encoding='utf-8') as f:
    content = f.read()

OLD = "href=\"{{ url_for('yandex_login_start') }}\""
NEW = "href=\"{{ url_for('link_yandex') }}\""

if OLD in content:
    content = content.replace(OLD, NEW, 1)
    with open('templates/profile.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: Button now points to /link_yandex (sets linking_mode=True in session)")
else:
    print("ERROR: Pattern not found - button may already be fixed or has different href")
    # Show context
    import re
    matches = re.findall(r'.{0,50}yandex_login_start.{0,50}', content)
    for m in matches:
        print(f"  Found: {repr(m)}")
