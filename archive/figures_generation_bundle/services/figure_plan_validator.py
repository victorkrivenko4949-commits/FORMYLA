# -*- coding: utf-8 -*-
"""services/figure_plan_validator.py — детерминированная проверка инвариантов.

CH15: Проверяет связь base ↔ aux без LLM.  Дополняет services.figure_validator
(который проверяет каждый отдельный план на соответствие geometric_engine).

Правила:
  * base.constructions не могут содержать style=="aux" или dashed==true.
  * Каждый aux-объект обязан иметь: dashed==true, style=="aux",
    purpose и solution_evidence.quote (непустые).
  * Все ID, на которые ссылается aux, должны существовать в base либо
    быть созданы ранее внутри aux.
  * Aux-объект не должен дублировать base-объект (по id).
  * Aux не может переопределять id, уже объявленный в base.
  * Ссылочные поля у aux проверяются в том же порядке, что и движок.

Возвращает {"valid": bool, "errors": [str, ...]}.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set

# Поля, которые являются ссылками на id точек/линий/окружностей.
_REFERENCE_FIELDS = [
    'p1', 'p2', 'p3', 'p4', 'center', 'line1', 'line2',
    'circle', 'circle1', 'circle2', 'origin',
    # CH15 aliases из новых промптов.
    'a', 'b', 'vertex', 'side_a', 'side_b', 'points',
    # CH15.1: поля контракта altitude / right_angle_mark / angle_label.
    'ray1', 'ray2',
    # BUG-4: inscribed_polygon объявляет вершины через vertices — они тоже
    # должны валидироваться как ссылки (симметрия с _declared_ids).
    'vertices',
]

# CH15.1: операции, которые создают новую точку-результат и обязаны
# выдавать её id (foot_id у altitude).  Без явного id следующая операция
# не может на неё ссылаться.
_POINT_CREATING_TYPES = {"altitude", "median", "angle_bisector"}

# CH15.1: сегменты/прямые/лучи в aux допустимы ТОЛЬКО при явном действии
# построения в solution_evidence.quote.  Доказательная фраза вида
# «MC является радиусом» не разрешает строить отрезок MC.
_SEGMENT_LIKE_TYPES = {"segment", "line", "ray"}

# Глаголы явного построения (стемы, покрывают формы «проведём/проведена»,
# «соединим», «продлим», «построим», «опустим», «обозначим»).
_CONSTRUCTION_ACTION_STEMS = (
    "провед", "соедин", "продл", "постро", "опуст",
)

# CH16: разрешённый enum visual_role.  Прямые hex/rgb/hsl цвета не принимаются.
_VALID_VISUAL_ROLES = frozenset({
    "base", "aux", "reference_circle", "target_circle", "key_point",
    "right_angle_mark", "given_mark", "secondary",
})

# ── CH19: защита от служебных имён в видимых подписях ─────────────────────
# Подпись (text у angle_label / length_label / point_label и label у точек)
# не должна быть внутренним id-именем переменной, вроде "len_AB", "seg_BC".
_VAR_LABEL_RE = re.compile(
    r"^(?:len|dist|length|side|seg|val|var)[_\-]?[A-Za-z0-9]*$",
    re.IGNORECASE,
)
# Имя с подчёркиванием, если оно не несёт математического смысла
# (нет цифр, знака градуса, и это не «число_единица»).
_UNDERSCORE_ONLY_RE = re.compile(r"^[A-Za-z_]+$")

# Разрешённые паттерны подписей (числа, градусы, буквы из условия, выражения).
_OK_LABEL_RE = re.compile(
    r"^(?:"
    r"\d+(?:[.,]\d+)?\s*(?:см|м|мм)?|"                # 6, 4.5, 6 см
    r"\d*\s*°|"                                        # 40°
    r"[A-Za-zαβγ]\d*(?:\s*[°x])?|"                     # a, x, 2x, α
    r"[A-Za-zαβγ]\d*\s*[+\-]\s*\d+|"                   # x+1
    r"[A-Za-zαβγ]\d*\s*°|"                             # a°
    r"\d*\s*[A-Za-zαβγ]"                               # 3a, 2x
    r")$"
)

# Поля-потенциальные носители прямых цветов (запрещены для LLM JSON).
_COLOR_FIELDS = ("color", "stroke", "fill", "hex", "rgb", "hsl")

# ── BUG-1: триггеры для безусловных MISSING_GIVEN_* warnings ───────────────
# Warning «отсутствует метка» допустим ТОЛЬКО если условие действительно
# требует эту метку.  Иначе repair-модель дописывает несуществующие объекты.
_EQUALITY_TRIGGER_RE = re.compile(
    r"([A-Z]{2}\s*=\s*[A-Z]{2}|равн[ыоае]|равнобедренн|равносторонн|"
    r"ромб|квадрат|середин|медиан|биссектрис\w*\s+дел)",
    re.IGNORECASE,
)
_ANGLE_TRIGGER_RE = re.compile(
    r"(\d+\s*[°градус]|угол\s+\w+\s+равен|∠)",
    re.IGNORECASE,
)
_RIGHT_ANGLE_TRIGGER_RE = re.compile(
    r"(прям(ой|ым)\s+угол|перпендикуляр|90\s*°|высот[аыу]|"
    r"прямоугольн\w*\s+треугольник|прямоугольник|квадрат)",
    re.IGNORECASE,
)
_MIDPOINT_TRIGGER_RE = re.compile(
    r"(середин|медиан|дел\w*\s+пополам)",
    re.IGNORECASE,
)


def _has_construction_action(quote: str) -> bool:
    """True, если цитата содержит явное действие построения (не доказательство)."""
    q = (quote or "").lower()
    return any(stem in q for stem in _CONSTRUCTION_ACTION_STEMS)


def is_invalid_label_text(text: Any, object_id: Optional[str] = None) -> bool:
    """Детерминированно определить, является ли видимая подпись служебной.

    Возвращает True, если text запрещён (внутреннее имя переменной, а не
    математическая величина).  Используется и валидатором (INVALID_LABEL_TEXT),
    и последним барьером в render_svg (SKIPPED_INVALID_LABEL).
    """
    s = (text or "").strip()
    if not s:
        return False
    # 1) Совпадение с внутренним id объекта.
    if object_id is not None and s == str(object_id):
        return True
    # 2) Явный паттерн переменной: len_AB / seg_BC / dist / length / ...
    if _VAR_LABEL_RE.match(s):
        return True
    # 3) Содержит подчёркивание и при этом не несёт математического смысла
    #    (нет цифр, знака градуса).  "AB_2" -> допустимо (цифра есть),
    #    "len_AB" -> запрещено.
    if "_" in s:
        if not re.search(r"\d", s) and "°" not in s:
            return True
    # 4) Выглядит как имя переменной, а не как величина: строка из букв +
    #    подчёркиваний длиной > 1, не совпадающая с разрешённым паттерном.
    if _UNDERSCORE_ONLY_RE.match(s) and len(s) > 1:
        if not _OK_LABEL_RE.match(s):
            return True
    return False


def validate_label_texts(constructions: List[dict]) -> List[str]:
    """Проверить видимые текстовые подписи в списке построений.

    Возвращает список ошибок вида "INVALID_LABEL_TEXT: ...".
    """
    errors: List[str] = []
    for i, c in enumerate(constructions):
        if not isinstance(c, dict):
            continue
        prefix = f"constructions[{i}]"
        ctype = c.get("type") or ""
        cid = c.get("id")

        # angle_label / length_label: text (или label)
        if ctype in ("angle_label", "length_label"):
            label = c.get("text", c.get("label"))
            if is_invalid_label_text(label, cid):
                errors.append(
                    f"INVALID_LABEL_TEXT: {prefix} '{cid}' ({ctype}) has "
                    f"invalid label text {label!r}"
                )
        elif ctype == "point_label":
            label = c.get("label", c.get("text"))
            if is_invalid_label_text(label, cid):
                errors.append(
                    f"INVALID_LABEL_TEXT: {prefix} '{cid}' (point_label) has "
                    f"invalid label text {label!r}"
                )
        else:
            # label у точек (free_point и пр.) тоже видимый текст.
            label = c.get("label")
            if isinstance(label, str) and label:
                # label точки — это имя точки (A, B, M, O).  Не считаем
                # служебным, если совпадает с id (стандартный случай).
                if label != str(cid) and is_invalid_label_text(label, cid):
                    errors.append(
                        f"INVALID_LABEL_TEXT: {prefix} '{cid}' ({ctype}) has "
                        f"invalid label text {label!r}"
                    )
    return errors


def _loads(data) -> Any:
    if isinstance(data, dict):
        return data
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", "replace")
    if not isinstance(data, str) or not data.strip():
        return None
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return None


def _constructions_of(plan: Any, key: str = "constructions") -> List[dict]:
    """Извлечь список построений из base/aux плана (v2-структура или flat)."""
    if not isinstance(plan, dict):
        return []
    cs = plan.get(key)
    if isinstance(cs, list):
        return [c for c in cs if isinstance(c, dict)]
    return []


def _base_constructions(plan: Any) -> List[dict]:
    """Base-план может быть v2 (base.constructions) или flat."""
    if not isinstance(plan, dict):
        return []
    if "base" in plan and isinstance(plan["base"], dict):
        return _constructions_of(plan["base"])
    return _constructions_of(plan)


def _aux_plan(plan: Any) -> Dict[str, Any]:
    """Aux-план может быть v2 (aux.has_aux/constructions) или flat."""
    if not isinstance(plan, dict):
        return {}
    if "aux" in plan and isinstance(plan["aux"], dict):
        return plan["aux"]
    return plan


def _declared_ids(constructions: List[dict]) -> Set[str]:
    ids: Set[str] = set()
    for c in constructions:
        cid = c.get("id")
        if isinstance(cid, str) and cid:
            ids.add(cid)
        # CH26 FIX2: inscribed_polygon объявляет вершины как точки.
        if c.get("type") == "inscribed_polygon":
            for v in c.get("vertices", []) or []:
                if isinstance(v, str) and v:
                    ids.add(v)
        # CH26 FIX1: point_on_circle объявляет точку через id (уже учтён).
    return ids


def all_produced_ids(constructions: List[dict]) -> Set[str]:
    """Все id точек, которые ПОРОЖДАЮТ построения.

    В отличие от _declared_ids, учитывает и поля-результаты операций, которые
    создают новые точки без явного id: foot_id у altitude/median/angle_bisector,
    вершины inscribed_polygon, и id-поля операций пересечения.  Переиспользуется
    в services/condition_coverage.py (проверка A · точки условия).
    """
    ids: Set[str] = set()
    point_creating = {"altitude", "median", "angle_bisector"}
    intersection_types = {
        "intersect_lines", "intersect_line_circle", "intersect_circles",
        "foot_perpendicular", "midpoint", "point_on_segment",
        "point_on_circle", "reflect_point", "rotate_point",
    }
    for c in constructions:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if isinstance(cid, str) and cid:
            ids.add(cid)
        ctype = c.get("type") or ""
        # Вершины вписанного многоугольника.
        if ctype == "inscribed_polygon":
            for v in c.get("vertices", []) or []:
                if isinstance(v, str) and v:
                    ids.add(v)
        # foot_id у операций, создающих точку-результат.
        foot = c.get("foot_id")
        if ctype in point_creating and isinstance(foot, str) and foot:
            ids.add(foot)
        # Операции пересечения объявляют точку своим id (уже учтено), но
        # также могут порождать точку через creates_point — покрыто выше.
    return ids


def _referenced_ids(c: dict) -> Set[str]:
    """Все id, на которые ссылается конструкция через ссылочные поля."""
    refs: Set[str] = set()
    for field in _REFERENCE_FIELDS:
        val = c.get(field)
        if isinstance(val, str) and val:
            refs.add(val)
        elif isinstance(val, list):
            for v in val:
                if isinstance(v, str) and v:
                    refs.add(v)
                # триплет углов: [p1, vertex, p3]
                elif isinstance(v, list):
                    for vv in v:
                        if isinstance(vv, str) and vv:
                            refs.add(vv)
    return refs


def extract_condition_points(statement: str) -> Set[str]:
    """Извлечь из условия одиночные заглавные обозначения точек.

    Учитывает контекст «точка X», «в точке X», «X — середина», «середина X»,
    «O — центр», «центр O», «основание высоты X», «пересекаются в X»,
    «обозначим X», «отметим X», «основание перпендикуляра X», «вершина X».
    НЕ считает точками обозначения фигур (ABC), углов (AOB) и отрезков (AB).
    """
    if not statement:
        return set()
    from services.text_normalize import normalize_condition
    statement = normalize_condition(statement)
    points: Set[str] = set()

    # Явные декларации точки (BUG-7: добавлены формы «середина M»,
    # «O — центр», «пересекаются в P», «обозначим K», «отметим K»,
    # «основание перпендикуляра/высоты H»).
    patterns = [
        r"точк[ауе]?\s+([A-Z])",
        r"([A-Z])\s*[—–-]\s*(?:середина|центр|основание|точка пересечения)",
        r"середин[аыуе]\s+\w*\s*([A-Z])",
        r"центр\w*\s+(?:\w+\s+){0,3}([A-Z])\b",
        r"основани[ея]\s+(?:перпендикуляра|высоты)\s+([A-Z])",
        r"в\s+точке\s+([A-Z])",
        r"пересека\w+\s+(?:\w+\s+){0,3}в\s+точке\s+([A-Z])",
        r"(?:обознач|отмет)\w+\s+(?:\w+\s+){0,2}([A-Z])",
        r"вершин[аыуе]?\s+([A-Z])",
    ]
    for pat in patterns:
        for m in re.finditer(pat, statement, re.IGNORECASE):
            for g in m.groups():
                if g:
                    points.add(g)

    # Имена фигур с перечислением вершин: «треугольник ABC»,
    # «четырёхугольник ABCD», «квадрат ABCD» — каждая буква объявляет точку.
    # BUG-7: «трапец[ия]{2}» → «трапеци[а-я]*» (покрывает «трапеция»/«трапеции»).
    for m in re.finditer(
        r"(?:треугольник|четыр[ёе]хугольник|квадрат|прямоугольник|"
        r"параллелограмм|ромб|трапеци[а-я]*|многоугольник|"
        r"п[я]тиугольник|шестиугольник)[а-я]*\s+([A-Z]{2,8})",
        statement,
    ):
        for ch in m.group(1):
            points.add(ch)

    # Буквы сразу после знака угла (∠A, ∠ABC) — НЕ точки (это обозначение угла).
    # Убираем их, если они были захвачены предыдущими паттернами как одиночные.
    angle_letters: Set[str] = set()
    for m in re.finditer(r"∠\s*([A-Z]{1,3})", statement):
        for ch in m.group(1):
            angle_letters.add(ch)

    points -= angle_letters
    return points


def check_condition_points(statement: str, base_plan: Any) -> List[str]:
    """Проверить, что все объявленные в условии точки созданы в base.

    Возвращает список warnings вида MISSING_CONDITION_POINT.
    """
    points = extract_condition_points(statement)
    if not points:
        return []
    base_cs = _base_constructions(base_plan)
    declared = _declared_ids(base_cs)
    warnings = []
    for p in sorted(points):
        if p not in declared:
            warnings.append(
                f"MISSING_CONDITION_POINT: точка '{p}' объявлена в условии, "
                f"но не создана в base-плане"
            )
    return warnings


# CH26 FIX4 / BUG-2: формулировки условия, требующие инцидентности точки/объекта.
# Регексы несут capture-группы с именем точки, чтобы проверять ТОЛЬКО точку,
# названную в инцидентном контексте, а не все free_point подряд.
_INSCRIBED_RE = re.compile(
    r"(вписан\w*\s+в\s+окружност|вписанн\w*\s+четыр[ёе]хугольник|"
    r"вписанн\w*\s+треугольник|вписанн\w*\s+многоугольник)",
    re.IGNORECASE,
)
_ON_CIRCLE_RE = re.compile(
    r"(?:"
    r"точк\w+\s+((?:[A-Z]\s*,?\s*)+)\s*(?:лежат|лежит)\s+на\s+окружност"
    r"|на\s+окружност\w+\s+(?:выбран|взят|отмечен)\w*\s+точк\w+\s+([A-Z])"
    r")",
    re.IGNORECASE,
)
_ON_SEGMENT_RE = re.compile(
    r"(?:"
    r"на\s+(?:сторон[еы]|отрезке|луче|продолжении)\s+[A-Z]{2}\s+"
    r"(?:выбран|взят|отмечен|лежит|дан)\w*\s+точк\w+\s+([A-Z])"
    r"|точк\w+\s+([A-Z])\s+(?:лежит|взят|выбран|отмечен)\w*\s+"
    r"на\s+(?:сторон[еы]|отрезке|луче)"
    r"|([A-Z])\s*∈\s*[A-Z]{2}"
    r")",
    re.IGNORECASE,
)
_TOUCH_RE = re.compile(
    r"каса\w*\s+(?:\w+\s+){0,3}в\s+точке\s+([A-Z])",
    re.IGNORECASE,
)


def _extract_named(rx, text) -> Set[str]:
    """BUG-2: извлечь имена точек из capture-групп регекса.

    Каждая непустая группа разбивается на отдельные заглавные буквы, чтобы
    «A, B, C» и «ABC» давали одно и то же множество {A, B, C}.
    """
    out: Set[str] = set()
    for m in rx.finditer(text or ""):
        for g in m.groups():
            if not g:
                continue
            for ch in re.findall(r"[A-Z]", g):
                out.add(ch)
    return out


def check_missing_incidence(condition_text: str, base_plan: Any) -> List[str]:
    """CH26 FIX4 / BUG-2: детерминированная проверка MISSING_INCIDENCE.

    Проверяет ТОЛЬКО точки, которые по условию обязаны лежать на объекте
    (на окружности / стороне / отрезке / луче / вписанный многоугольник /
    касание в точке).  Обычные вершины (A, B, C) — законные free_point и
    не помечаются.  Если регекс сработал, но имя точки извлечь не удалось,
    это warning, а не error (нестандартная формулировка).
    """
    if not condition_text:
        return []
    from services.text_normalize import normalize_condition
    condition_text = normalize_condition(condition_text)
    base_cs = _base_constructions(base_plan)

    # Точки, объявленные в incidences.
    plan = _loads(base_plan)
    root = plan.get("base", plan) if isinstance(plan, dict) else plan
    incidences = root.get("incidences", []) if isinstance(root, dict) else []
    incidence_points = {i.get("point") for i in incidences if isinstance(i, dict)}

    # Множество точек, созданных инцидентными операциями (они уже корректны).
    incidence_op_points: Set[str] = set()
    for c in base_cs:
        if c.get("type") == "inscribed_polygon":
            for v in c.get("vertices", []) or []:
                if isinstance(v, str):
                    incidence_op_points.add(v)
        elif c.get("type") == "point_on_circle":
            incidence_op_points.add(c.get("id"))
        elif c.get("type") == "point_on_segment":
            incidence_op_points.add(c.get("id"))
        elif c.get("type") == "circle_three_points":
            for f in ("p1", "p2", "p3"):
                if c.get(f):
                    incidence_op_points.add(c[f])

    # Центры окружностей — законные free_point.
    center_ids = {
        c.get("center") for c in base_cs
        if c.get("type") in ("circle_center_radius", "circumcircle", "incircle")
        and c.get("center")
    }

    # Точки, созданные операциями пересечения (тоже законно инцидентны).
    intersection_types = {"intersect_lines", "intersect_line_circle",
                          "intersect_circles", "foot_perpendicular"}
    intersection_points = {
        c.get("id") for c in base_cs
        if c.get("type") in intersection_types and c.get("id")
    }

    errors: List[str] = []
    warnings: List[str] = []

    def _free_points() -> List[dict]:
        return [c for c in base_cs if c.get("type") == "free_point" and c.get("id")]

    # 1. «Вписан в окружность» / «вписанный многоугольник».
    if _INSCRIBED_RE.search(condition_text):
        for c in _free_points():
            cid = c.get("id")
            if cid in incidence_op_points or cid in incidence_points \
                    or cid in center_ids or cid in intersection_points:
                continue
            errors.append(
                f"MISSING_INCIDENCE: многоугольник вписан в окружность, но вершина "
                f"'{cid}' создана как free_point и не лежит на окружности. "
                f"Используй операцию inscribed_polygon со vertices или point_on_circle для '{cid}'."
            )

    # 2. «лежит на окружности» / «на одной окружности».
    on_circle_named = _extract_named(_ON_CIRCLE_RE, condition_text)
    if _ON_CIRCLE_RE.search(condition_text):
        if not on_circle_named:
            warnings.append(
                "MISSING_INCIDENCE: условие содержит «лежит на окружности», "
                "но имя точки не распознано — проверь инцидентность вручную."
            )
        for c in _free_points():
            cid = c.get("id")
            if cid not in on_circle_named:
                continue
            if cid in incidence_op_points or cid in incidence_points \
                    or cid in center_ids or cid in intersection_points:
                continue
            errors.append(
                f"MISSING_INCIDENCE: точка '{cid}' по условию лежит на окружности, "
                f"но создана как free_point. Используй point_on_circle или incidences."
            )

    # 3. «на стороне / на отрезке / на луче».
    on_segment_named = _extract_named(_ON_SEGMENT_RE, condition_text)
    if _ON_SEGMENT_RE.search(condition_text):
        if not on_segment_named:
            warnings.append(
                "MISSING_INCIDENCE: условие содержит «на стороне/отрезке/луче», "
                "но имя точки не распознано — проверь инцидентность вручную."
            )
        for c in _free_points():
            cid = c.get("id")
            if cid not in on_segment_named:
                continue
            if cid in incidence_op_points or cid in incidence_points \
                    or cid in center_ids or cid in intersection_points:
                continue
            errors.append(
                f"MISSING_INCIDENCE: точка '{cid}' по условию лежит на стороне/"
                f"отрезке/луче, но создана как free_point. Используй point_on_segment."
            )

    # 4. Касание в точке.
    touch_named = _extract_named(_TOUCH_RE, condition_text)
    if touch_named:
        for c in _free_points():
            cid = c.get("id")
            if cid not in touch_named:
                continue
            if cid in incidence_op_points or cid in incidence_points:
                continue
            errors.append(
                f"MISSING_INCIDENCE: точка '{cid}' — точка касания по условию, "
                f"но создана как free_point. Используй инцидентную операцию."
            )

    return errors + warnings


def validate_condition_solution(base_plan: Any, aux_plan: Any,
                                condition_text: Optional[str] = None) -> Dict[str, Any]:
    """Проверить инварианты base ↔ aux.

    Аргументы:
        base_plan: dict или JSON-строка base-плана.
        aux_plan:  dict или JSON-строка aux-плана (diff).

    Возвращает {"valid": bool, "errors": [str, ...], "warnings": [str, ...]}.
    Валидация остаётся обратно совместимой: существующие проверки не меняют
    поведение (valid/errors), а новые CH15.1 проверки добавляются как
    warnings (repair feedback), чтобы не ломать текущие тесты.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if condition_text:
        from services.text_normalize import normalize_condition
        condition_text = normalize_condition(condition_text)

    base = _loads(base_plan)
    aux = _loads(aux_plan)

    base_cs = _base_constructions(base)
    aux_obj = _aux_plan(aux) if isinstance(aux, dict) else {}

    has_aux = aux_obj.get("has_aux", False) if aux_obj else False
    aux_cs = _constructions_of(aux_obj)

    # ── 1. В base не должно быть aux-стиля и пунктира ──
    for i, c in enumerate(base_cs):
        cid = c.get("id", f"#{i}")
        style = c.get("style")
        dashed = c.get("dashed")
        if style == "aux":
            errors.append(
                f"BASE_LEAK: base object '{cid}' has style='aux'"
            )
        if dashed is True:
            errors.append(
                f"BASE_LEAK: base object '{cid}' has dashed=true"
            )

    base_ids = _declared_ids(base_cs)

    # ── 0. CH21 FIX 2: все точки из условия должны быть в base ──
    if condition_text:
        warnings.extend(check_condition_points(condition_text, base))
        # CH26 FIX4: пропущенные инцидентности — блокирующая ошибка.
        errors.extend(check_missing_incidence(condition_text, base))

    # ── 1a. CH19: служебные имена в подписях (base и aux) ──
    errors.extend(validate_label_texts(base_cs))
    errors.extend(validate_label_texts(aux_cs))

    # ── 1c. CH21 FIX 4: вырожденные segment/line между совпадающими точками ──
    for i, c in enumerate(base_cs + aux_cs):
        ctype = c.get("type")
        if ctype not in ("segment", "line", "ray"):
            continue
        p1 = c.get("p1")
        p2 = c.get("p2")
        if p1 and p2 and p1 == p2:
            errors.append(
                f"DEGENERATE_SEGMENT: объект '{c.get('id')}' ({ctype}) соединяет "
                f"точку '{p1}' саму с собой — прямая не определена"
            )

    # ── 1b. CH15.1: given_marks — валидация ссылок и warnings ──
    given_marks = _given_marks_of(base)
    _validate_given_marks(given_marks, base_ids, errors, warnings,
                          condition_text=condition_text)

    # ── 2. Если has_aux=false, то constructions должны быть пусты ──
    if not has_aux and aux_cs:
        errors.append(
            "INCONSISTENT_AUX: has_aux=false but constructions is non-empty"
        )
    if has_aux and not aux_cs:
        errors.append(
            "INCONSISTENT_AUX: has_aux=true but constructions is empty"
        )

    # ── 3. Проверка каждого aux-объекта ──
    seen_aux_ids: Set[str] = set()
    # available = base ids + ранее созданные aux ids
    available: Set[str] = set(base_ids)

    for i, c in enumerate(aux_cs):
        prefix = f"aux[{i}]"
        cid = c.get("id")
        if not isinstance(cid, str) or not cid:
            errors.append(f"{prefix}: missing 'id'")
            continue

        # Не переопределять base-сущность.
        if cid in base_ids:
            errors.append(
                f"BASE_OVERRIDE: aux object '{cid}' redefines a base id"
            )

        # Не дублировать внутри aux.
        if cid in seen_aux_ids:
            errors.append(f"{prefix}: duplicate id '{cid}'")
        seen_aux_ids.add(cid)

        # CH15.1: altitude/median/angle_bisector создают новую точку-результат
        # (foot_id) и обязаны её выдавать, чтобы следующие операции могли на
        # неё ссылаться.  Отсутствие foot_id — repair feedback (warning), чтобы
        # не ломать обратную совместимость с legacy aux-планами.
        # BUG-3: altitude ∈ _POINT_CREATING_TYPES, поэтому отдельная ветка
        # `elif ... altitude` была недостижима (мёртвый код удалён).
        # BUG-5: foot_id регистрируется в `available` ТОЛЬКО если валиден и
        # прошёл проверки на конфликт (раньше безусловный add маскировал каскад).
        ctype = c.get("type") or ""
        raw_foot_id = c.get("foot_id")
        registered_foot_id: Optional[str] = None
        if ctype in _POINT_CREATING_TYPES:
            if not raw_foot_id:
                warnings.append(
                    f"MISSING_FOOT_ID: {prefix} '{cid}' ({ctype}) должен "
                    f"выдавать id создаваемой точки (foot_id), например foot_id=\"H\""
                )
            elif not isinstance(raw_foot_id, str) or not raw_foot_id:
                errors.append(f"{prefix}: foot_id must be a non-empty string")
            elif raw_foot_id in base_ids:
                errors.append(
                    f"FOOT_ID_CONFLICT: aux {ctype} '{cid}' foot_id '{raw_foot_id}' "
                    f"conflicts with a base id"
                )
            elif raw_foot_id in available:
                errors.append(
                    f"FOOT_ID_CONFLICT: aux {ctype} '{cid}' foot_id '{raw_foot_id}' "
                    f"already exists"
                )
            else:
                registered_foot_id = raw_foot_id

        # Ссылки должны существовать в base или быть созданы ранее в aux.
        for ref in _referenced_ids(c):
            if ref not in available and ref != cid:
                errors.append(
                    f"INVALID_REFERENCE: {prefix} references unknown id '{ref}'"
                )

        # Обязательные атрибуты aux-объекта.
        if c.get("style") != "aux":
            errors.append(f"STYLE: {prefix} '{cid}' missing style='aux'")

        # CH15.1: dashed=true обязателен ТОЛЬКО для auxiliary geometry
        # (segment/line/ray/altitude/median/angle_bisector и окружностей).
        # Для auxiliary visual marks (right_angle_mark, angle_label,
        # equal_segments_mark, midpoint_mark, point_label и прочих не-geometry
        # типов) dashed не обязателен.
        ctype = c.get("type") or ""
        if _requires_dashed(ctype) and c.get("dashed") is not True:
            errors.append(f"STYLE: {prefix} '{cid}' must have dashed=true")

        purpose = (c.get("purpose") or "").strip()
        if not purpose:
            errors.append(f"MISSING_AUX_META: {prefix} '{cid}' missing purpose")

        evidence = c.get("solution_evidence")
        quote = ""
        if not isinstance(evidence, dict):
            errors.append(
                f"MISSING_AUX_META: {prefix} '{cid}' missing solution_evidence"
            )
        else:
            quote = (evidence.get("quote") or "").strip()
            if not quote:
                errors.append(
                    f"MISSING_AUX_META: {prefix} '{cid}' missing "
                    f"solution_evidence.quote"
                )
            step_no = evidence.get("step_no")
            if step_no is not None and (not isinstance(step_no, int) or step_no < 1):
                errors.append(
                    f"MISSING_AUX_META: {prefix} '{cid}' step_no must be int >= 1"
                )

        # CH15.1: минимальность — подозрительно короткая цитата без явного
        # действия (эвристика, не фатально).
        if quote and len(quote) < 4:
            warnings.append(
                f"UNNECESSARY_AUX_CONSTRUCTION: {prefix} '{cid}' has a very "
                f"short evidence quote, verify it is explicitly required by "
                f"the solution"
            )

        # CH15.1: segment/line/ray в aux допустимы только при явном действии
        # построения в цитате («проведём», «соединим», «продлим», «построим»,
        # «опустим», «проведена», «обозначим точку ...»).  Доказательная фраза
        # вида «MC является радиусом» НЕ разрешает строить отрезок MC.
        if ctype in _SEGMENT_LIKE_TYPES and not _has_construction_action(quote):
            warnings.append(
                f"AUX_SEGMENT_WITHOUT_CONSTRUCTION_ACTION: {prefix} '{cid}' "
                f"({ctype}) must have an explicit construction action in "
                f"solution_evidence.quote"
            )

        # CH16: визуальная роль — ограниченный enum, не произвольные цвета.
        visual_role = c.get("visual_role")
        if visual_role is not None:
            if visual_role not in _VALID_VISUAL_ROLES:
                errors.append(
                    f"INVALID_VISUAL_ROLE: {prefix} '{cid}' has unknown "
                    f"visual_role '{visual_role}'"
                )
        for f in _COLOR_FIELDS:
            if f in c:
                errors.append(
                    f"DIRECT_COLOR_FORBIDDEN: {prefix} '{cid}' must not set "
                    f"raw color field '{f}' — use visual_role"
                )

        # После проверки ссылок — id становится доступным для следующих aux.
        available.add(cid)
        # BUG-5: регистрируем только валидный foot_id (см. выше).
        if registered_foot_id:
            available.add(registered_foot_id)

    result: Dict[str, Any] = {"valid": len(errors) == 0}
    if errors:
        result["errors"] = errors
    if warnings:
        result["warnings"] = warnings
    return result


