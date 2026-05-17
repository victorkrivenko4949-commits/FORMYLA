# -*- coding: utf-8 -*-
# One-off patch for templates/base.html: replace two olympiad dropdown items
# with a single calendar link. Uses only escape-encoded literals to avoid
# any cyrillic-in-source issues with terminals.
import io

P = "templates/base.html"
src = io.open(P, "r", encoding="utf-8").read()

# Russian text via unicode escapes:
PODG = "\u041f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0430 \u043a \u043e\u043b\u0438\u043c\u043f\u0438\u0430\u0434\u0430\u043c"
MOI_PLANY = "\u041c\u043e\u0438 \u043f\u043b\u0430\u043d\u044b \u043f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0438"
MOI_PROGRESS = "\u041c\u043e\u0439 \u043f\u0440\u043e\u0433\u0440\u0435\u0441\u0441"
KALENDAR = "\u041a\u0430\u043b\u0435\u043d\u0434\u0430\u0440\u044c \u043e\u043b\u0438\u043c\u043f\u0438\u0430\u0434"
PODG_OL = "\u041f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0430 \u043a \u043e\u043b\u0438\u043c\u043f\u0438\u0430\u0434\u0430\u043c"


def patch_desktop(text: str) -> str:
    old = (
        '                    <a href="/olympiad-prep">\U0001f3af ' + PODG + '</a>\n'
        '                    {% if current_user.is_authenticated %}\n'
        '                    <a href="/prep">\U0001f4c5 ' + MOI_PLANY + '</a>\n'
        '                    <a href="{{ url_for(\'olympiad.my_progress\') }}">\U0001f4c8 ' + MOI_PROGRESS + '</a>\n'
        '                    {% endif %}\n'
    )
    new = (
        '                    <a href="{{ url_for(\'olympiad_prep.calendar\') }}">\U0001f4c5 ' + KALENDAR + '</a>\n'
        '                    {% if current_user.is_authenticated %}\n'
        '                    <a href="{{ url_for(\'olympiad.my_progress\') }}">\U0001f4c8 ' + MOI_PROGRESS + '</a>\n'
        '                    {% endif %}\n'
    )
    if old in text:
        return text.replace(old, new)
    return text


def patch_drawer(text: str) -> str:
    # Mobile drawer block — replace the two links with one calendar link.
    old = (
        '            <a href="/olympiad-prep" class="drawer-link">\n'
        '                <span class="drawer-link-icon">\U0001f3af</span>\n'
        '                ' + PODG_OL + '\n'
        '            </a>\n'
        '            {% if current_user.is_authenticated %}\n'
        '            <a href="/prep" class="drawer-link">\n'
        '                <span class="drawer-link-icon">\U0001f4c5</span>\n'
        '                ' + MOI_PLANY + '\n'
        '            </a>\n'
        '            {% endif %}\n'
    )
    new = (
        '            <a href="{{ url_for(\'olympiad_prep.calendar\') }}" class="drawer-link">\n'
        '                <span class="drawer-link-icon">\U0001f4c5</span>\n'
        '                ' + KALENDAR + '\n'
        '            </a>\n'
    )
    if old in text:
        return text.replace(old, new)
    return text


out = patch_desktop(src)
out = patch_drawer(out)

if out == src:
    print("NO CHANGES — patterns not found (already patched?)")
else:
    io.open(P, "w", encoding="utf-8").write(out)
    print("OK: base.html patched")
