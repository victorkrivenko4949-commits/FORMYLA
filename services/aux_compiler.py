# -*- coding: utf-8 -*-
"""services/aux_compiler.py — детерминированный компилятор шагов в aux-план.

CH23 PART B2.  Преобразует список шагов извлечения (action + args) в
aux-план движка, не вызывая LLM.  Полностью детерминирован.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# action -> (op движка, параметры-алиасы, создаёт ли точку)
_ACTION_OP = {
    "draw_segment": ("segment", ("p1", "p2"), False),
    "draw_line": ("line", ("p1", "p2"), False),
    "draw_ray": ("ray", ("p1", "p2"), False),
    "extend_side": ("line_extension", ("origin", "direction"), False),
    "draw_altitude": ("altitude", ("vertex", "side_a", "side_b"), True),
    "draw_median": ("median", ("vertex", "side_a", "side_b"), True),
    "draw_bisector": ("angle_bisector", ("vertex", "side_a", "side_b"), True),
    "draw_perpendicular": ("perpendicular_bisector", ("p1", "p2"), False),
    "draw_parallel": ("parallel_line", ("point", "line"), False),
    "draw_circle_center_radius": ("circle_center_radius", ("center", "radius_point"), False),
    "draw_circle_through_points": ("circle_three_points", ("p1", "p2", "p3"), False),
    "circumscribe_triangle": ("circumcircle", ("p1", "p2", "p3"), False),
    "inscribe_circle": ("incircle", ("p1", "p2", "p3"), False),
    "mark_intersection": ("intersect_lines", ("line1", "line2"), True),
    "mark_midpoint": ("midpoint", ("p1", "p2"), True),
    "mark_point_on_segment": ("point_on_segment", ("p1", "p2"), True),
    "mark_right_angle": ("right_angle_mark", ("vertex", "ray1", "ray2"), False),
    "mark_equal_segments": ("equal_segments_mark", ("segments",), False),
    "mark_angle": ("angle_label", ("vertex", "ray1", "ray2"), False),
    # CH27: центральная симметрия и поворот.
    "reflect_point": ("reflect_point", ("point", "center"), True),
    "rotate_point": ("rotate_point", ("point", "center"), True),
}

# op -> visual_role (CH16)
_VISUAL_ROLE = {
    "segment": "aux",
    "line": "aux",
    "ray": "aux",
    "line_extension": "aux",
    "altitude": "aux",
    "median": "aux",
    "angle_bisector": "aux",
    "perpendicular_bisector": "aux",
    "parallel_line": "aux",
    "circle_center_radius": "reference_circle",
    "circle_three_points": "reference_circle",
    "circumcircle": "reference_circle",
    "incircle": "target_circle",
    "intersect_lines": "key_point",
    "midpoint": "key_point",
    "point_on_segment": "key_point",
    "reflect_point": "key_point",
    "rotate_point": "key_point",
    "right_angle_mark": "right_angle_mark",
    "equal_segments_mark": "given_mark",
    "angle_label": "given_mark",
}

# op -> требуется dashed (геометрия), marks — нет.
_GEOMETRY_OPS = {
    "segment", "line", "ray", "line_extension", "altitude", "median",
    "angle_bisector", "perpendicular_bisector", "parallel_line",
    "circle_center_radius", "circle_three_points", "circumcircle", "incircle",
}

_PURPOSE = {
    "segment": "Построен отрезок из решения",
    "line": "Построена прямая из решения",
    "ray": "Построен луч из решения",
    "line_extension": "Продление стороны",
    "altitude": "Высота из решения",
    "median": "Медиана из решения",
    "angle_bisector": "Биссектриса из решения",
    "perpendicular_bisector": "Перпендикуляр из решения",
    "parallel_line": "Прямая, параллельная данной",
    "circle_center_radius": "Окружность из решения",
    "circle_three_points": "Окружность через три точки",
    "circumcircle": "Описанная окружность",
    "incircle": "Вписанная окружность",
    "intersect_lines": "Точка пересечения",
    "midpoint": "Середина отрезка",
    "point_on_segment": "Точка на отрезке",
    "reflect_point": "Точка, симметричная относительно центра",
    "rotate_point": "Точка после поворота",
    "right_angle_mark": "Отметка прямого угла",
    "equal_segments_mark": "Отметка равных отрезков",
    "angle_label": "Подпись угла",
}


def _base_ids(base_plan: Dict) -> set:
    """Все id, доступные из base-плана: обычные id + foot_id (высоты/медианы/
    биссектрисы создают точку без отдельного id)."""
    cs = base_plan.get("constructions", []) if isinstance(base_plan, dict) else []
    ids = set()
    for c in cs:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if cid:
            ids.add(cid)
        # Операции, создающие точку-результат.
        if c.get("type") in ("altitude", "median", "angle_bisector"):
            foot = c.get("foot_id")
            if foot:
                ids.add(foot)
    return ids


# Поля-идентификаторы точек/линий/окружностей, на которые ссылается построение.
# Всё остальное (direction, beyond, label, side, degrees, maps, text, purpose,
# quote, ...) — НЕ ссылки и не должно попадать в проверку UNRESOLVED_POINT.
_REFERENCE_KEYS = {
    "p1", "p2", "p3", "p4", "point", "center", "origin", "line1", "line2",
    "circle", "circle1", "circle2", "vertex", "side_a", "side_b", "ray1",
    "ray2", "through", "radius_point", "foot_id", "line", "away_from",
    "length_from",
}


def _refs_of(construction: Dict) -> set:
    """Собрать id-ссылки конструкции (только реальные опорные поля + segments)."""
    refs = set()
    for k, v in construction.items():
        if k == "segments":
            for item in v if isinstance(v, list) else []:
                if isinstance(item, str):
                    refs.add(item)
                elif isinstance(item, (list, tuple)):
                    for x in item:
                        if isinstance(x, str):
                            refs.add(x)
        elif k in _REFERENCE_KEYS:
            if isinstance(v, str):
                refs.add(v)
            elif isinstance(v, (list, tuple)):
                for x in v:
                    if isinstance(x, str):
                        refs.add(x)
    return refs


def _line_id_for_points(pair, base_plan, constructions) -> Optional[str]:
    """Найти существующий id отрезка/прямой с родителями {p1, p2}.

    Ищет в base и в уже собранных aux-конструкциях.  Если не найден — None.
    """
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        return None
    s = {pair[0], pair[1]}
    for c in _base_constructions_list(base_plan) + constructions:
        if c.get("type") in ("segment", "line", "ray"):
            parents = [c.get("p1"), c.get("p2")]
            if set(parents) == s:
                return c.get("id")
    return None


def _base_constructions_list(base_plan: Dict) -> List[Dict]:
    cs = base_plan.get("constructions", []) if isinstance(base_plan, dict) else []
    return [c for c in cs if isinstance(c, dict)]


def _base_construction_by_id(base_plan: Dict, cid: str) -> Optional[Dict]:
    """Найти construction в base-плане по id (или None)."""
    if not cid:
        return None
    for c in _base_constructions_list(base_plan):
        if c.get("id") == cid:
            return c
    return None


def _given_equal_pairs(base_plan: Dict) -> set:
    """Множество frozenset({P,Q}) равных пар из УСЛОВИЯ (данное).

    Источники: midpoint_mark / equal_segments в given_marks, midpoint /
    equal_segments / segment_length в constructions. Используется, чтобы не
    пере-отмечать solver'ом равенства, уже заданные в условии.
    """
    pairs: set = set()
    if not isinstance(base_plan, dict):
        return pairs

    def _add(a, b):
        if isinstance(a, str) and isinstance(b, str) and a and b:
            pairs.add(frozenset((a, b)))

    # given_marks: midpoint_mark (p1,p2,p3,p4) и equal_segments (pairs).
    for gm in (base_plan.get("given_marks") or []):
        if not isinstance(gm, dict):
            continue
        gt = gm.get("type", "")
        if gt == "midpoint_mark":
            _add(gm.get("p1"), gm.get("p2"))
            _add(gm.get("p3"), gm.get("p4"))
            _add(gm.get("p1"), gm.get("p3"))
            _add(gm.get("p2"), gm.get("p4"))
        elif gt == "equal_segments":
            for pr in (gm.get("pairs") or []):
                if isinstance(pr, (list, tuple)) and len(pr) >= 2:
                    _add(pr[0], pr[1])

    # constructions: midpoint (p1,p2 → p1-M=M-p2), equal_segments, segment_length.
    for c in _base_constructions_list(base_plan):
        ct = c.get("type", "")
        if ct == "midpoint":
            m = c.get("id", "")
            _add(c.get("p1"), m)
            _add(c.get("p2"), m)
        elif ct == "equal_segments":
            for pr in (c.get("pairs") or []):
                if isinstance(pr, (list, tuple)) and len(pr) >= 2:
                    _add(pr[0], pr[1])
        elif ct == "midpoint_mark":
            _add(c.get("p1"), c.get("p2"))
            _add(c.get("p3"), c.get("p4"))
    return pairs


def compile_steps_to_aux(steps: List[Dict], base_plan: Dict) -> Tuple[Dict, List[str]]:
    """Скомпилировать steps в aux_plan.

    Возвращает (aux_plan, issues).  issues — список строк-кодов, например
    UNRESOLVED_POINT / UNKNOWN_ACTION / DUPLICATE_IN_BASE / UNKNOWN_STEP_ID.

    CH27: ведёт реестр step_id -> id объекта движка (для mark_intersection),
    поддерживает reflect_point / rotate_point и поле unsupported.
    """
    issues: List[str] = []
    constructions: List[Dict] = []

    base_ids = _base_ids(base_plan)
    created: set = set(base_ids)
    registry: Dict[str, str] = {}

    if not steps:
        return {"has_aux": False, "reason": "решение не содержит построений"}, []

    for step in steps:
        if not isinstance(step, dict):
            continue
        action = step.get("action")
        if action not in _ACTION_OP:
            issues.append(f"UNKNOWN_ACTION:{action}")
            continue

        op, aliases, creates_point = _ACTION_OP[action]
        args = step.get("args") or {}

        # CH29: нормализация синонимов аргументов из prebuilt-партии.
        #   a/b -> p1/p2 (draw_segment, draw_line, mark_midpoint, ...)
        #   from/to -> origin/direction (extend_side)
        #   point -> p1 (draw_perpendicular), line:[X,Y] -> p2 = X (первая точка)
        _nargs = dict(args)
        if "a" in _nargs and "p1" not in _nargs:
            _nargs["p1"] = _nargs["a"]
        if "b" in _nargs and "p2" not in _nargs:
            _nargs["p2"] = _nargs["b"]
        if "from" in _nargs and "origin" not in _nargs:
            _nargs["origin"] = _nargs["from"]
        if "to" in _nargs and "direction" not in _nargs:
            _nargs["direction"] = _nargs["to"]
        if "point" in _nargs and "p1" not in _nargs:
            _nargs["p1"] = _nargs["point"]
        if "line" in _nargs and isinstance(_nargs.get("line"), (list, tuple)) \
                and "p2" not in _nargs:
            _nargs["p2"] = _nargs["line"][0]
        args = _nargs

        c = {"type": op}
        for a in aliases:
            if a in args:
                c[a] = args[a]

        # rotate_point: degrees / maps.
        if op == "rotate_point":
            if "degrees" in args:
                c["degrees"] = args["degrees"]
            if "maps" in args:
                c["maps"] = args["maps"]

        # creates_point / foot_id
        cp = step.get("creates_point")
        if creates_point:
            if cp:
                if op == "altitude":
                    c["foot_id"] = cp
                else:
                    c["id"] = cp
                created.add(cp)
            elif op in ("altitude", "median", "angle_bisector"):
                issues.append("MISSING_FOOT_ID")
        elif cp:
            # action не создаёт точку, но creates_point задан — игнор.
            pass

        # стабильный id
        if "id" not in c:
            c["id"] = "aux_" + op + "_" + "_".join(str(args.get(a, "")) for a in aliases)

        # mark_intersection: разрешить operand'ы (obj1/obj2 или line1/line2).
        if op == "intersect_lines":
            resolved = {}
            for out_key, in_keys in (("line1", ("line1", "obj1")),
                                     ("line2", ("line2", "obj2"))):
                operand = None
                for k in in_keys:
                    if k in args:
                        operand = args[k]
                        break
                if operand is None:
                    continue
                if isinstance(operand, str):
                    if operand in registry:
                        resolved[out_key] = registry[operand]
                    elif operand in created:
                        resolved[out_key] = operand
                    else:
                        issues.append(f"UNKNOWN_STEP_ID:{operand}")
                elif isinstance(operand, (list, tuple)):
                    lid = _line_id_for_points(operand, base_plan, constructions)
                    if lid is None:
                        # Точки без существующей линии — создать промежуточную.
                        lid = "aux_line_" + "_".join(str(x) for x in operand)
                        line_c = {
                            "type": "line", "id": lid,
                            "p1": operand[0], "p2": operand[1],
                            "style": "aux", "dashed": True,
                            "visual_role": "aux",
                            "purpose": "Вспомогательная прямая из решения",
                            "solution_evidence": {
                                "step_no": step.get("step_no"),
                                "quote": (step.get("quote") or "").strip(),
                            },
                        }
                        constructions.append(line_c)
                        created.add(lid)
                    resolved[out_key] = lid
            c["line1"] = resolved.get("line1", "")
            c["line2"] = resolved.get("line2", "")

        # дубликат в base (по id)
        if c["id"] in base_ids:
            issues.append(f"DUPLICATE_IN_BASE:{c['id']}")
            continue

        # дубликат среди уже созданных aux
        existing_ids = {x.get("id") for x in constructions}
        if c["id"] in existing_ids:
            continue  # пропустить дубликат

        # проверка ссылок
        unresolved = [r for r in _refs_of(c)
                      if r and r not in created and r != c.get("foot_id") and r != c.get("id")]
        if unresolved:
            for r in unresolved:
                issues.append(f"UNRESOLVED_POINT:{r}")
            continue

        # auto style/dashed/visual_role/purpose/evidence
        c["style"] = "aux"
        c["dashed"] = True if op in _GEOMETRY_OPS else False
        c["visual_role"] = _VISUAL_ROLE.get(op, "aux")
        c["purpose"] = _PURPOSE.get(op, "Построение из решения")
        c["solution_evidence"] = {
            "step_no": step.get("step_no"),
            "quote": (step.get("quote") or "").strip(),
        }

        constructions.append(c)
        # CH27: id построенного объекта (точки или линии) становится доступным
        # для ссылок из последующих шагов (line1/line2 у intersect_lines).
        created.add(c["id"])

        # CH27: реестр step_id -> id объекта движка.
        step_id = step.get("id")
        if step_id:
            registry[str(step_id)] = c["id"]

    has_aux = len(constructions) > 0
    reason = "" if has_aux else "решение не содержит построений"
    return {"has_aux": has_aux, "reason": reason, "constructions": constructions}, issues


# ──────────────────────────────────────────────────────────────────────────
# CH-aux: компиляция solver-построений (закрытый словарь op + строгая цитата)
# ──────────────────────────────────────────────────────────────────────────

from services.aux_ops import AUX_ALLOWED_OPS, engine_op_for, creates_point  # noqa: E402

_CONSTRUCTION_ACTION_STEMS = ("провед", "соедин", "продл", "постро", "опуст", "отмет")


def _norm(s: str) -> str:
    """Нормализовать строку: пробелы -> один, регистр вниз."""
    return " ".join((s or "").split()).lower()


def _tokenize(s: str) -> set:
    """Токены строки (буквы/цифры) для мягкого сопоставления цитат."""
    return set(re.findall(r"[a-zа-яё0-9]+", _norm(s)))


def validate_quote(quote: str, steps: List[dict]) -> Tuple[bool, str]:
    """CH-aux: проверка цитаты (строгая, затем мягкая по токенам).

    1. quote должна быть ПОДСТРОКОЙ одного из steps[].text (после нормализации);
    2. иначе — мягкая проверка: все значимые токены цитаты должны
       присутствовать в одном из шагов решения.

    Стем действия построения НЕ обязателен: модели часто пишут «биссектрису
    угла B», «точку пересечения обозначим O» без глагола «проведём/построим».

    Возвращает (ok, error_code).
    """
    q = (quote or "").strip()
    if not q:
        return False, "EMPTY_QUOTE"
    # CH-fidelity FIX: если steps пусты (модель вернула aux_constructions без
    # пронумерованных steps — встречается при aux_needed=false), не отбрасываем
    # построение: цитата есть, а сверять её не с чем.
    if not steps:
        return True, ""
    q_norm = _norm(q)
    for step in steps:
        text = step.get("text", "")
        if q_norm in _norm(text):
            return True, ""

    # CH-fidelity FIX: цитаты с лишней пунктуацией/пробелами не должны ронять
    # всё построение.  Мягкая проверка — пересечение значимых токенов.
    q_tokens = _tokenize(q)
    if len(q_tokens) >= 2:
        for step in steps or []:
            if q_tokens <= _tokenize(step.get("text", "")):
                return True, ""
    return False, "QUOTE_NOT_IN_SOLUTION"


def _intersection_id_from_quote(ac: Dict) -> str:
    """CH-fidelity: имя точки-РЕЗУЛЬТАТА пересечения из quote.

    Для line_intersection фраза обычно «...до пересечения с AB в точке E».
    Обычный _new_point_id_from_quote цепляет ПЕРВОЕ вхождение «точку M»
    (точку, ЧЕРЕЗ которую проведена параллель), а не результат.  Здесь
    приоритет у «в точке X» / «точкой X» / «обозначим X», затем fallback.
    """
    q = (ac.get("quote") or "").strip()
    if not q:
        return ""
    m = re.search(r"в\s+точк(?:у|е|ой)\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9_]*)", q)
    if m:
        return m.group(1)
    m = re.search(r"точк(?:ой|е)\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9_]*)", q)
    if m:
        return m.group(1)
    m = re.search(r"(?:обозначим|назов[ёе]м)\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9_]*)", q)
    if m:
        return m.group(1)
    return _new_point_id_from_quote(ac)


def _new_point_id_from_quote(ac: Dict) -> str:
    """CH-fidelity: вытащить имя новой точки из quote, когда solver не дал id.

    DeepSeek часто пишет «отметим точку D на луче BA за A» и кладёт id=null в
    line_extension/point_on_line/…, а затем ссылается на D в следующем
    построении (например segment [D,M]).  Без id точке присваивается
    синтетическое aux_*_N, и следующий шаг падает с UNRESOLVED_POINT:D,
    из-за чего часть построений теряется (fidelity < 1).  Достаём имя из
    текста шага, чтобы следующая ссылка резолвилась.
    """
    q = (ac.get("quote") or "").strip()
    if not q:
        return ""
    # «точку D», «точка D», «точке E», «точки D и M» — первое имя после
    # форм слова «точка».
    m = re.search(r"точк(?:у|а|и|е|ой|ами)\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9_]*)", q)
    if m:
        return m.group(1)
    # «основание K», «основанием K» — точка-основание перпендикуляра.
    m = re.search(r"основани(?:е|ем|я)\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9_]*)", q)
    if m:
        return m.group(1)
    # «обозначим D», «назовём D», «через D», «пересечение обозначим O».
    m = re.search(r"(?:обозначим|назов[ёе]м|через)\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9_]*)", q)
    if m:
        return m.group(1)
    return ""


def _last_point_id_from_quote(ac: Dict) -> str:
    """E5 FIX: имя НОВОЙ точки из quote — ПОСЛЕДНЕЕ упоминание.

    Для line_extension фраза «продлим BA за A до точки D» содержит ДВА имени
    после слова «точка»: сначала «точку A» (точку, за которую продлеваем),
    затем «точки D» (результат).  _new_point_id_from_quote берёт ПЕРВОЕ
    (A) — и id становится A → DUPLICATE_IN_BASE:A, построение теряется.
    Результат построения всегда упоминается в КОНЦЕ фразы, поэтому берём
    последнее совпадение.
    """
    q = (ac.get("quote") or "").strip()
    if not q:
        return ""
    names = re.findall(r"(?:точк(?:у|а|и|е|ой|ами)|основани(?:е|ем|я))\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9_]*)", q)
    if names:
        return names[-1]
    m = re.search(r"до\s+точк(?:и|а|у)\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9_]*)", q)
    if m:
        return m.group(1)
    m = re.findall(r"(?:обозначим|назов[ёе]м)\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9_]*)", q)
    if m:
        return m[-1]
    return ""


def _foot_id_from_quote(ac: Dict, vertex: str) -> str:
    """CH-fidelity: имя ОСНОВАНИЯ перпендикуляра из quote (не вершина).

    Для perpendicular_through quote обычно «...из точки M на прямую AB,
    обозначим основание K».  Обычный _new_point_id_from_quote цепляет «точки M»
    (вершину), поэтому здесь приоритет у «основание X», затем «обозначим X /
    назовём X», но X не должен совпадать с вершиной.
    """
    q = (ac.get("quote") or "").strip()
    if not q:
        return ""
    m = re.search(r"основани(?:е|ем|я)\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9_]*)", q)
    if m:
        return m.group(1)
    for m in re.finditer(r"(?:обозначим|назов[ёе]м)\s+([A-Za-zА-ЯЁ][A-Za-zА-ЯЁ0-9_]*)", q):
        name = m.group(1)
        if name != vertex:
            return name
    return ""


def _triangle_vertices(base_plan: Dict) -> List[str]:
    """Первые free_point из base_plan (вершины треугольника)."""
    cs = (base_plan or {}).get("constructions", []) if isinstance(base_plan, dict) else []
    return [c.get("id") for c in cs
            if isinstance(c, dict) and c.get("type") == "free_point" and c.get("id")]


def _side_id(base_plan: Dict, x: str, y: str) -> str:
    """id отрезка/прямой с родителями {x, y} в base_plan (или f'{x}{y}')."""
    cs = (base_plan or {}).get("constructions", []) if isinstance(base_plan, dict) else []
    for c in cs:
        if isinstance(c, dict) and c.get("type") in ("segment", "line"):
            if {c.get("p1"), c.get("p2")} == {x, y}:
                return c.get("id")
    return f"{x}{y}"


def _llm_incircle_aux(aux_cs: List[dict], A: str, B: str, C: str):
    """Извлечь из solver-aux имена инцентра и точек касания и индексы
    «съеденных» инкруг-операций (биссектрисы, перпендикуляры из инцентра,
    точки касания, радиусы, окружность), чтобы основной цикл не компилировал
    их повторно (иначе самоссылающиеся line_intersection вида [O, D] падают).
    Возвращает (incenter_name, touch_names, consumed_idx).
    """
    sides = [frozenset([B, C]), frozenset([C, A]), frozenset([A, B])]
    # Инцентр — точка, из которой опускают перпендикуляры на стороны.
    # Вычисляем ПЕРВЫМ, чтобы фильтр точек касания мог отличить touch-def
    # (line1 содержит инцентр: [O, D]) от «параллель через D до AB в точке E»
    # (line1 = [D, E], инцентра НЕ содержит).
    incenter_name = None
    for ac in aux_cs:
        if ac.get("op") != "perpendicular_through":
            continue
        tl = [x for x in (ac.get("to_line") or []) if isinstance(x, str)]
        if len(tl) == 2 and frozenset(tl) in sides:
            incenter_name = ac.get("from_point") or ac.get("point")
            if incenter_name:
                break
    touch_names: Dict[frozenset, str] = {}
    for ac in aux_cs:
        if ac.get("op") != "line_intersection":
            continue
        l1 = [x for x in (ac.get("line1") or []) if isinstance(x, str)]
        l2 = [x for x in (ac.get("line2") or []) if isinstance(x, str)]
        refs_inc = bool(incenter_name) and (incenter_name in l1 or incenter_name in l2)
        if not refs_inc:
            continue  # не touch-def (напр. пересечение параллели с AB)
        if len(l2) == 2 and frozenset(l2) in sides:
            touch_names[frozenset(l2)] = ac.get("id")
        elif len(l1) == 2 and frozenset(l1) in sides:
            touch_names[frozenset(l1)] = ac.get("id")
    consumed = set()
    for i, ac in enumerate(aux_cs):
        op = ac.get("op", "")
        if op == "angle_bisector":
            consumed.add(i); continue
        if op == "circle_center_radius" and ac.get("center") == incenter_name:
            consumed.add(i); continue
        if op == "segment":
            pts = [x for x in (ac.get("points") or []) if isinstance(x, str)]
            if incenter_name and incenter_name in pts:
                consumed.add(i); continue
        if op == "line_intersection":
            if incenter_name and ac.get("id") == incenter_name:
                consumed.add(i); continue
            l1 = [x for x in (ac.get("line1") or []) if isinstance(x, str)]
            l2 = [x for x in (ac.get("line2") or []) if isinstance(x, str)]
            side_hit = (len(l2) == 2 and frozenset(l2) in sides) or \
                       (len(l1) == 2 and frozenset(l1) in sides)
            refs_inc = bool(incenter_name) and (incenter_name in l1 or incenter_name in l2)
            # E7: точка касания определяется line_intersection, где line2 — сторона,
            # а line1 содержит инцентр (часто самоссылаясь: [O, D]).  Отличаем от
            # «параллель через D до пересечения с AB в точке E»: там line1 = [D, E]
            # инцентра НЕ содержит → не съедаем.
            if side_hit and refs_inc:
                consumed.add(i); continue
        if op == "perpendicular_through":
            tl = [x for x in (ac.get("to_line") or []) if isinstance(x, str)]
            fp = ac.get("from_point") or ac.get("point")
            if incenter_name and fp == incenter_name and len(tl) == 2 \
                    and frozenset(tl) in sides:
                consumed.add(i); continue
    return incenter_name, touch_names, consumed


def _recognize_incircle(aux_cs: List[dict], base_plan: Dict) -> Optional[Tuple[List[dict], set, set]]:
    """Распознать построение вписанной окружности и вернуть нативный план.

    GPT описывает инцентр как цепочку «биссектрисы -> пересечение O ->
    перпендикуляры -> окружность», но не даёт стабильных id линий/точек.
    Движок умеет incenter / altitude / line / circle_center_radius нативно,
    поэтому собираем корректную цепочку, сохраняя на чертеже и биссектрисы,
    и перпендикуляры, и саму окружность.
    """
    # CH-aux FIX: находим типы уже построенных объектов в base-плане, чтобы
    # понять, что нужно ДОстроить (не дублируя уже существующее).
    base_types = {
        c.get("type")
        for c in ((base_plan or {}).get("constructions", []) if isinstance(base_plan, dict) else [])
        if isinstance(c, dict)
    }
    base_has_incircle = "incircle" in base_types
    base_has_incenter = "incenter" in base_types
    base_has_touch = "incircle_touch" in base_types
    # Если base уже построил И окружность, И инцентр, И точки касания —
    # дополнять нечего (кроме биссектрис, которые тоже уже могут быть).
    # Не отключаемся полностью: достроим недостающие биссектрисы и радиусы,
    # но не станем дублировать окружность/точки/инцентр.

    ops = [a.get("op") for a in aux_cs]
    if ops.count("angle_bisector") < 2:
        return None
    if not any(o in ops for o in ("circle_center_radius", "incircle", "circle_three_points")):
        return None

    tri = _triangle_vertices(base_plan)
    if len(tri) < 3:
        return None
    A, B, C = tri[0], tri[1], tri[2]

    base_ids = _base_ids(base_plan)
    constructions: List[dict] = []
    created_ids: set = set()

    # E7 FIX: имя инцентра и точек касания, заданное solver'ом.  Раньше ранний
    # return отбрасывал ВСЕ прочие построения, а точки касания становились
    # безымянными aux_touch_* — поэтому последующие ссылки на «D» (напр.
    # parallel_through из D) падали с UNRESOLVED_POINT:D.  Теперь используем
    # имена solver'а как id движка и возвращаем индексы «съеденных» операций,
    # чтобы основной цикл продолжил компилировать остальное.
    incenter_name, touch_names, consumed_idx = _llm_incircle_aux(aux_cs, A, B, C)

    # 1) Инцентр O.  Если base уже содержит инцентр — переиспользуем его id;
    # иначе создаём нативно под именем solver'а (если оно не коллидирует с base).
    if base_has_incenter:
        incenter_id = next(
            (c.get("id") for c in (base_plan or {}).get("constructions", [])
             if isinstance(c, dict) and c.get("type") == "incenter" and c.get("id")),
            "aux_O",
        )
        created_ids.add(incenter_id)
    else:
        incenter_id = (incenter_name
                        if (incenter_name and incenter_name not in base_ids)
                        else "aux_O")
        constructions.append({
            "type": "incenter", "id": incenter_id, "p1": A, "p2": B, "p3": C,
            "label": incenter_name or "O", "style": "aux", "dashed": False,
            "visual_role": "key_point", "purpose": "Центр вписанной окружности",
        })
        created_ids.add(incenter_id)

    # 2) Биссектрисы: отрезки вершина -> O (O лежит на каждой биссектрисе).
    for v in (A, B, C):
        constructions.append({
            "type": "line", "id": f"aux_bis_{v}", "p1": v, "p2": incenter_id,
            "style": "aux", "dashed": True, "visual_role": "aux",
            "purpose": f"Биссектриса угла {v}",
        })

    # 3) Точки касания.  Если base-план уже объявил точку касания на этой
    # стороне (A1/A_1, B1/B_1, C1/C_1) — переиспользуем её; иначе вычисляем
    # нативным incircle_touch под уникальным именем aux_touch_*.
    touch_defs = [
        ("BC", A, B, C, ("A1", "A_1"), "aux_touch_A"),   # сторона BC, напротив A
        ("CA", B, C, A, ("B1", "B_1"), "aux_touch_B"),   # CA, напротив B
        ("AB", C, A, B, ("C1", "C_1"), "aux_touch_C"),   # AB, напротив C
    ]
    first_touch = None
    for side_label, opp, s1, s2, existing_names, fallback_id in touch_defs:
        touch_id = None
        for name in existing_names:
            if name in base_ids:
                # E2 FIX: переиспользовать base-точку касания как radius_point
                # можно ТОЛЬКО если она уже приведена к нативному incircle_touch
                # (normalize_base_plan).  Если base оставил её как point_on_segment
                # с произвольным ratio — окружность/радиус уедут на другую сторону.
                bc = _base_construction_by_id(base_plan, name)
                if bc is not None and bc.get("type") == "incircle_touch":
                    touch_id = name
                break
        # E7: имя точки касания, заданное solver'ом (line_intersection с
        # line2 == сторона).  Используем его как id И подпись — иначе
        # последующие ссылки на эту точку (parallel_through из D) не резолвятся.
        llm_name = touch_names.get(frozenset([s1, s2]))
        if touch_id is None:
            touch_id = llm_name or fallback_id
            label = llm_name or ""
            constructions.append({
                "type": "incircle_touch", "id": touch_id,
                "p1": opp, "p2": s1, "p3": s2,
                "label": label, "side": "auto",
                "style": "aux", "visual_role": "key_point",
                "purpose": f"Точка касания вписанной окружности на стороне {side_label}",
            })
            created_ids.add(touch_id)
        # Радиус из O в точку касания.
        constructions.append({
            "type": "line", "id": f"aux_perp_{touch_id}",
            "p1": incenter_id, "p2": touch_id,
            "style": "aux", "dashed": True, "visual_role": "aux",
            "purpose": f"Радиус в точку касания на стороне {side_label}",
        })
        if first_touch is None:
            first_touch = touch_id

    # 4) Окружность.  Строим только если base ещё не содержит incircle.
    if not base_has_incircle:
        constructions.append({
            "type": "circle_center_radius", "id": "aux_incircle",
            "center": incenter_id, "radius_point": first_touch,
            "style": "aux", "dashed": True, "visual_role": "target_circle",
            "purpose": "Вписанная окружность",
        })

    return constructions, consumed_idx, created_ids


# ── Обязательные поля для каждого движкового типа ─────────────────────────
# CH-aux FIX (жёсткая валидация): GPT часто присылает построение с неполным
# набором опор (например, line_intersection без line1/line2).  Раньше такое
# построение попадало в план и роняло ВЕСЬ aux на ConstructionError в движке.
# Теперь каждое построение проверяется на полноту обязательных полей, и
# неполное отбрасывается отдельно (с кодом MISSING_FIELDS:<type>), не ломая
# остальные.
_REQUIRED_FIELDS = {
    "segment": ("p1", "p2"),
    "line": ("p1", "p2"),
    "ray": ("p1", "p2"),
    "perpendicular_bisector": ("p1", "p2"),
    "midpoint": ("p1", "p2"),
    "line_extension": ("origin",),
    "tangent_at_point": ("circle", "p1"),
    "reflect_point": ("point", "center"),
    "reflect_point_over_line": ("p1", "line1"),
    "rotate_point": ("point", "center"),
    "parallel_line": ("point", "line"),
    "circle_center_radius": ("center",),
    "point_on_ray": ("origin", "away_from"),
}

# Типы с несколькими допустимыми наборами полей: достаточно, чтобы
# сработало хотя бы одно из альтернативных условий.
_ALT_FIELDS = {
    "altitude": (("vertex", "side_a", "side_b"), ("p1", "p2", "p3")),
    "median": (("vertex", "side_a", "side_b"), ("p1", "p2", "p3")),
    "angle_bisector": (("vertex", "side_a", "side_b"), ("p1", "p2", "p3")),
    "intersect_lines": (("line1", "line2"), ("p1", "p2", "p3", "p4")),
}


def _missing_required_fields(engine_type: str, c: dict) -> List[str]:
    """Вернуть список недостающих обязательных полей (пустой, если полно)."""
    if engine_type in _REQUIRED_FIELDS:
        return [f for f in _REQUIRED_FIELDS[engine_type]
                if not c.get(f)]
    alts = _ALT_FIELDS.get(engine_type)
    if alts:
        for group in alts:
            if all(c.get(f) for f in group):
                return []
        return list(alts[0])
    return []


def compile_solver_aux(solver_result: dict, base_plan: dict) -> Tuple[dict, List[str]]:
    """Скомпилировать solver aux_constructions в aux-план движка.

    Возвращает (aux_plan, issues).  Строгая проверка:
      - op из закрытого словаря AUX_ALLOWED_OPS;
      - quote обязана быть подстрокой steps[].text и содержать стем действия.

    Атрибуты style/dashed/visual_role/purpose/evidence проставляет компилятор.
    """
    issues: List[str] = []
    constructions: List[dict] = []

    steps = (solver_result or {}).get("steps", []) or []
    aux_cs = (solver_result or {}).get("aux_constructions", []) or []

    # CH-fidelity: склейка пар «line_extension points:[P1,P2]» + «point_on_line
    # id:D» (без линии) — DeepSeek описывает «продлим BA за A до точки D» двумя
    # записями, где точка D живёт во второй.  Сливаем их в одну reflect_point с
    # id=D, а вторую запись убираем.
    if aux_cs:
        merged = []
        skip_next = False
        for idx, ac in enumerate(aux_cs):
            if skip_next:
                skip_next = False
                continue
            if ac.get("op") == "line_extension" and not ac.get("id"):
                nxt = aux_cs[idx + 1] if idx + 1 < len(aux_cs) else None
                if nxt and nxt.get("op") == "point_on_line" and nxt.get("id") \
                        and not nxt.get("line") and not nxt.get("points"):
                    ac = dict(ac)
                    ac["id"] = nxt.get("id")
                    skip_next = True
            merged.append(ac)
        aux_cs = merged

    if not aux_cs:
        return {"has_aux": False, "reason": "", "constructions": []}, []

    # CH-aux FIX: вписанная окружность.  GPT шлёт цепочку «биссектрисы ->
    # пересечение O -> перпендикуляры -> окружность» без стабильных id линий.
    # Движок умеет incenter/altitude/line/circle_center_radius нативно, поэтому
    # распознаём эту цепочку и собираем корректный план, сохраняя на чертеже и
    # биссектрисы, и перпендикуляры, и саму окружность.
    incircle_plan = _recognize_incircle(aux_cs, base_plan)
    consumed_idx: set = set()
    if incircle_plan is not None:
        # E7 FIX: НЕ возвращаемся сразу.  Раньше ранний return отбрасывал все
        # построения после инкруга (параллель, пересечение E, высота H,
        # продолжение F).  Теперь добавляем нативный инкруг-план в начало,
        # регистрируем созданные им точки (инцентр + точки касания по именам
        # solver'а) в `created` и продолжаем компилировать остальные операции,
        # пропуская «съеденные» инкруг-операции (иначе самоссылающиеся
        # line_intersection вида [O, D] падают с UNRESOLVED_POINT:D).
        incircle_plan, consumed_idx, incircle_created = incircle_plan
        constructions.extend(incircle_plan)
        incircle_created_ids = incircle_created
    else:
        incircle_created_ids = set()

    base_ids = _base_ids(base_plan)
    created: set = set(base_ids) | incircle_created_ids
    # CH-aux FIX (E11): множество неупорядоченных пар концов base-отрезков/линий.
    # Нужно, чтобы solver, пере-диктовавший данное как segment/line/ray aux
    # (напр. «Проведём медиану AM» → segment [A,M], хотя AM уже в base),
    # не дублировался поверх данного пунктиром. См. FULFILLED_BY_BASE ниже.
    base_seg_pairs = set()
    for bc in (base_plan.get("constructions") or []):
        if not isinstance(bc, dict):
            continue
        if bc.get("type") in ("segment", "line", "ray"):
            p1, p2 = bc.get("p1"), bc.get("p2")
            if p1 and p2:
                base_seg_pairs.add(frozenset((p1, p2)))
    # CH-fidelity: реестр созданных параллельных прямых (точка -> id линии),
    # чтобы line_intersection мог резолвить «прямую через M» (описанную как
    # [M, E], где E — ещё не существующая точка-результат пересечения).
    parallel_lines: Dict[str, str] = {}
    # E18: равные пары из УСЛОВИЯ — чтобы не пере-отмечать solver'ом равенства,
    # уже заданные в условии (середины / equal_segments в базе).
    given_equal = _given_equal_pairs(base_plan)

    for i, ac in enumerate(aux_cs):
        if i in consumed_idx:
            continue  # E7: инкруг-операция уже свёрнута в нативный план
        op = ac.get("op", "")
        if op not in AUX_ALLOWED_OPS:
            issues.append(f"UNKNOWN_AUX_OP:{op}")
            continue

        # Строгая цитата.
        quote = ac.get("quote", "")
        ok, code = validate_quote(quote, steps)
        if not ok:
            issues.append(f"{code}:{quote[:30]}")
            continue

        step_no = ac.get("step_no")
        engine_type = engine_op_for(op)
        c: dict = {"type": engine_type}

        # Маппинг аргументов solver-контракта в поля движка.
        if op in ("segment", "line", "ray"):
            pts = ac.get("points") or []
            if len(pts) >= 2:
                c["p1"], c["p2"] = pts[0], pts[1]
            # CH-aux FIX (E11): solver пере-диктовал данное как segment/line/ray
            # aux (напр. «Проведём медиану AM» → segment [A,M]). Если пара концов
            # уже есть в base как данный отрезок — пропускаем как выполненное
            # базой, иначе пунктирная aux-копия ляжет поверх сплошного данного.
            if c.get("p1") and c.get("p2") and frozenset((c["p1"], c["p2"])) in base_seg_pairs:
                issues.append(f"FULFILLED_BY_BASE:{engine_type}:{c['p1']}{c['p2']}")
                continue
        elif op in ("altitude", "median", "angle_bisector"):
            # Универсальная разборка трёх точек: форматы
            #   angle_bisector: [A, B, C]  -> вершина B, стороны A/C
            #   altitude:        [O, A, B] -> вершина O, сторона A-B
            #   median:          [A, B, C] -> вершина A, сторона B-C
            pts = [p for p in (ac.get("points") or []) if isinstance(p, str)]
            v = ac.get("from_point") or ac.get("vertex") or ""
            side = ac.get("to_line") or ac.get("to_side") or ac.get("rays") or []
            side = [s for s in side if isinstance(s, str)]
            if not v and not side and len(pts) >= 3:
                if op == "angle_bisector":
                    # формат [сторона1, вершина, сторона2]
                    v = pts[1]
                    side = [pts[0], pts[2]]
                elif op == "median":
                    v = pts[0]
                    side = [pts[1], pts[2]]
                elif op == "altitude":
                    v = pts[0]
                    side = [pts[1], pts[2]]
            # Для angle_bisector/median отфильтруем саму вершину из side.
            if op != "altitude":
                side = [s for s in side if s != v]
            if v and len(side) >= 2:
                c["vertex"] = v
                c["side_a"], c["side_b"] = side[0], side[1]
            foot = (ac.get("foot_id") or ac.get("id", "")
                    or _foot_id_from_quote(ac, v)
                    or _new_point_id_from_quote(ac))
            # E3b FIX: имя основания не должно совпадать с вершиной — иначе
            # следующая ссылка на основание (напр. segment [K,A]) резолвится
            # в вершину и построение теряется.
            if foot == v:
                foot = ""
            if foot:
                c["foot_id"] = foot
                created.add(foot)
        elif op == "perpendicular_bisector":
            seg = ac.get("segment") or []
            if len(seg) >= 2:
                c["p1"], c["p2"] = seg[0], seg[1]
        elif op == "midpoint":
            seg = ac.get("segment") or ac.get("points") or []
            mid_id = ac.get("id", "")
            if len(seg) >= 2:
                c["p1"], c["p2"] = seg[0], seg[1]
                c["id"] = mid_id or f"aux_mid_{seg[0]}{seg[1]}"
                created.add(c["id"])
        elif op == "point_on_line":
            # «точка D на луче/прямой через [A, B]» → point_on_segment.
            # Контракт обычно: point:D, line:[A,B] ИЛИ points:[...] + id:D.
            # E3a FIX: если solver не дал id (DeepSeek пишет «точку D» в quote),
            # достаём имя из quote, иначе следующая ссылка на D падает с
            # UNRESOLVED_POINT:D.
            pid = ac.get("id") or ac.get("point") or _new_point_id_from_quote(ac)
            line = [x for x in (ac.get("line") or ac.get("to_line") or []) if isinstance(x, str)]
            pts = [x for x in (ac.get("points") or []) if isinstance(x, str)]
            if len(line) < 2 and len(pts) >= 2:
                line = pts[:2]
            if len(line) >= 2:
                c["p1"], c["p2"] = line[0], line[1]
                if pid:
                    c["id"] = pid
                    created.add(pid)
            else:
                issues.append("POINT_ON_LINE_NO_LINE")
                continue
        elif op == "parallel_through":
            # E4: solver пишет и from_point, и point, и просто первый элемент
            # points — поддерживаем все три.
            c["point"] = ac.get("point", "") or ac.get("from_point", "")
            line = [x for x in (ac.get("to_line") or []) if isinstance(x, str)]
            pts = [x for x in (ac.get("points") or []) if isinstance(x, str)]
            if not c["point"] and pts:
                c["point"] = pts[0]
            if len(line) < 2 and len(pts) >= 3:
                # points:[M, C, H] — точка M, прямая C-H.
                c["point"] = c["point"] or pts[0]
                line = pts[1:3]
            if len(line) >= 2:
                c["line"] = line
            else:
                issues.append("PARALLEL_NO_LINE")
                continue
        elif op == "perpendicular_through":
            # «перпендикуляр из точки P на прямую [A,B]» = высота из P на AB.
            # Движковый тип altitude требует vertex/side_a/side_b (+ foot_id).
            v = ac.get("point", "")
            line = [x for x in (ac.get("to_line") or []) if isinstance(x, str)]
            pts = [p for p in (ac.get("points") or []) if isinstance(p, str)]
            if not v and pts:
                v = pts[0]
            if len(line) < 2 and len(pts) >= 3:
                # формат points:[P, A, B] -> перпендикуляр из P на сторону A-B
                v = v or pts[0]
                line = [pts[1], pts[2]]
            if v and len(line) >= 2:
                c["vertex"] = v
                c["side_a"], c["side_b"] = line[0], line[1]
                foot = (ac.get("foot_id") or ac.get("id", "")
                        or _foot_id_from_quote(ac, v)
                        or f"aux_foot_{v}_{line[0]}{line[1]}")
                c["foot_id"] = foot
                created.add(foot)
            else:
                issues.append("PERPENDICULAR_NO_LINE")
                continue
        elif op == "line_extension":
            # Контракт: segment:[P1,P2], beyond:P2, id:NEW — «продлим P1P2 за P2
            # до точки NEW так, что P2 — середина P1-NEW».  Это центральная
            # симметрия P1 относительно P2 (NEW = 2*P2 - P1), т.е. reflect_point.
            # CH-fidelity: fallback на points:[P1,P2], если segment не задан.
            seg = [x for x in (ac.get("segment") or ac.get("points") or []) if isinstance(x, str)]
            beyond = ac.get("beyond", "")
            quote = ac.get("quote", "")
            # «продлим BA за A до точки D так, что AD = AM» — это НЕ центральная
            # симметрия (там AD = AB), а точка на луче за A на расстоянии |AM|.
            # Распознаём паттерн «<XY> = <ZW>» в цитате и строим point_on_ray.
            len_m = re.search(r"\b([A-Za-zА-ЯЁ])([A-Za-zА-ЯЁ])\s*=\s*([A-Za-zА-ЯЁ])([A-Za-zА-ЯЁ])\b", quote)
            # E5 FIX: id новой точки.  При равенстве «AD = AM» новая точка — D
            # (вторая буква ЛЕВОЙ части).  Старый _new_point_id_from_quote цеплял
            # ПЕРВОЕ «точку A» (точку, за которую продлеваем), id становился A —
            # потом DUPLICATE_IN_BASE:A.  Без равенства берём последнее упоминание
            # «точки/до точки X» (результат всегда в конце фразы).
            if len_m:
                ext_id = ac.get("id") or len_m.group(2)
            else:
                ext_id = ac.get("id") or _last_point_id_from_quote(ac)
            # E5 FIX: пара для length_from.  Берём из равенства в цитате
            # («AD = AM» -> [A, M]) ИЛИ из поля length_from, которое solver
            # передаёт явно, когда выражает равенство словами («равный ED»,
            # без знака «=»).  Без этого branch point_on_ray не срабатывает и
            # построение ошибочно падает в центральную симметрию (F = 2·E − A),
            # где EF = AE, а не EF = ED.
            lf_field = ac.get("length_from")
            if len_m:
                lf_pair = [len_m.group(3), len_m.group(4)]
            elif isinstance(lf_field, (list, tuple)) and len(lf_field) >= 2:
                lf_pair = [lf_field[0], lf_field[1]]
            else:
                lf_pair = None
            if len(seg) >= 2 and lf_pair and ext_id:
                # seg = [B, A] (луч BA), beyond A — ext_id на расстоянии |AM|.
                origin = beyond if beyond and beyond in seg else seg[1]
                away_from = seg[0] if origin == seg[1] else seg[1]
                c["type"] = "point_on_ray"
                engine_type = "point_on_ray"
                c["origin"] = origin
                c["away_from"] = away_from
                # «AD = AM»: расстояние = |AM| = dist(A, M).  length_from — пара
                # [rhs1, rhs2]; движок считает dist(rhs1, rhs2).  Раньше передавали
                # одну точку M и считали dist(origin, M) — совпадало с |AM| только
                # когда origin == A (первая буква правой части); для «BD = AM»
                # получали |BM| ≠ |AM|.
                c["length_from"] = lf_pair
                c["id"] = ext_id
                created.add(ext_id)
            elif len(seg) >= 2:
                p1 = seg[0]
                p2 = beyond if beyond and beyond in seg else seg[1]
                c["type"] = "reflect_point"
                c["point"] = p1
                c["center"] = p2
                if ext_id:
                    c["id"] = ext_id
                    created.add(ext_id)
            else:
                issues.append("LINE_EXTENSION_NO_SEGMENT")
                continue
        elif op == "circle_center_radius":
            c["center"] = ac.get("center", "")
            c["radius_point"] = ac.get("through", "")
            pts = [p for p in (ac.get("points") or []) if isinstance(p, str)]
            if not c["center"] and not c["radius_point"] and len(pts) >= 2:
                c["center"] = pts[0]
                c["radius_point"] = pts[1]
        elif op == "tangent_at_point":
            c["circle"] = ac.get("circle", "")
            c["p1"] = ac.get("point", "")
        elif op == "line_intersection":
            l1 = [x for x in (ac.get("line1") or []) if isinstance(x, str)]
            l2 = [x for x in (ac.get("line2") or []) if isinstance(x, str)]
            pts = [p for p in (ac.get("points") or []) if isinstance(p, str)]
            # CH-fidelity: если solver не дал id результата, достаём его из quote
            # («...до пересечения с AB в точке E» -> E).  Без этого следующее
            # построение, ссылающееся на E, падает с UNRESOLVED_POINT:E.
            inter_id = ac.get("id") or _intersection_id_from_quote(ac)
            # CH-aux FIX (жёсткий): GPT шлёт этот op в разных форматах.
            #   1) line1/line2 — пары точек (['A','B']) ИЛИ [точка, id линии];
            #   2) points: [p1, p2, p3, p4] — две прямые p1-p2 и p3-p4.
            # Если элемента пары нет среди уже созданных точек — это id линии
            # (например ['A', 'l_A']), берём его как прямую-опору целиком.

            # CH-fidelity special case: points=[M, E, A, B] — «через M
            # (параллель уже построена) до пересечения с AB в точке E».
            # p1=M (есть parallel_line через M), p2=E (результат), p3/p4=A/B.
            # Разрешаем line1 из parallel_lines, а AB создаём как линию.
            handled = False
            if (not l1 and not l2 and len(pts) >= 4
                    and inter_id and inter_id in pts
                    and pts[0] in parallel_lines):
                line1_id = parallel_lines[pts[0]]
                line2_id = f"aux_line_{pts[2]}{pts[3]}"
                constructions.append({
                    "type": "line", "id": line2_id,
                    "p1": pts[2], "p2": pts[3],
                    "style": "aux", "dashed": True, "visual_role": "aux",
                    "purpose": "вспомогательная прямая",
                    "solution_evidence": {"step_no": step_no, "quote": quote},
                })
                created.add(line2_id)
                c["line1"] = line1_id
                c["line2"] = line2_id
                c["id"] = inter_id
                created.add(inter_id)
                handled = True

            def _resolve_pair(pair):
                # Вернуть (id линии, [p1, p2]) или (None, None).
                if len(pair) < 2:
                    return None, None
                a, b = pair[0], pair[1]
                a_is_pt = a in created
                b_is_pt = b in created
                if a_is_pt and b_is_pt:
                    lid = f"aux_line_{a}{b}"
                    return lid, [a, b]
                # [точка, будущая точка-результат] — например [M, E], где E ещё
                # не существует, но есть параллельная прямая через M.
                if a_is_pt and not b_is_pt and b == inter_id and a in parallel_lines:
                    return parallel_lines[a], None
                if b_is_pt and not a_is_pt and a == inter_id and b in parallel_lines:
                    return parallel_lines[b], None
                # [точка, id-линии] — линия уже существует в base/aux.
                if a_is_pt and not b_is_pt:
                    return b, None
                if b_is_pt and not a_is_pt:
                    return a, None
                # Оба не точки — считаем b id линии.
                return b, None

            r1_line, r1_pair = _resolve_pair(l1)
            r2_line, r2_pair = _resolve_pair(l2)
            # Если одна сторона — id существующей линии, а другая — пара точек,
            # создаём промежуточную линию для пары точек (иначе движок упадёт с
            # «прямая не найдена»).
            for lid, pair in ((r1_line, r1_pair), (r2_line, r2_pair)):
                if pair:
                    lid = f"aux_line_{pair[0]}{pair[1]}"
                    if lid not in created:
                        constructions.append({
                            "type": "line", "id": lid, "p1": pair[0], "p2": pair[1],
                            "style": "aux", "dashed": True, "visual_role": "aux",
                            "hidden": True,
                            "purpose": "вспомогательная прямая для пересечения",
                            "solution_evidence": {"step_no": step_no, "quote": quote},
                        })
                        created.add(lid)

            if r1_line and r2_line:
                # Обе стороны — id уже существующих линий.
                c["line1"] = r1_line
                c["line2"] = r2_line
                c["id"] = inter_id or f"aux_inter_{i}"
                created.add(c["id"])
            elif r1_pair and r2_pair:
                # Обе стороны — пары точек; создаём промежуточные линии.
                c["line1"] = r1_line
                c["line2"] = r2_line
                for lid, pair in ((r1_line, r1_pair), (r2_line, r2_pair)):
                    constructions.append({
                        "type": "line", "id": lid, "p1": pair[0], "p2": pair[1],
                        "style": "aux", "dashed": True, "visual_role": "aux",
                        "hidden": True,
                        "purpose": "вспомогательная прямая для пересечения",
                        "solution_evidence": {"step_no": step_no, "quote": quote},
                    })
                    created.add(lid)
                c["id"] = inter_id or f"aux_inter_{i}"
                created.add(c["id"])
            elif len(pts) >= 4 and not (
                    inter_id and inter_id in pts and pts[0] in parallel_lines):
                # Две прямые: p1-p2 и p3-p4 (обычный случай; special case выше
                # уже установил line1/line2, не перезаписываем его p1..p4).
                c["p1"], c["p2"], c["p3"], c["p4"] = pts[0], pts[1], pts[2], pts[3]
                c["id"] = inter_id or f"aux_inter_{i}"
                created.add(c["id"])
            elif not handled:
                issues.append("INTERSECTION_NO_LINES")
                continue
        elif op == "reflect_point":
            # Контракт: point:P, over_line:[A,B], id:NEW — отразить точку P
            # относительно прямой AB (ОСЕВАЯ симметрия).  Движковый тип
            # reflect_point_over_line требует p1 (точка) и line1 (id линии).
            p = ac.get("point", "")
            line = [x for x in (ac.get("over_line") or []) if isinstance(x, str)]
            pts = [x for x in (ac.get("points") or []) if isinstance(x, str)]
            if not p and pts:
                p = pts[0]
            if len(line) < 2 and len(pts) >= 3:
                p = p or pts[0]
                line = [pts[1], pts[2]]
            if p and len(line) >= 2:
                line_id = f"aux_reflect_line_{line[0]}{line[1]}"
                constructions.append({
                    "type": "line", "id": line_id, "p1": line[0], "p2": line[1],
                    "style": "aux", "dashed": True, "visual_role": "aux",
                    "purpose": "ось симметрии",
                    "solution_evidence": {"step_no": step_no, "quote": quote},
                })
                created.add(line_id)
                c["p1"] = p
                c["line1"] = line_id
            else:
                issues.append("REFLECT_NO_LINE")
                continue
            rid = ac.get("id", "")
            if rid:
                c["id"] = rid
                created.add(rid)
        elif op == "mark_equal_segments":
            # Контракт: segments:[P1,P2,P3,P4,...] — список пар точек равных
            # отрезков; count:N — число насечек (1 по умолчанию).  Движковый
            # тип equal_segments_mark рисует насечки в середине каждого отрезка.
            seg = [x for x in (ac.get("segments") or []) if isinstance(x, str)]
            if len(seg) % 2 != 0:
                issues.append("EQUAL_SEGMENTS_ODD_POINTS")
                continue
            if len(seg) < 2:
                issues.append("EQUAL_SEGMENTS_NO_POINTS")
                continue
            c["segments"] = seg
            try:
                cnt = int(ac.get("count", 1) or 1)
            except (TypeError, ValueError):
                cnt = 1
            c["count"] = cnt
            c["id"] = ac.get("id", f"aux_eqseg_{i}")
            # E18: если ВСЕ пары равенства уже заданы в условии (середины /
            # equal_segments базы) — не дублируем насечки поверх midpoint_mark.
            seg_pairs = [frozenset((seg[k], seg[k + 1]))
                         for k in range(0, len(seg) - 1, 2)]
            if seg_pairs and all(p in given_equal for p in seg_pairs):
                issues.append(f"FULFILLED_BY_BASE:mark_equal_segments:{c['id']}")
                continue

        # Стабильный id, если не задан.
        if "id" not in c:
            c["id"] = f"aux_{op}_{i}"

        # Не переопределять base.
        if c["id"] in base_ids:
            issues.append(f"DUPLICATE_IN_BASE:{c['id']}")
            continue

        # CH-aux FIX (E8): solver пере-диктует данное условие (медиана/высота/
        # биссектриса из условия) как aux-операцию. Её foot_id уже существует в
        # base — повторное создание точки в движке падает с «точка уже
        # существует». Это НЕ потеря построения: элемент уже нарисован в base
        # (midpoint M + segment BM реализуют медиану BM). Пропускаем как
        # выполненное базой. Без этого фикса весь aux-рендер падает на одной
        # пере-диктованной операции.
        _foot = c.get("foot_id")
        if _foot and _foot in base_ids and engine_type in ("altitude", "median", "angle_bisector"):
            issues.append(f"FULFILLED_BY_BASE:{engine_type}:{_foot}")
            continue

        # CH-aux FIX (жёсткая валидация): построение с неполным набором
        # обязательных опор отбрасываем отдельно, не роняя весь aux.
        missing = _missing_required_fields(engine_type, c)
        if missing:
            issues.append(f"MISSING_FIELDS:{engine_type}:{','.join(missing)}")
            continue

        # Проверка ссылок (упрощённая: строки-точки существуют).
        refs = _refs_of(c)
        unresolved = [r for r in refs
                      if r and r not in created and r != c.get("foot_id") and r != c.get("id")]
        if unresolved:
            for r in unresolved:
                issues.append(f"UNRESOLVED_POINT:{r}")
            continue

        # Атрибуты aux-объекта.
        c["style"] = "aux"
        c["dashed"] = True
        c["visual_role"] = "aux"
        c["purpose"] = ac.get("purpose", "доп. построение из решения")
        c["solution_evidence"] = {"step_no": step_no, "quote": quote}

        constructions.append(c)

        # CH-aux FIX (E9): для line_extension → reflect_point (центральная
        # симметрия: отразить point P относительно center C → новая точка K)
        # эмитить видимый отрезок продления C–K. Иначе точка K создаётся, но на
        # чертеже повисает без линии — продление не видно (K уходит за кадр и
        # не связан с исходной фигурой). Отрезок C–K — это новая часть продления
        # (исходный P–C уже есть в base как данное).
        if engine_type == "reflect_point" and c.get("center") and c.get("id"):
            constructions.append({
                "type": "segment", "id": f"aux_ext_{c['id']}",
                "p1": c["center"], "p2": c["id"],
                "style": "aux", "dashed": True, "visual_role": "aux",
                "purpose": "продление отрезка за центр симметрии",
                "solution_evidence": {"step_no": step_no, "quote": quote},
            })

        # CH-fidelity: регистрируем параллельную прямую (точка -> id), чтобы
        # последующий line_intersection мог ссылаться на неё как на линию.
        if c.get("type") == "parallel_line" and c.get("point"):
            parallel_lines[c["point"]] = c["id"]
        created.add(c["id"])

    has_aux = len(constructions) > 0
    return {"has_aux": has_aux, "reason": "", "constructions": constructions}, issues


# ──────────────────────────────────────────────────────────────────────────
# CH-fidelity: численная проверка, что компилятор сохранил построения solver'а
# ──────────────────────────────────────────────────────────────────────────

def fidelity_report(solver_result: dict, base_plan: dict) -> Dict[str, Any]:
    """Сравнить объявленные aux_constructions с тем, что реально скомпилировано.

    Использует РЕАЛЬНЫЙ результат compile_solver_aux: каждый код в issues
    соответствует одному отброшенному построению.  Особый случай — вписанная
    окружность: компилятор сворачивает цепочку «биссектрисы -> O ->
    перпендикуляры -> окружность» в нативный план и возвращает issues=[].

    Возвращает:
      {
        "declared": int,        # сколько построений объявил solver
        "compiled": int,        # сколько реально попало в план движка
        "dropped": int,         # потеряно
        "ratio": float,         # compiled / declared (0..1)
        "issues": [str, ...],   # коды потерь
        "ok": bool,             # ничего не потеряно
      }
    """
    aux_cs = (solver_result or {}).get("aux_constructions", []) or []
    declared = len(aux_cs)
    if declared == 0:
        return {"declared": 0, "compiled": 0, "dropped": 0, "ratio": 1.0,
                "issues": [], "ok": True}

    compiled_plan, issues = compile_solver_aux(solver_result, base_plan)

    # Вписанная окружность / нативный план без потерь.
    if not issues and compiled_plan.get("has_aux"):
        return {"declared": declared, "compiled": declared, "dropped": 0,
                "ratio": 1.0, "issues": [], "ok": True}

    # DUPLICATE_IN_BASE и FULFILLED_BY_BASE — НЕ потеря: объект уже существует
    # в base (DUPLICATE_IN_BASE — по id; FULFILLED_BY_BASE — solver пере-диктовал
    # данное условие как aux, и его foot_id уже в base).  Повторно строить его не
    # нужно, repair запускать не обязательно.
    real_issues = [i for i in issues
                   if not i.startswith("DUPLICATE_IN_BASE")
                   and not i.startswith("FULFILLED_BY_BASE")]

    dropped = min(len(real_issues), declared)
    compiled = declared - dropped
    ratio = round(compiled / declared, 4) if declared else 1.0
    return {
        "declared": declared,
        "compiled": compiled,
        "dropped": dropped,
        "ratio": ratio,
        "issues": real_issues,
        "ok": dropped == 0,
    }