def _given_marks_of(base: Any) -> List[dict]:
    """Извлечь given_marks из base-плана (v2-структура или flat)."""
    if not isinstance(base, dict):
        return []
    if "base" in base and isinstance(base["base"], dict):
        root = base["base"]
    else:
        root = base
    marks = root.get("given_marks")
    if isinstance(marks, list):
        return [m for m in marks if isinstance(m, dict)]
    return []


def _requires_dashed(ctype: str) -> bool:
    """True для auxiliary geometry, которой ОБЯЗАТЕЛЕН dashed=true.

    CH15.1: dashed=true требуется только для настоящей вспомогательной
    геометрии (отрезки/прямые/лучи/высоты/медианы/биссектрисы и окружности).
    Визуальные метки (right_angle_mark, angle_label, equal_segments_mark,
    midpoint_mark, point_label и пр.) не требуют dashed.
    """
    return ctype in {
        "segment", "line", "ray", "altitude", "median", "angle_bisector",
        "perpendicular_bisector", "tangent_from_point", "tangent_at_point",
        "line_extension",
        "circle_center_radius", "circumcircle", "incircle",
        "circle_three_points",
    }


def _validate_given_marks(given_marks: List[dict], base_ids: Set[str],
                          errors: List[str], warnings: List[str],
                          condition_text: Optional[str] = None) -> None:
    """Проверить given_marks: ссылки должны существовать; наличие ключевых
    меток даёт MISSING_GIVEN_* warnings (repair feedback, не fatal).

    BUG-1: MISSING_GIVEN_* warnings выдаются ТОЛЬКО если условие реально
    требует соответствующую метку (равенство/угол/прямой угол/середину).
    Без condition_text догадок нет — хвостовой блок пропускается.
    """
    if condition_text:
        from services.text_normalize import normalize_condition
        condition_text = normalize_condition(condition_text)
    valid_mark_types = {
        "equal_segments_mark", "angle_label", "right_angle_mark",
        "midpoint_mark", "parallel_mark", "perpendicular_mark",
    }

    mark_ref_fields = ("vertex", "ray1", "ray2", "point", "p1", "p2", "p3")

    present_types: Set[str] = set()
    for i, m in enumerate(given_marks):
        mtype = m.get("type")
        if not isinstance(mtype, str) or not mtype:
            errors.append(f"given_marks[{i}]: missing 'type'")
            continue
        if mtype not in valid_mark_types:
            warnings.append(
                f"GIVEN_MARK_UNKNOWN: given_marks[{i}] has unknown type '{mtype}'"
            )
        else:
            present_types.add(mtype)

        # Ссылочные поля.
        for f in mark_ref_fields:
            val = m.get(f)
            if isinstance(val, str) and val and val not in base_ids:
                errors.append(
                    f"GIVEN_MARK_INVALID_REF: given_marks[{i}] '{f}'='{val}' "
                    f"references unknown id"
                )
        # segments: список пар ["A","B"] или плоский список.
        segs = m.get("segments")
        if isinstance(segs, list):
            for item in segs:
                if isinstance(item, str):
                    if item and item not in base_ids:
                        errors.append(
                            f"GIVEN_MARK_INVALID_REF: given_marks[{i}] segment "
                            f"references unknown id '{item}'"
                        )
                elif isinstance(item, (list, tuple)):
                    for pid in item:
                        if isinstance(pid, str) and pid and pid not in base_ids:
                            errors.append(
                                f"GIVEN_MARK_INVALID_REF: given_marks[{i}] segment "
                                f"references unknown id '{pid}'"
                            )

    # BUG-1: Warnings только при явном триггере в условии.  Без текста условия
    # догадок нет — выходим сразу, не шумя ложными MISSING_GIVEN_*.
    if not condition_text:
        return
    if _EQUALITY_TRIGGER_RE.search(condition_text) \
            and "equal_segments_mark" not in present_types:
        warnings.append("MISSING_GIVEN_EQUALITY_MARK: условие содержит "
                        "равенство отрезков, но equal_segments_mark отсутствует")
    if _ANGLE_TRIGGER_RE.search(condition_text) \
            and "angle_label" not in present_types:
        warnings.append("MISSING_GIVEN_ANGLE_LABEL: условие содержит угол "
                        "с величиной, но angle_label отсутствует")
    if _RIGHT_ANGLE_TRIGGER_RE.search(condition_text) \
            and "right_angle_mark" not in present_types:
        warnings.append("MISSING_GIVEN_RIGHT_ANGLE_MARK: условие содержит "
                        "прямой угол, но right_angle_mark отсутствует")
    if _MIDPOINT_TRIGGER_RE.search(condition_text) \
            and "midpoint_mark" not in present_types:
        warnings.append("MISSING_GIVEN_MIDPOINT_MARK: условие содержит "
                        "середину, но midpoint_mark отсутствует")


def merge_base_aux(base_plan: Any, aux_plan: Any) -> Dict[str, Any]:
    """Объединить base + aux в единое описание для GeometricEngine.

    Возвращает dict с полями canvas/constructions, пригодный для
    GeometricEngine.build_with_retry().  Базовые построения остаются
    неизменными; aux-построения дописываются в конец.
    """
    base = _loads(base_plan)
    aux = _loads(aux_plan)

    base_cs = _base_constructions(base)
    aux_obj = _aux_plan(aux) if isinstance(aux, dict) else {}
    aux_cs = _constructions_of(aux_obj)

    canvas: Dict[str, Any] = {}
    if isinstance(base, dict):
        b = base.get("base", base)
        if isinstance(b, dict) and isinstance(b.get("canvas"), dict):
            canvas = dict(b["canvas"])

    return {
        "canvas": canvas,
        "constructions": list(base_cs) + list(aux_cs),
    }
