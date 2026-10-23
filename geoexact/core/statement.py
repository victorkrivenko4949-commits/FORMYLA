"""«Проведено и отмечено»: всё, что сказано в условии, есть на чертеже.

Рисунок без дополнительного построения строится по модельному плану, и часть
объектов условия в нём может пропасть: названная медиана не проведена, данное
равенство AB = CD не отмечено засечками, данный угол не подписан, прямой угол
показан без квадратика. Модуль извлекает такие требования прямо из текста
условия и завершает их по решённым координатам.

Каждый добавленный отрезок и каждая отметка проверяются численно ДО того,
как попадут в чертёж (допуски совпадают с гейтом корректности): неверная
геометрия не дорисовывается — о ней по-прежнему сообщает семантический гейт.
Точки, которых нет вообще, достроить нельзя: о них сообщает семантическая
проверка, требующая их от модели.
"""
from __future__ import annotations

import copy
import itertools
import math
import re

import numpy as np

_NAME = r"[A-Z](?:_?\d{1,2})?"
_PAIR = rf"(?:{_NAME})(?:{_NAME})"
_PAIRS = rf"{_PAIR}(?:\s*(?:,|и)\s*{_PAIR})*"

# Названные в условии объекты, которые обязаны быть проведены. Существительное
# стоит перед парами точек («отрезок AD», «медиана AM», «биссектрисы AA_1 и BB_1»)
# или после пары через тире («CM — медиана», «CH — высота»).
_NOUN_BEFORE = re.compile(
    rf"\b(?:отрезк\w*|медиан\w*|биссектрис\w*|высот\w*|диагонал\w*|хорд\w*"
    rf"|средн\w*\s+лин\w*|продолжени\w*\s+сторон\w*"
    rf"|прям(?:ая|ые|ой|ую|ым|ого|ых|я|и))\s+({_PAIRS})\b", re.I)
_NOUN_AFTER = re.compile(
    rf"\b({_PAIR})\s*[—–-]\s*(?:медиан\w*|биссектрис\w*|высот\w*)\b", re.I)

# Данные величины. Предложение с доказательством — цель, а не данность:
# равенство из «докажите, что BE = BF» на чертеже не отмечается.
_PROOF = re.compile(r"докаж|доказать|покаж", re.I)
_EQUAL = re.compile(r"(?<![A-Z_])(?=([A-Z]{2})\s*=\s*([A-Z]{2})(?![A-Z_]))", re.I)
_LENGTH = re.compile(r"(?<![A-Z_])([A-Z]{2})\s*=\s*(\d+(?:[.,]\d+)?)\b", re.I)
_ANGLE3 = re.compile(rf"(?:∠\s*|(?<![А-Яа-яё])уг(?:ол|л)\w*\s+)((?:{_NAME}){{3}})"
                     rf"\s*[;,]?\s*(?:=|рав\w*)\s*(\d+(?:[.,]\d+)?)\s*°?", re.I)
_ANGLE1 = re.compile(rf"(?:∠\s*|(?<![А-Яа-яё])уг(?:ол|л)\w*\s+)((?:{_NAME}))"
                     rf"\s*[;,]?\s*(?:=|рав\w*)\s*(\d+(?:[.,]\d+)?)\s*°?", re.I)
_TRIANGLE = re.compile(r"\bтреугольник\w*\s+([A-Z]{3})\b", re.I)
_PERP = re.compile(rf"\b({_PAIR})\s*(?:⊥|перпендикулярн\w*\s+(?:к\s+)?)\s*({_PAIR})\b",
                   re.I)
_RIGHT_WORD = re.compile(r"\b(?:с\s+)?прямым\s+углом\s+([A-Z])\b", re.I)
_MEDIAN = re.compile(rf"\bмедиан\w*\s+({_PAIRS})\b", re.I)
# «M — середина стороны BC», «точка M является серединой отрезка BC»,
# «M и N — середины сторон AB и AC».
_OF = r"(?:(?:сторон|отрезк|гипотенуз|основани|катет|диагонал|хорд)\w*\s+)?"
_MIDPOINT = re.compile(
    rf"\b({_NAME})\s*(?:[—–-]|является|—\s*это)?\s*середин\w*\s+{_OF}({_PAIR})\b(?!\s*и\s*{_PAIR})", re.I)
