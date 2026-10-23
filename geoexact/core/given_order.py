# -*- coding: utf-8 -*-
"""«Равны a и b соответственно»: данные длины в порядке упоминания объектов.

Повод (задача о медианах, живая генерация 23.10.2026): условие «медианы из A
и B ... равны 9 и 12 соответсвенно» формализатор переложил на план как
dist(A, A_1) = 12, dist(B, B_1) = 9 — порядок перепутан. Чертёж при этом
самосогласован (гейт верификации проходит), площадь не выдаёт подмену, и
неверный чертёж уходил пользователю без единого предупреждения.

Правило формализатора (правило 36) требует соблюдать порядок упоминания.
Проверка после формализации: для каждой фразы «равны a и b соответственно»
ищем в предложении пары объектов «X и Y» и смотрим dist-ограничения плана:
какой длиной план пометил объект X, какой — Y. Если ровно переставлено
(X получил b, Y получил a, a ≠ b) — порядок исправляем сам (обмен значений
двух dist-ограничений и текстов их подписей): фигура та же, длины встают
на свои места. Если трактовка неоднозначна (объект в нескольких dist, пары
противоречат друг другу) — не трогаем: лучше видимый гейт, чем слепая правка.

Обёртка без правки llm.py: install(llm) подменяет llm.formalize (пост-проверка
плана) и дописывает правило в SYS_FORMALIZE / SYS_AUX. Повторно — no-op.
GEOEXACT_GIVEN_ORDER=0 выключает.
"""
from __future__ import annotations

import os
import re
from functools import wraps

ENABLED = (os.environ.get("GEOEXACT_GIVEN_ORDER") or "1").strip().lower() not in ("0", "no", "off")

MARK = "GIVEN_ORDER"          # признак того, что правило уже дописано

EXTRA_RULES = """
36. GIVEN_ORDER: «Равны a и b соответственно» — строго по порядку упоминания: ПЕРВЫЙ
    объект получает a, ВТОРОЙ — b. «Медианы из A и B равны 9 и 12 соответственно» —
    значит dist(A, A_1) = 9 и dist(B, B_1) = 12, а не наоборот. Перепутанный
    порядок движок исправит сам, но не полагайся на это: перечитай, какой
    объект упомянут первым, и проверь значения в constraints.
"""

# «равны 9 и 12 соответственно» (опечатка «соответсвенно» допустима)
_NUMS = re.compile(r"равн\w*\s+(\d+(?:[.,]\d+)?)\s+и\s+(\d+(?:[.,]\d+)?)\s+соответ", re.I)
# пара объектов: имена точек плана (A, B, A1, A_1, M1)
_PAIR = re.compile(r"(?<![A-ZА-Я])([A-Z](?:[0-9]|_[0-9])?)\s+и\s+([A-Z](?:[0-9]|_[0-9])?)(?![A-Z0-9])")
_TRAILING_NUM = re.compile(r"(\d+(?:\.\d+)?)\s*$")


def _norm(name: str) -> str:
    """«A1» из условия → «A_1» плана (если такой есть в dist)."""
    return name


def _alt(name: str) -> str:
    """Альтернативное имя: A1 → A_1."""
    if "_" not in name and len(name) > 1 and name[-1].isdigit():
        return name[:-1] + "_" + name[-1]
    return name


def _dists(plan):
    out = []
    for c in getattr(plan, "constraints", None) or []:
        if getattr(c, "type", None) == "dist" and c.value is not None and len(c.args) == 2:
            out.append(c)
    return out


def _touching(dists, name: str):
    """dist-ограничения, чей отрезок содержит точку name (без второй точки пары)."""
    return [c for c in dists if name in c.args]


