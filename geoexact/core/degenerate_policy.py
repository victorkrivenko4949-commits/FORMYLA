"""Вырожденность с учётом семантики плана: законные конфигурации не бракуются.

Повод. Коммит 7585ffd1 научил решатель отвергать вырожденные фигуры
(DEGENERATE_FIGURE в solver._finish). Защита нужная, но она не знала семантики
плана и браковала законные чертежи:

  1) Трисектор-задача (semantics.trisected_parallel_plan): D лежит на
     продолжении CA за A, поэтому A, C, D коллинеарны ПО УСЛОВИЮ, а отрезки
     AC, AD и CD нарисованы — «треугольник ACD» схлопнулся. Решатель
     отбрасывал единственное верное решение, конвейер повторял запросы к
     модели и в итоге показывал approximate со словами «условия выполнены
     лишь приближённо». Падали test_trisector_* и test_generic_figure.
  2) Высота CH при H=foot(C,A,B) и медиана AM при M=midpoint(A,B) в
     равнобедренном случае дают H≡M — ТОЧНОЕ совпадение построенных точек.
     Гейт корректности относится к нему как к предупреждению
     (CONSTRUCTED_COINCIDENCE), а решатель — как к отказу. Падали
     test_right_angles_marked и test_equal_colors.

Что делает модуль (обёртки, как convexity / general_position, без правки
solver.py, gates.py и semantics.py):

  1) solver._drawn_triangles заменяется на gates._draw_triangles: тот же
     граф отрезков, но тройки, объявленные коллинеарными конструкциями
     (midpoint, divide_segment, foot, line_intersect, …) или ограничениями
     (collinear, on_segment), из списка вычёркиваются. Это чинит и мягкий
     штраф решателя: он больше не воюет с ограничением on_segment за
     «плоскость» законно вырожденного треугольника.
  2) solver.degenerate_figure оборачивается:
       - совпадение двух СВОБОДНЫХ точек — по-прежнему отказ (как
         COINCIDENT_POINTS в гейте);
       - ТОЧНОЕ совпадение (≤ 1e-9 габарита), в котором участвует построенная
         точка, — не отказ решателя: это либо законная геометрия (H=foot ≡
         M=midpoint в равнобедренном треугольнике), либо ошибка формализации
         («медиана BD» с D≡A) — обе решаются дальше по конвейеру, гейтами
         и текстовыми проверками, см. пункт 3 и UNDRAWABLE_SEGMENT;
       - «почти слипшиеся» РАЗНЫЕ точки (< DEGEN_POINT_FRAC габарита,
         но не точное совпадение) — по-прежнему отказ: чертёж с двумя
         неотличимыми точками не показываем.
  3) Ошибки формализации, которые точечные совпадения вскрывают, ловятся
     текстовыми проверками (жёсткие, как convexity/radius_claims):
       - «треугольник ABC» (или △ABC) с нулевой площадью — NAMED_FIGURE;
         раньше решатель сам отвергал «отрезок вместо треугольника»
         (C=midpoint(A,B)), теперь это видит текст по имени фигуры;
       - «медиана BD» — D обязан быть серединой противоположной стороны
         названного треугольника; «высота BD» — перпендикулярной ей и не
         совпадать с вершиной. Без этого «медиана BD» с D=line_intersect,
         совпавшим с вершиной A, и скрытой меткой D проходила как
         «проверено»: решатель видит законное совпадение, гейт — псевдоним,
         а числовой проверки медианы не было.
    Итог: существенное условие либо проверяется по тексту независимо от
    плана, либо понижает статус (approximate/sketch) с причиной в предупреждениях.

GEOEXACT_DEGENERATE_POLICY=0 выключает всё; к pipeline.ENGINE_VERSION
дописывается суффикс, чтобы старые кэши не выдавали чертежи, отвергнутые
старой политикой.
"""
from __future__ import annotations

import itertools
import os
import re

import numpy as np

ENABLED = (os.environ.get("GEOEXACT_DEGENERATE_POLICY") or "1").strip().lower() not in ("0", "no", "off")
CACHE_SUFFIX = "+dgp3"
_EPS = 1e-12
# точное совпадение построенных точек — факт геометрии, а не дефект
# (гейт: CONSTRUCTED_COINCIDENCE / совпадение с скрытым псевдонимом)
EXACT_COINCIDE = 1e-9
PREFIX = "NAMED_FIGURE: "
PPREFIX = "PARALLELOGRAM: "