_MIDPOINTS2 = re.compile(
    rf"\b({_NAME})\s*(?:и|,)\s*({_NAME})\s*(?:[—–-]|являются)?\s*середин\w*\s+{_OF}"
    rf"({_PAIR})\s*(?:и|,)\s*({_PAIR})\b", re.I)
_BISECTOR = re.compile(rf"\bбиссектрис\w*\s+({_PAIRS})\b", re.I)
_HEIGHT = re.compile(rf"\bвысот\w*\s+({_PAIRS})\b", re.I)

_OPERATOR_BEFORE = re.compile(r"[:/·*×+\-^∙]\s*$")
_OPERATOR_AFTER = re.compile(r"^(?:\s*[:/·*×+\-^∙]|[A-Za-zА-Яа-я(√])")


def _plain_relation(text: str, start: int, end: int) -> bool:
    """Голое утверждение «XY = …», а не член отношения или суммы.

    «BD : DC = 1 : 2» не должно читаться как DC = 1, а «AB + BC = 12» — как
    BC = 12.
    """
    return not (_OPERATOR_BEFORE.search(text[max(0, start - 6):start])
                or _OPERATOR_AFTER.match(text[end:end + 3]))


def _plain(text: str) -> str:
    """Приведение LaTeX-записи углов к обычной: \\angle → ∠, ^\\circ → °."""
    for a, b in ((r"\angle", "∠"), (r"^{\circ}", "°"), (r"^\circ", "°"),
                 (r"\circ", "°"), (r"\(", " "), (r"\)", " "), ("$", " ")):
        text = text.replace(a, b)
    return text


def _split_pairs(chunk: str) -> list[tuple[str, str]]:
    out = []
    for part in re.split(r"\s*(?:,|и)\s*", chunk):
        m = re.fullmatch(rf"({_NAME})({_NAME})", part.strip())
        if m and m[1] != m[2]:
            out.append((m[1], m[2]))
    return out


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.;!?])\s+|\n+", text or "")


def named_segments(text: str) -> list[tuple[str, tuple[str, str]]]:
    """Объекты условия, которые обязаны быть проведены: [(подпись, (X, Y))]."""
    text = _plain(text or "")
    found: list[tuple[str, tuple[str, str]]] = []
    for m in _NOUN_BEFORE.finditer(text):
        for pair in _split_pairs(m[1]):
            found.append((f"{pair[0]}{pair[1]}", pair))
    for m in _NOUN_AFTER.finditer(text):
        for pair in _split_pairs(m[1]):
            found.append((f"{pair[0]}{pair[1]}", pair))
    return list(dict.fromkeys(found))


def statement_requirements(text: str) -> dict:
    """Требования «проведено и отмечено», извлечённые из условия.

    Ключи: segments (названные отрезки), equalities (данные равенства длин),
    lengths (данные длины), angles (данные углы, включая развёрнутые из
    однобуквенной записи «∠A = 40°» по названному треугольнику).
    """
    raw = text or ""
    text = _plain(raw)
    segments = named_segments(raw)

    equalities: list[tuple[tuple[str, str], tuple[str, str]]] = []
    lengths: list[tuple[tuple[str, str], str]] = []
    angles: list[tuple[tuple[str, str, str], str]] = []
    triangles = [t.upper() for t in _TRIANGLE.findall(text)]
    for sentence in _sentences(text):
        if _PROOF.search(sentence):
            continue
        for m in _EQUAL.finditer(sentence):
            left, right = m[1].upper(), m[2].upper()
            end = m.start() + len(re.match(r"[A-Za-z]{2}\s*=\s*[A-Za-z]{2}",
                                           sentence[m.start():], re.I)[0])
            if not _plain_relation(sentence, m.start(), end):
                continue
            if set(left) != set(right):
                equalities.append((tuple(left), tuple(right)))
        for m in _LENGTH.finditer(sentence):
            pair, value = m[1].upper(), m[2]
            if _plain_relation(sentence, m.start(), m.end()):
                lengths.append((tuple(pair), value))
        for m in _ANGLE3.finditer(sentence):
            pts = re.findall(_NAME, m[1])
            if len(pts) == 3 and len(set(pts)) == 3:
                angles.append((tuple(pts), m[2]))
        for m in _ANGLE1.finditer(sentence):
            letter, value = m[1].upper(), m[2]
            for tri in triangles:
                if letter in tri and len(set(tri)) == 3:
                    others = [n for n in tri if n != letter]
                    angles.append(((others[0], letter, others[1]), value))
                    break
    return {"segments": segments, "equalities": equalities,
            "lengths": lengths, "angles": angles}


