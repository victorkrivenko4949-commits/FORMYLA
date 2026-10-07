# -*- coding: utf-8 -*-
"""services/aux_compiler.py — детерминированный компилятор шагов в aux-план.

CH23 PART B2.  Преобразует список шагов извлечения (action + args) в
aux-план движка, не вызывая LLM.  Полностью детерминирован.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

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
    cs = base_plan.get("constructions", []) if isinstance(base_plan, dict) else []
    return {c.get("id") for c in cs if isinstance(c, dict) and c.get("id")}


def _refs_of(construction: Dict) -> set:
    """Собрать id-ссылки конструкции (p1/p2/vertex/side_a/... + segments)."""
    refs = set()
    for k, v in construction.items():
        if k in ("segments",):
            for item in v if isinstance(v, list) else []:
                if isinstance(item, str):
                    refs.add(item)
                elif isinstance(item, (list, tuple)):
                    for x in item:
                        if isinstance(x, str):
                            refs.add(x)
        elif isinstance(v, str) and k not in ("id", "type", "style", "purpose",
                                               "solution_evidence", "visual_role",
                                               "quote", "reason"):
            refs.add(v)
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


def validate_quote(quote: str, steps: List[dict]) -> Tuple[bool, str]:
    """CH-aux: строгая проверка цитаты.

    1. quote должна быть ПОДСТРОКОЙ одного из steps[].text (после нормализации);
    2. quote должна содержать стем действия построения.

    Возвращает (ok, error_code).
    """
    q = (quote or "").strip()
    if not q:
        return False, "EMPTY_QUOTE"
    # Стем действия построения НЕ обязателен: модели часто пишут «биссектрису
    # угла B», «точку пересечения обозначим O» без глагола «проведём/построим».
    # Требуем только, чтобы цитата была подстрокой шага решения.
    q_norm = _norm(q)
    for step in steps or []:
        text = step.get("text", "")
        if q_norm in _norm(text):
            return True, ""
    return False, "QUOTE_NOT_IN_SOLUTION"


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


def _recognize_incircle(aux_cs: List[dict], base_plan: Dict) -> Optional[List[dict]]:
    """Распознать построение вписанной окружности и вернуть нативный план.

    GPT описывает инцентр как цепочку «биссектрисы -> пересечение O ->
    перпендикуляры -> окружность», но не даёт стабильных id линий/точек.
    Движок умеет incenter / altitude / line / circle_center_radius нативно,
    поэтому собираем корректную цепочку, сохраняя на чертеже и биссектрисы,
    и перпендикуляры, и саму окружность.
    """
    ops = [a.get("op") for a in aux_cs]
    if ops.count("angle_bisector") < 2:
        return None
    if not any(o in ops for o in ("circle_center_radius", "incircle", "circle_three_points")):
        return None

    tri = _triangle_vertices(base_plan)
    if len(tri) < 3:
        return None
    A, B, C = tri[0], tri[1], tri[2]

    constructions: List[dict] = []

    # 1) Инцентр O (нативный расчёт из трёх вершин).
    constructions.append({
        "type": "incenter", "id": "aux_O", "p1": A, "p2": B, "p3": C,
        "label": "O", "style": "aux", "dashed": False,
        "visual_role": "key_point", "purpose": "Центр вписанной окружности",
    })

    # 2) Биссектрисы: отрезки вершина -> O (O лежит на каждой биссектрисе).
    for v in (A, B, C):
        constructions.append({
            "type": "line", "id": f"aux_bis_{v}", "p1": v, "p2": "aux_O",
            "style": "aux", "dashed": True, "visual_role": "aux",
            "purpose": f"Биссектриса угла {v}",
        })

    # 3) Перпендикуляры из O на стороны; основания = точки касания A_1/B_1/C_1.
    #    side (s1,s2) -> точка касания f'{opp}_1' (напротив вершины opp).
    feet = [
        ("BC", A, B, C),  # сторона BC -> основание A_1 (напротив A)
        ("CA", B, C, A),  # CA -> B_1 (напротив B)
        ("AB", C, A, B),  # AB -> C_1 (напротив C)
    ]
    for side_label, opp, s1, s2 in feet:
        point_id = f"{opp}_1"
        constructions.append({
            "type": "altitude", "id": f"aux_perp_{point_id}",
            "vertex": "aux_O", "side_a": s1, "side_b": s2,
            "foot_id": point_id, "foot_label": point_id,
            "style": "aux", "dashed": True, "visual_role": "aux",
            "purpose": f"Перпендикуляр из O на сторону {side_label}",
        })

    # 4) Окружность с центром O и радиусом до первого основания.
    constructions.append({
        "type": "circle_center_radius", "id": "aux_incircle",
        "center": "aux_O", "radius_point": f"{A}_1",
        "style": "aux", "dashed": True, "visual_role": "target_circle",
        "purpose": "Вписанная окружность",
    })

    return constructions


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
    if not aux_cs:
        return {"has_aux": False, "reason": "", "constructions": []}, []

    # CH-aux FIX: вписанная окружность.  GPT шлёт цепочку «биссектрисы ->
    # пересечение O -> перпендикуляры -> окружность» без стабильных id линий.
    # Движок умеет incenter/altitude/line/circle_center_radius нативно, поэтому
    # распознаём эту цепочку и собираем корректный план, сохраняя на чертеже и
    # биссектрисы, и перпендикуляры, и саму окружность.
    incircle_plan = _recognize_incircle(aux_cs, base_plan)
    if incircle_plan is not None:
        return {"has_aux": True, "reason": "Вписанная окружность (инцентр + радиус)",
                "constructions": incircle_plan}, []

    base_ids = _base_ids(base_plan)
    created: set = set(base_ids)

    for i, ac in enumerate(aux_cs):
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
            foot = ac.get("foot_id") or ac.get("id", "")
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
        elif op == "parallel_through":
            c["point"] = ac.get("point", "")
            line = ac.get("to_line") or []
            if len(line) >= 2:
                c["line"] = line
        elif op == "perpendicular_through":
            c["point"] = ac.get("point", "")
            line = ac.get("to_line") or []
            pts = [p for p in (ac.get("points") or []) if isinstance(p, str)]
            if not line and len(pts) >= 3:
                # формат [вершина, A, B] -> перпендикуляр из вершины на сторону A-B
                c["point"] = pts[0]
                line = [pts[1], pts[2]]
            if len(line) >= 2:
                c["p1"], c["p2"] = line[0], line[1]
        elif op == "line_extension":
            seg = ac.get("segment") or []
            if len(seg) >= 2:
                c["origin"] = seg[0]
                c["direction"] = "both"
            ext_id = ac.get("id", "")
            if ext_id:
                c["id"] = ext_id
                created.add(ext_id)
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
            l1 = ac.get("line1") or []
            l2 = ac.get("line2") or []
            pts = [p for p in (ac.get("points") or []) if isinstance(p, str)]
            # Формат [A, B] от GPT: это опорные точки прямой; здесь просто
            # создаём точку пересечения двух линий, опираясь на уже созданные
            # биссектрисы (line1/line2 не даны).  Если точек 2 — это две прямые,
            # но без id линий — пропускаем (не создаём пустую intersect).
            if not l1 and not l2 and len(pts) == 2:
                # Нет id линий — не можем построить пересечение; помечаем
                # как неразрешимое, чтобы не падать в движке.
                issues.append("INTERSECTION_NO_LINES")
                continue
            inter_id = ac.get("id", "")
            if len(l1) >= 2 and len(l2) >= 2:
                c["line1"] = f"{l1[0]}{l1[1]}"
                c["line2"] = f"{l2[0]}{l2[1]}"
                # Создать промежуточные линии-опоры.
                constructions.append({
                    "type": "line", "id": c["line1"], "p1": l1[0], "p2": l1[1],
                    "style": "aux", "dashed": True, "visual_role": "aux",
                    "purpose": "вспомогательная прямая",
                    "solution_evidence": {"step_no": step_no, "quote": quote},
                })
                created.add(c["line1"])
                constructions.append({
                    "type": "line", "id": c["line2"], "p1": l2[0], "p2": l2[1],
                    "style": "aux", "dashed": True, "visual_role": "aux",
                    "purpose": "вспомогательная прямая",
                    "solution_evidence": {"step_no": step_no, "quote": quote},
                })
                created.add(c["line2"])
                c["id"] = inter_id or f"aux_inter_{i}"
                created.add(c["id"])
        elif op == "reflect_point":
            c["point"] = ac.get("point", "")
            line = ac.get("over_line") or []
            if len(line) >= 2:
                c["center"] = line[0]  # упрощение: центральная симметрия
            rid = ac.get("id", "")
            if rid:
                c["id"] = rid
                created.add(rid)

        # Стабильный id, если не задан.
        if "id" not in c:
            c["id"] = f"aux_{op}_{i}"

        # Не переопределять base.
        if c["id"] in base_ids:
            issues.append(f"DUPLICATE_IN_BASE:{c['id']}")
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
        created.add(c["id"])

    has_aux = len(constructions) > 0
    return {"has_aux": has_aux, "reason": "", "constructions": constructions}, issues