TRI_NAME = re.compile(r"(?:[Тт]реугольник\w*|△)\s*([A-Z]{3})\b")
_QUAD_NAME = re.compile(r"(?:четыр[её]хугольник\w*|четырехугольник\w*)\s*([A-Z]{4})\b")
# «медиана AM», «медианы AD и BE», «AM — медиана», «высота CH».
# (?<![A-Z]) в первой альтернативе: без него «в треугольнике BLC — медиану
# BM» парсилась как «LC — медиана» и проверка требовала C быть серединой
# стороны названного треугольника, в которой она не состоит.
_CEVIAN = re.compile(r"(?<![A-Z])(медиан|высот)\w*\s+([A-Z]{2})"
                     r"|(?<![A-Z])([A-Z]{2})\s*[—–-]\s*(?:это\s+)?(медиан|высот)\w*", re.I)
_HYPOTHETICAL = re.compile(r"может\s+ли|верно\s+ли|возможно\s+ли|если\s+бы|предполож|неверно",
                           re.I)


def _free_points(plan) -> set[str]:
    return {c.out for c in (getattr(plan, "constructions", None) or [])
            if getattr(c, "op", None) == "free_point"}


def _plain(text: str) -> str:
    try:
        from .convexity import _plain as p
        return p(text)
    except Exception:  # noqa: BLE001
        return (text or "").replace("$", " ")


def named_polygons(text: str) -> list[tuple[str, ...]]:
    """Треугольники и четырёхугольники, названные в условии по вершинам."""
    plain = _plain(text)
    out: list[tuple[str, ...]] = []
    for rx, size in ((TRI_NAME, 3), (_QUAD_NAME, 4)):
        for m in rx.finditer(plain):
            names = tuple(m[1].upper())
            if len(set(names)) == size:
                out.append(names)
    return list(dict.fromkeys(out))


def _cevians(text: str) -> list[tuple[str, str, str]]:
    """[(тип, вершина, основание)] из фраз «медиана BD», «CH — высота» и т. п."""
    out: list[tuple[str, str, str]] = []
    for sentence in re.split(r"(?<=[.;!?])\s+", _plain(text)):
        if _HYPOTHETICAL.search(sentence):
            continue
        for m in _CEVIAN.finditer(sentence):
            if m[2]:        # «медиана BD»
                kind, seg = ("медиана" if m[1].lower().startswith("медиан") else "высота"), m[2]
            else:           # «BD — медиана»
                kind, seg = ("медиана" if m[4].lower().startswith("медиан") else "высота"), m[3]
            if len(set(seg)) == 2:
                out.append((kind, seg[0], seg[1]))
    return list(dict.fromkeys(out))


def cevian_failures(text: str, plan, coords: dict) -> list[str]:
    """«Медиана BD» — D середина противоположной стороны; «высота BD» — ⟂ и не вершина.

    Основание проверяется относительно названных в условии треугольников.
    Семантика — «существует сторона»: чевиана валидна, если она является
    медианой/высотой ХОТЯ БЫ ОДНОЙ из них. Раньше требовалось совпадение
    со всеми сторонами — ложное «приближённо» на текстах вида «в треугольнике
    ABC проведена медиана BM … площади треугольников ABM и MBC» (M — конец,
    а не середина стороны AM треугольника ABM). Без названного треугольника
    (или без точки на чертеже) проверка пропускается — отсутствие точек ловят
    statement-проверки. Вырожденные стороны (P≈Q) пропускаются.
    """
    fails: list[str] = []
    triangles = [t for t in named_polygons(text) if len(t) == 3]
    for kind, vertex, foot in _cevians(text):
        if foot not in coords or vertex not in coords:
            continue
        sides = [tuple(p for p in tri if p != vertex) for tri in triangles if vertex in tri]
        sides = [s for s in sides if all(p in coords for p in s)]
        if not sides:
            continue
        V, F = np.asarray(coords[vertex], dtype=float), np.asarray(coords[foot], dtype=float)
        matched, checked = False, False
        for p, q in sides:
            P, Q = np.asarray(coords[p], dtype=float), np.asarray(coords[q], dtype=float)
            if float(np.linalg.norm(Q - P)) <= 1e-6:      # вырожденная сторона
                continue
            checked = True
            scale = max(float(np.linalg.norm(Q - P)), float(np.linalg.norm(V - P)),
                        float(np.linalg.norm(V - Q)), 1e-9)
            cross = abs(float(np.linalg.det(np.array([Q - P, F - P]))))
            if kind == "медиана":
                ok = cross <= 1e-5 * scale * scale and \
                    abs(float(np.linalg.norm(F - P)) - float(np.linalg.norm(F - Q))) \
                    <= 1e-4 * scale
            else:
                along = abs(float((F - V) @ (Q - P)))
                near = min(float(np.linalg.norm(F - P)), float(np.linalg.norm(F - Q)))
                ok = cross <= 1e-5 * scale * scale and along <= 1e-4 * scale * scale \
                    and near > 1e-5 * scale
            if ok:
                matched = True
                break
        if checked and not matched:
            side_names = ", ".join(f"{p}{q}" for p, q in sides)
            if kind == "медиана":
                fails.append(
                    f"CEVIAN: медиана {vertex}{foot} — {foot} не является серединой "
                    f"ни одной из сторон ({side_names}). Строй {foot}=midpoint(p,q) "
                    f"подходящей стороны и рисуй [{vertex},{foot}] в draw.segments")
            else:
                fails.append(
                    f"CEVIAN: высота {vertex}{foot} не перпендикулярна сторонам "
                    f"({side_names}) или её основание совпало с вершиной. Строй "
                    f"{foot}=foot({vertex},p,q) и рисуй [{vertex},{foot}]")
    return list(dict.fromkeys(fails))