# ------------------------------------------------------------------ геометрия

def _angle_deg(A, B, C) -> float:
    from .gates import _angle_deg as f
    return f(A, B, C)


def _point_on(P, A, B) -> float | None:
    """Параметр t точки P на прямой AB (None, если P не на прямой)."""
    A, B, P = (np.asarray(q, float) for q in (A, B, P))
    d = B - A
    den = float(d @ d)
    if den < 1e-20:
        return None
    p = P - A
    if abs(float(d[0] * p[1] - d[1] * p[0])) > 1e-7 * den:
        return None
    return float(p @ d) / den


class _Cover:
    """Проведён ли отрезок XY на чертеже — прямо или цепью коллинеарных частей.

    Середина W отрезка I–I_A часто рисуется половинами WI и WI_A: тогда
    отрезок I I_A покрыт цепью и повторно не проводится.
    """

    def __init__(self, plan, Q: dict):
        self.Q = Q
        self.objects = []
        d = plan.draw
        for field, kind in (("segments", "seg"), ("aux_segments", "seg"),
                            ("lines", "line"), ("aux_lines", "line"),
                            ("rays", "ray"), ("aux_rays", "ray"),
                            ("extensions", "line"), ("aux_extensions", "line")):
            for u, v in getattr(d, field):
                if u in Q and v in Q:
                    self.objects.append((np.asarray(Q[u], float),
                                         np.asarray(Q[v], float), kind))

    def __call__(self, x: str, y: str) -> bool:
        X, Y = self.Q.get(x), self.Q.get(y)
        if X is None or Y is None:
            return False
        for A, B, kind in self.objects:
            if ((A == X).all() and (B == Y).all()) or ((A == Y).all() and (B == X).all()):
                return True                   # пара уже есть среди проведённых
        for A, B, kind in self.objects:
            tx, ty = _point_on(X, A, B), _point_on(Y, A, B)
            if tx is None or ty is None:
                continue
            lo, hi = {"seg": (0.0, 1.0), "ray": (0.0, math.inf),
                      "line": (-math.inf, math.inf)}[kind]
            if lo <= min(tx, ty) + 1e-7 and max(tx, ty) - 1e-7 <= hi:
                return True
        return self._chain(X, Y)

    def _chain(self, X, Y) -> bool:
        groups: dict[tuple, list] = {}
        for A, B, kind in self.objects:
            d = B - A
            n = float(np.linalg.norm(d))
            if n < 1e-12:
                continue
            u = d / n
            off = float(u[0] * A[1] - u[1] * A[0])
            key = min((round(float(u[0]), 6), round(float(u[1]), 6), round(off, 6)),
                      (round(-float(u[0]), 6), round(-float(u[1]), 6), round(-off, 6)))
            groups.setdefault(key, []).append((A, B, kind))
        for key, pieces in groups.items():
            A0 = pieces[0][0]
            d0 = pieces[0][1] - A0
            den0 = float(d0 @ d0)
            if den0 < 1e-20:
                continue
            tx = _point_on(X, A0, A0 + d0)
            ty = _point_on(Y, A0, A0 + d0)
            if tx is None or ty is None:
                continue
            if self._covers_span(pieces, A0, d0, tx, ty):
                return True
        return False

    def _covers_span(self, pieces, A, d, tx, ty) -> bool:
        lo, hi = sorted((tx, ty))
        den = float(d @ d)
        spans = []
        for PA, PB, kind in pieces:
            dd = PB - PA
            s = float((PA - A) @ d) / den
            e = s + float(dd @ d) / den
            if kind == "line":
                s, e = -math.inf, math.inf
            elif kind == "ray":
                e = math.inf
            spans.append((min(s, e), max(s, e)))
        spans.sort()
        cur = lo
        for s, e in spans:
            if s > cur + 1e-7:
                return False
            cur = max(cur, e)
        return cur >= hi - 1e-7


