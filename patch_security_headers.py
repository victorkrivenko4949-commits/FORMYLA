# -*- coding: utf-8 -*-
"""Patch app.py to add extra security headers to add_security_headers function."""

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

OLD_FUNC = (
    "    except Exception:\n"
    "        pass  # current_user может быть недоступен вне request context\n"
    "    return response"
)

NEW_FUNC = (
    "    except Exception:\n"
    "        pass  # current_user может быть недоступен вне request context\n"
    "    # Базовые security headers для всех ответов\n"
    "    response.headers.setdefault('X-Content-Type-Options', 'nosniff')\n"
    "    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')\n"
    "    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')\n"
    "    return response"
)

if OLD_FUNC in content:
    content = content.replace(OLD_FUNC, NEW_FUNC, 1)
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: Security headers added to add_security_headers()")
else:
    print("ERROR: Pattern not found in app.py - check manually")
    # Print context around line 237
    lines = content.split('\n')
    for i, line in enumerate(lines[230:245], start=231):
        print(f"{i}: {repr(line)}")