# «BB₁CC₁ — параллелограмм», «ABCD — параллелограмм», «в параллелограмме
# BB₁CC₁»: semantics видит только «четырёхугольник XXXX — параллелограмм»
# и «параллелограмм XXXX» с четырьмя ОДИНОЧНЫМИ буквами ([A-Z]{4}). Форму
# без слова «четырёхугольник» и индексные имена (B₁) он не замечает — неверный
# чертёж с такой формулировкой проходил как «проверено».
_NAME = r"[A-Z](?:_\d+)?"
_QUAD_GROUP = r"(?P<quad>" + _NAME * 4 + ")"
PARALLELOGRAM_CLAIM = re.compile(
    r"(?<![A-Za-zА-Яа-яЁё_])(?:(?P<pre>(?i:четыр[её]хугольник\w*))\s+)?" + _QUAD_GROUP
    + r"(?![A-Za-zА-Яа-яЁё_])\s*(?:[-—–:]\s*)?(?:(?i:это|и|является)\s+)?"
    + r"(?P<word>(?i:параллелограмм\w*))"
    r"|(?P<word2>(?i:параллелограмм\w*))\s+(?:(?i:это)\s+)?"
    + _QUAD_GROUP.replace("(?P<quad>", "(?P<quad2>")
    + r"(?![A-Za-zА-Яа-яЁё_0-9])")

# формулировки, которые проверяет semantics (дубли не нужны)
_SEMANTICS_PARA = re.compile(
    r"\b(?:четырёхугольник|четырехугольник)\s+([A-Z]{4})\s*"
    r"(?:[-—–:]?\s*)?параллелограмм\b"
    r"|\bпараллелограмм\s+([A-Z]{4})\b", re.I)


def parallelogram_names(text: str) -> list[tuple[str, ...]]:
    """Пары-четвёрки имён из фраз «BB₁CC₁ — параллелограмм» и родственных.

    Дубли семантики пропускаются: если все четыре имени — одиночные буквы
    и формулировка совпадает с одной из двух, покрытых semantics
    («четырёхугольник XXXX — параллелограмм», «параллелограмм XXXX»),
    проверку делает semantics, а не этот модуль.
    """
    plain = _plain(text)
    covered = {m[1] or m[2] for m in _SEMANTICS_PARA.finditer(plain)}
    out: list[tuple[str, ...]] = []
    for m in PARALLELOGRAM_CLAIM.finditer(plain):
        quad = m["quad"] or m["quad2"] or ""
        names = tuple(re.findall(r"[A-Z](?:_\d+)?", quad))
        if len(names) != 4:
            continue
        if all(len(n) == 1 for n in names) and "".join(names) in covered:
            continue          # эту формулировку проверяет semantics
        out.append(names)
    return list(dict.fromkeys(out))