# ------------------------------------------------------------------ достройка

def _has_equal_mark(d, pair) -> bool:
    key = frozenset(pair)
    return any(frozenset(m.get("pts", [])) == key for m in d.equal_marks)


def _has_length_mark(d, pair) -> bool:
    key = frozenset(pair)
    return any(frozenset(m.get("pts", [])) == key for m in d.length_marks)


def _free_count(used: set) -> int | None:
    return next((n for n in (1, 2, 3) if n not in used), None)


def _mark_value(s: str) -> float | None:
    from .gates import numeric_mark_value
    return numeric_mark_value(s.replace(",", "."))


def _side_pairs(Q: dict):
    """Все неупорядоченные пары различных точек (для поиска стороны)."""
    keys = sorted(Q)
    return list(itertools.combinations(keys, 2))


def complete_statement_display(plan, coords: dict, text: str):
    """Вернуть (план, сообщения): условие проведено и отмечено на чертеже.

    Сообщение появляется только когда что-то действительно добавлено;
    недостроимое остаётся за семантическим гейтом и здесь лишь перечисляется.
    """
    plan = copy.deepcopy(plan)
    d = plan.draw
    Q = {k: np.asarray(v, dtype=float) for k, v in coords.items()}
    messages: list[str] = []
    if not Q or not text:
        return plan, messages
    try:
        req = statement_requirements(text)
    except Exception:  # noqa: BLE001 - извлечение не должно ломать чертёж
        return plan, messages
    cover = _Cover(plan, Q)
    added: set[frozenset] = set()

    def draw_pair(x, y, why: str) -> None:
        if x not in Q or y not in Q or x == y:
            return
        key = frozenset((x, y))
        if key in added or cover(x, y):
            return
        d.segments.append([x, y])
        added.add(key)
        messages.append(f"STATEMENT_DRAW: проведён отрезок {x}{y} — {why}")

    def dist(a, b) -> float:
        return float(np.linalg.norm(Q[a] - Q[b]))

    # 1) ПРОВЕДЕНО: названные отрезки и отрезки данных равенств и длин.
    for label, (x, y) in req["segments"]:
        if x not in Q or y not in Q:
            miss = [n for n in (x, y) if n not in Q]
            messages.append(f"STATEMENT_MISSING: не проведён отрезок {x}{y}"
                            f" — на чертеже нет точки {' и '.join(miss)}")
            continue
        draw_pair(x, y, "назван в условии")
    for (x, y), (u, v) in req["equalities"]:
        for a, b in ((x, y), (u, v)):
            draw_pair(a, b, "входит в данное равенство")
    for (x, y), _v in req["lengths"]:
        draw_pair(x, y, "имеет данную длину")

    used_lengths = {m.get("count", 1) for m in d.equal_marks}
    used_angles = {m["count"] for m in d.angle_marks if "count" in m}

    # 2) ОТМЕЧЕНО: данные равенства длин — засечками.
    for (x, y), (u, v) in req["equalities"]:
        if not all(n in Q for n in (x, y, u, v)):
            continue
        if abs(dist(x, y) - dist(u, v)) > 1e-4 * max(dist(x, y), dist(u, v), 1e-9):
            continue                        # не выполняется: скажет семантический гейт
        if _has_equal_mark(d, (x, y)) or _has_equal_mark(d, (u, v)):
            continue
        count = _free_count(used_lengths)
        if count is None:
            continue
        for pair in ((x, y), (u, v)):
            draw_pair(*pair, "входит в данное равенство")
            d.equal_marks.append({"pts": [pair[0], pair[1]], "count": count})
        used_lengths.add(count)
        messages.append(f"STATEMENT_MARK: отмечено данное равенство {x}{y} = {u}{v}")

    # данные длины — числами
    for (x, y), value in req["lengths"]:
        if x not in Q or y not in Q:
            continue
        want = _mark_value(value)
        if want is None or want <= 0 \
                or abs(dist(x, y) - want) > max(1e-7, abs(want) * 1e-4):
            continue
        if _has_length_mark(d, (x, y)):
            continue
        draw_pair(x, y, "имеет данную длину")
        d.length_marks.append({"pts": [x, y], "text": value})
        messages.append(f"STATEMENT_MARK: подписана данная длина {x}{y} = {value}")

    def has_angle_mark(a, b, c) -> bool:
        for m in d.angle_marks:
            pts = m.get("pts", [])
            if len(pts) == 3 and pts[1] == b and set(pts) == {a, b, c}:
                if m.get("text") or "count" in m:
                    return True
        return any(len(t) == 3 and t[1] == b and set(t) == {a, b, c}
                   for t in d.right_angles)

    # данные углы — дугами с числом; 90° — квадратиком прямого угла
    for (a, b, c), value in req["angles"]:
        if not all(n in Q for n in (a, b, c)):
            continue
        want = _mark_value(value)
        if want is None or not math.isfinite(want) or not 0 < want < 360:
            continue
        got = _angle_deg(Q[a], Q[b], Q[c])
        if not math.isfinite(got) or abs(got - want) > 0.01:
            continue
        if has_angle_mark(a, b, c):
            continue
        if abs(want - 90) < 1e-9:
            d.right_angles.append([a, b, c])
            messages.append(f"STATEMENT_MARK: отмечен прямой угол {a}{b}{c} = 90°")
        else:
            d.angle_marks.append({"pts": [a, b, c], "text": f"{value}°"})
            messages.append(f"STATEMENT_MARK: подписан данный угол {a}{b}{c} = {value}°")

    _add_derived_marks(plan, Q, text, cover, used_lengths, used_angles, messages,
                       draw_pair)
    return plan, list(dict.fromkeys(messages))