def _fix_mark_texts(plan, dist_a, dist_b, old_a, old_b):
    """Обновить тексты подписей длин у обменённых отрезков."""
    pair_a, pair_b = frozenset(dist_a.args), frozenset(dist_b.args)
    for m in getattr(getattr(plan, "draw", None), "length_marks", None) or []:
        pts = frozenset(m.get("pts") or [])
        text = m.get("text")
        if not isinstance(text, str) or len(pts) != 2:
            continue
        if pts == pair_a and _TRAILING_NUM.search(text) and abs(float(_TRAILING_NUM.search(text).group(1)) - old_b) < 1e-9:
            m["text"] = _TRAILING_NUM.sub(lambda _: _fmt(old_a), text)
        elif pts == pair_b and _TRAILING_NUM.search(text) and abs(float(_TRAILING_NUM.search(text).group(1)) - old_a) < 1e-9:
            m["text"] = _TRAILING_NUM.sub(lambda _: _fmt(old_b), text)


def _fmt(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else repr(v)


def repair(text: str, plan) -> bool:
    """Исправить перепутанный порядок «соответственно». True — если исправлено."""
    dists = _dists(plan)
    if len(dists) < 2:
        return False
    fixed = False
    for m in _NUMS.finditer(text):
        a, b = float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))
        if a == b:
            continue                      # равные длины — порядок не различить
        window = text[max(0, m.start() - 320):m.end()]
        swap_pair = None                  # (dist_X, dist_Y): X получил b, Y получил a
        correct = False
        for pm in _PAIR.finditer(window):
            x, y = pm.group(1), pm.group(2)
            for nx, ny in ((x, y), (_alt(x), _alt(y))):
                tx = [c for c in dists if nx in c.args]
                ty = [c for c in dists if ny in c.args]
                if len(tx) != 1 or len(ty) != 1 or tx[0] is ty[0]:
                    continue
                vx, vy = float(tx[0].value), float(ty[0].value)
                if abs(vx - b) < 1e-9 and abs(vy - a) < 1e-9:
                    swap_pair = (tx[0], ty[0])
                elif abs(vx - a) < 1e-9 and abs(vy - b) < 1e-9:
                    correct = True
                break
            if swap_pair or correct:
                break
        if swap_pair is not None and not correct:
            dx, dy = swap_pair
            va, vb = float(dx.value), float(dy.value)
            dx.value, dy.value = a, b
            _fix_mark_texts(plan, dx, dy, a, b)
            note = (f"Порядок «соответственно» исправлен: "
                    f"{''.join(dx.args)} = {_fmt(a)}, {''.join(dy.args)} = {_fmt(b)}.")
            plan.notes = ((plan.notes + " ") if getattr(plan, "notes", None) else "") + note
            fixed = True
    return fixed


def _append_rules(llm_module) -> bool:
    base = getattr(llm_module, "SYS_FORMALIZE", None)
    aux = getattr(llm_module, "SYS_AUX", None)
    if not isinstance(base, str) or MARK in base:
        return False
    llm_module.SYS_FORMALIZE = base.rstrip() + "\n" + EXTRA_RULES.rstrip() + "\n"
    if isinstance(aux, str):
        if aux.startswith(base):
            llm_module.SYS_AUX = llm_module.SYS_FORMALIZE + aux[len(base):]
        elif MARK not in aux:
            llm_module.SYS_AUX = aux.rstrip() + "\n" + EXTRA_RULES.rstrip() + "\n"
    return True


def install(llm_module) -> bool:
    """Правило в промпты + пост-проверка плана после formalize. Повторно — no-op."""
    if not ENABLED:
        return False
    done = _append_rules(llm_module)
    orig = getattr(llm_module, "formalize", None)
    if orig is not None and not getattr(orig, "_given_order", False):
        @wraps(orig)
        def formalize(sess, text, *args, **kwargs):
            plan, warn = orig(sess, text, *args, **kwargs)
            try:
                if repair(text, plan):
                    warn = [str(w) for w in (warn or [])] + \
                        ["GIVEN_ORDER_FIXED: перепутанный порядок «равны ... соответственно» исправлен"]
            except Exception:              # noqa: BLE001 - проверка не должна валить формализацию
                pass
            return plan, warn
        formalize._given_order = True
        llm_module.formalize = formalize
        done = True
    return done