def parallelogram_failures(text: str, plan, coords: dict) -> list[str]:
    """Названный параллелограмм обязан им быть и быть показанным всеми сторонами.

    Отсутствие вершин — не повод молчать (как в semantics-проверке):
    названный в тексте параллелограмм без вершины на чертеже — жёсткая
    ошибка, конвейер переспросит модель.
    """
    fails: list[str] = []
    try:
        segments = {frozenset(s) for s in (plan.draw.segments or [])}
    except Exception:  # noqa: BLE001
        segments = set()
    for names in parallelogram_names(text):
        label = "".join(names)
        missing = [n for n in names if n not in coords]
        if missing or len(set(names)) != 4:
            fails.append(f"{PPREFIX}отсутствуют вершины параллелограмма {label}: "
                         f"{', '.join(missing)}")
            continue
        try:
            V = [np.asarray(coords[n], dtype=float) for n in names]
            if any(v.shape != (2,) or not np.isfinite(v).all() for v in V):
                continue
            edges = [V[(i + 1) % 4] - V[i] for i in range(4)]
            scale = max(*(float(np.linalg.norm(e)) for e in edges), 1e-9)
            turns = [float(np.linalg.det(np.array([edges[i], edges[(i + 1) % 4]])))
                     for i in range(4)]
            cross = lambda u, v: abs(float(np.linalg.det(np.array([u, v]))))  # noqa: E731
            label = "".join(names)
            if (min(float(np.linalg.norm(e)) for e in edges) < 1e-5 * scale
                    or not (all(t > 1e-5 * scale * scale for t in turns)
                            or all(t < -1e-5 * scale * scale for t in turns))
                    or cross(edges[0], edges[2]) > 1e-5 * scale * scale
                    or cross(edges[1], edges[3]) > 1e-5 * scale * scale
                    or float(np.linalg.norm(edges[0] + edges[2])) > 1e-4 * scale):
                fails.append(f"{PPREFIX}{label} не является невырожденным "
                             "параллелограммом — проверь порядок вершин в имени "
                             "и построение точек")
            sides = {frozenset((names[i], names[(i + 1) % 4])) for i in range(4)}
            if not sides <= segments:
                fails.append(f"{PPREFIX}не все стороны параллелограмма {label} "
                             "показаны — добавь их в draw.segments")
        except Exception:  # noqa: BLE001 — проверка не должна ломать гейт
            continue
    return list(dict.fromkeys(fails))


def named_figure_failures(text: str, plan, coords: dict) -> list[str]:
    """«Треугольник ABC» на чертеже обязан иметь ненулевую площадь.

    Восстанавливает защиту коммита 7585ffd1 для главного случая — модель
    строит вершины треугольника друг из друга (C=midpoint(A,B)) и рисует
    отрезок вместо треугольника: решатель такую фигуру больше не
    отвергает (коллинеарность объявлена конструкцией), зато текст
    называет фигуру треугольником — и проверка по координатам это видит.
    """
    fails: list[str] = []
    for names in named_polygons(text):
        if not all(p in coords for p in names):
            continue                 # отсутствие точек — забота statement-проверок
        try:
            V = [np.asarray(coords[p], dtype=float) for p in names]
            if any(v.shape != (2,) or not np.isfinite(v).all() for v in V):
                continue
            n = len(V)
            scale = max(float(np.linalg.norm(V[(i + 1) % n] - V[i])) for i in range(n))
            if scale <= 1e-12:
                fails.append(f"{PREFIX}{''.join(names)} вырожден: все вершины совпали")
                continue
            area2 = abs(sum(float(np.linalg.det(np.array([V[i], V[(i + 1) % n]])))
                            for i in range(n)))
            if area2 <= 1e-6 * scale * scale:
                kind = "треугольник" if n == 3 else "четырёхугольник"
                fails.append(
                    f"{PREFIX}{kind} {''.join(names)} вырожден: вершины на одной прямой. "
                    "Вершины названной фигуры задавай free_point, а не конструкциями "
                    "друг из друга (midpoint/translate/line_intersect и т. п.)")
        except Exception:  # noqa: BLE001 — проверка не должна ломать гейт
            continue
    fails += cevian_failures(text, plan, coords)
    fails += parallelogram_failures(text, plan, coords)
    return fails


# ------------------------------------------------------------------ обёртки
def _wrap_drawn_triangles(solver_module) -> bool:
    """Тройки-циклы отрезков решателя без объявленных коллинеарных.

    Список гейта шире (добавляет тройки из right_angles/angle_marks) — его
    нельзя подставлять в решатель: необъявленный «плоский» отмеченный угол
    стал бы вырождением. Берём ИСХОДНЫЙ список решателя и вычёркиваем
    только тройки, коллинеарность которых объявлена конструкциями или
    ограничениями (как делает gates._draw_triangles).
    """
    orig = getattr(solver_module, "_drawn_triangles", None)
    if orig is None or getattr(orig, "_degenerate_policy", False):
        return False

    def _drawn_triangles(plan):
        tris = orig(plan)
        try:
            from .gates import _incidence_claims
            collinear = {frozenset((p, a, b)) for p, a, b in _incidence_claims(plan)[0]}
            for c in (getattr(plan, "constraints", None) or []):
                if getattr(c, "type", None) == "collinear" and len(c.args) == 3:
                    collinear.add(frozenset(c.args))
            return [t for t in tris if frozenset(t) not in collinear]
        except Exception:  # noqa: BLE001 — политика не должна ломать решатель
            return tris

    _drawn_triangles._degenerate_policy = True
    _drawn_triangles._original = orig
    _drawn_triangles.__doc__ = getattr(orig, "__doc__", None)
    _drawn_triangles.__name__ = "_drawn_triangles"
    solver_module._drawn_triangles = _drawn_triangles
    return True