def _add_derived_marks(plan, Q, text, cover, used_lengths, used_angles, messages,
                       draw_pair) -> None:
    """Отметки, следующие из слов «медиана», «биссектриса», «высота», «перпендикуляр»."""
    d = plan.draw
    text = _plain(text or "")

    def dist(a, b) -> float:
        return float(np.linalg.norm(Q[a] - Q[b]))

    def mark_halves(f, u, w) -> bool:
        """Точка f делит отрезок uw пополам: половины получают общие засечки."""
        if f not in Q or u not in Q or w not in Q or len({f, u, w}) != 3:
            return False
        t = _point_on(Q[f], Q[u], Q[w])
        if t is None or not 0.01 < t < 0.99:
            return False
        if abs(dist(u, f) - dist(f, w)) > 1e-5 * max(dist(u, f), 1e-9):
            return False
        halves = ([u, f], [f, w])
        if any(_has_equal_mark(d, h) or _has_length_mark(d, h) for h in halves):
            return True
        count = _free_count(used_lengths)
        if count is None:
            return False
        # сторону, проведённую целиком, делим на две половины
        for i, s in enumerate(d.segments):
            if {s[0], s[1]} == {u, w}:
                d.segments[i:i + 1] = halves
                break
        else:
            if not (cover(u, f) and cover(f, w)):
                return False
        for h in halves:
            d.equal_marks.append({"pts": h, "count": count})
        used_lengths.add(count)
        return True

    # медиана VM: половины стороны равны — засечки на них
    for m in _MEDIAN.finditer(text):
        for v, f in _split_pairs(m[1]):
            if v not in Q or f not in Q or v == f:
                continue
            for u, w in _side_pairs(Q):
                if v in (u, w) or f in (u, w):
                    continue
                if mark_halves(f, u, w):
                    draw_pair(v, f, "медиана названа в условии")
                    messages.append(f"STATEMENT_MARK: медиана {v}{f} — половины стороны "
                                    f"{u}{f} и {f}{w} отмечены равными")
                    break

    # «M — середина BC»: половины равны, даже если медиана не названа
    for m in _MIDPOINT.finditer(text):
        f, pair = m[1].upper(), _split_pairs(m[2])
        if pair and mark_halves(f, pair[0][0], pair[0][1]):
            messages.append(f"STATEMENT_MARK: {f} — середина {pair[0][0]}{pair[0][1]}, "
                            f"половины отмечены равными")
    for m in _MIDPOINTS2.finditer(text):
        first, second = _split_pairs(m[3]), _split_pairs(m[4])
        for f, pair in ((m[1].upper(), first), (m[2].upper(), second)):
            if pair and mark_halves(f, pair[0][0], pair[0][1]):
                messages.append(f"STATEMENT_MARK: {f} — середина {pair[0][0]}{pair[0][1]}, "
                                f"половины отмечены равными")

    # биссектриса VF: половины угла равны — дуги с одинаковым числом штрихов
    for m in _BISECTOR.finditer(text):
        for v, f in _split_pairs(m[1]):
            if v not in Q or f not in Q or v == f:
                continue
            if any(len(mm.get("pts", [])) == 3 and mm["pts"][1] == v and "count" in mm
                   for mm in d.angle_marks):
                continue                   # у вершины уже есть равные дуги
            for u, w in _side_pairs(Q):
                if v in (u, w) or f in (u, w):
                    continue
                t = _point_on(Q[f], Q[u], Q[w])
                if t is None or not 0.01 < t < 0.99:
                    continue
                left = _angle_deg(Q[u], Q[v], Q[f])
                right = _angle_deg(Q[f], Q[v], Q[w])
                if not (math.isfinite(left) and math.isfinite(right)) \
                        or abs(left - right) > 0.01:
                    continue
                count = _free_count(used_angles)
                if count is None:
                    continue
                d.angle_marks.append({"pts": [u, v, f], "count": count})
                d.angle_marks.append({"pts": [f, v, w], "count": count})
                used_angles.add(count)
                draw_pair(v, f, "биссектриса названа в условии")
                messages.append(f"STATEMENT_MARK: биссектриса {v}{f} — половины угла "
                                f"{u}{v}{f} и {f}{v}{w} отмечены равными дугами")
                break

    # перпендикулярность и прямые углы словами
    right_triples = []
    for m in _PERP.finditer(text):
        first, second = _split_pairs(m[1]), _split_pairs(m[2])
        if not first or not second:
            continue
        (a, b), (c, e) = first[0], second[0]
        shared = {a, b} & {c, e}
        if shared:
            s = shared.pop()
            right_triples.append((a if b == s else b, s, c if e == s else e))
    for m in _RIGHT_WORD.finditer(text):
        letter = m[1].upper()
        tri = _TRIANGLE.search(text)
        if tri and letter in tri[1].upper() and len(set(tri[1].upper())) == 3:
            others = [n for n in tri[1].upper() if n != letter]
            right_triples.append((others[0], letter, others[1]))
    for m in _HEIGHT.finditer(text):
        for v, h in _split_pairs(m[1]):
            if v not in Q or h not in Q:
                continue
            for u, w in _side_pairs(Q):
                if v in (u, w) or h in (u, w):
                    continue
                if _point_on(Q[h], Q[u], Q[w]) is None:
                    continue
                if abs(_angle_deg(Q[v], Q[h], Q[u]) - 90) > 0.01:
                    continue
                right_triples.append((v, h, u))
                break
    for a, b, c in dict.fromkeys(right_triples):
        if not all(n in Q for n in (a, b, c)):
            continue
        if any(len(t) == 3 and t[1] == b and set(t) == {a, b, c} for t in d.right_angles):
            continue
        got = _angle_deg(Q[a], Q[b], Q[c])
        if not math.isfinite(got) or abs(got - 90) > 0.01:
            continue
        d.right_angles.append([a, b, c])
        messages.append(f"STATEMENT_MARK: отмечен прямой угол при {b} ({a}{b}{c} = 90°)")