def _wrap_degenerate_figure(solver_module) -> bool:
    """Совпадение точек — отказ, кроме ТОЧНОГО совпадения с построенной точкой.

    Прочее — как в оригинальном solver.degenerate_figure (пороги читаются из
    модуля решателя, чтобы остаться с ним в синхроне): нулевой габарит,
    совпадение свободных точек, «почти слипшиеся» разные точки и схлопнувшийся
    необъявленный треугольник по-прежнему вырождение.
    """
    orig = getattr(solver_module, "degenerate_figure", None)
    if orig is None or getattr(orig, "_degenerate_policy", False):
        return False

    def degenerate_figure(plan, coords: dict) -> str:
        try:
            visible = [n for n in (plan.points or []) if n in coords
                       and n not in set(getattr(plan.draw, "hide_labels", []) or [])]
            if len(visible) < 2:
                return ""
            P = {n: np.asarray(coords[n], dtype=float) for n in visible}
            arr = np.array(list(P.values()))
            span = float(np.max(arr.max(axis=0) - arr.min(axis=0)))
            eps = float(getattr(solver_module, "_EPS", _EPS))
            if span <= eps:
                return "все точки совпали"
            free = _free_points(plan)
            point_frac = float(getattr(solver_module, "DEGEN_POINT_FRAC", 0.004))
            for a, b in itertools.combinations(visible, 2):
                dist = float(np.hypot(*(P[a] - P[b])))
                if dist >= point_frac * span:
                    continue
                if a in free and b in free:
                    return f"точки {a} и {b} совпали"
                if dist <= EXACT_COINCIDE * span and (a not in free or b not in free):
                    continue     # точное совпадение с построенной точкой — см. докстринг
                return f"точки {a} и {b} слиплись ({dist / span:.4%} габарита)"
            area_frac = float(getattr(solver_module, "DEGEN_AREA_FRAC", 2e-4))
            for a, b, c in solver_module._drawn_triangles(plan):
                if not (a in P and b in P and c in P):
                    continue
                area = 0.5 * abs((P[b] - P[a])[0] * (P[c] - P[a])[1]
                                 - (P[b] - P[a])[1] * (P[c] - P[a])[0])
                if area < area_frac * span * span:
                    return f"треугольник {a}{b}{c} схлопнулся в отрезок"
        except Exception:  # noqa: BLE001 — проверка никогда не ломает решатель
            return ""
        return ""

    degenerate_figure._degenerate_policy = True
    degenerate_figure._original = orig
    degenerate_figure.__doc__ = getattr(orig, "__doc__", None)
    degenerate_figure.__name__ = "degenerate_figure"
    solver_module.degenerate_figure = degenerate_figure
    return True


def _wrap_semantic_failures(orig):
    import functools

    def semantic_failures(text, plan, coords, *args, **kwargs):
        fails = orig(text, plan, coords, *args, **kwargs)
        try:
            extra = named_figure_failures(text, plan, coords)
        except Exception:  # noqa: BLE001
            extra = []
        return list(fails) + extra if extra else fails
    functools.wraps(orig)(semantic_failures)
    semantic_failures._degenerate_policy = True
    semantic_failures._original = orig
    return semantic_failures


def install(solver_module, semantics_module=None, pipeline_module=None) -> bool:
    """Обернуть проверки вырожденности решателя и семантики. Повторный вызов — no-op."""
    if not ENABLED:
        return False
    done = _wrap_drawn_triangles(solver_module)
    if _wrap_degenerate_figure(solver_module):
        done = True
    if semantics_module is not None:
        orig = getattr(semantics_module, "semantic_failures", None)
        if orig is not None and not getattr(orig, "_degenerate_policy", False):
            semantics_module.semantic_failures = _wrap_semantic_failures(orig)
            done = True
    if pipeline_module is None:
        try:
            from . import pipeline as pipeline_module  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            pipeline_module = None
    ver = getattr(pipeline_module, "ENGINE_VERSION", None) if pipeline_module else None
    if isinstance(ver, str) and "+dgp" not in ver:
        pipeline_module.ENGINE_VERSION = ver + CACHE_SUFFIX
        done = True
    return done
