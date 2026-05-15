# -*- coding: utf-8 -*-
"""
LLM-driven geometry spec builder.

Goal
----
Given a Russian text of an olympiad geometry problem, produce a strict JSON
spec describing the basic figure (vertices + their coordinates, segments,
angles, equal marks) so that services.geometry_renderer can draw it.

We deliberately ask the LLM ONLY for:
  * vertex names (single Latin caps)
  * what segments to draw
  * which lengths / angles are GIVEN in the problem and must be labelled
  * which equal-segment / right-angle marks are stated in the problem

…and we compute the coordinates ourselves whenever the figure is constrained
enough (triangle by SSS / SAS / ASA, simple polygons, etc.). The LLM may
also propose coordinates as a fallback (it is told it CAN, but we will
recompute them deterministically if it gives us enough data).

Schema (returned by LLM)
------------------------
{
  "figure_type": "triangle" | "quadrilateral" | "polygon" | "other",
  "vertices": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
  "given": {
    "sides": [{"from":"A","to":"B","length":5},
              {"from":"A","to":"C","length":7}],
    "angles": [{"at":"A","from":"B","to":"C","degrees":60}],
    "right_angles": [{"at":"B","from":"A","to":"C"}],
    "equal_segments": [{"segments":[["A","M"],["M","B"]], "ticks":1}],
    "equal_angles":   [{"angles":[{"at":"A","from":"B","to":"C"},
                                  {"at":"B","from":"A","to":"C"}], "arcs":2}]
  },
  "segments_to_draw": [["A","B"], ["A","C"], ["B","C"]]
}

The deterministic post-processor turns this into the renderer spec
(see services.geometry_renderer.render_spec_to_png).
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Dict, List, Optional, Tuple

from services.openrouter_client import openrouter, OpenRouterError

logger = logging.getLogger(__name__)


# ── Models ────────────────────────────────────────────────────────────────────
# JSON-mode-friendly, cheap, strong at structured math reasoning.
SPEC_MODEL = "anthropic/claude-sonnet-4.5"
SPEC_MODEL_FALLBACK = "deepseek/deepseek-chat"


SYSTEM_PROMPT = """\
Ты — парсер условий геометрических задач. Твоя ЕДИНСТВЕННАЯ задача — извлечь
из русскоязычного условия структурированное описание базового чертежа в
формате JSON. Никаких рассуждений, никакого текста вне JSON.

ПРАВИЛА ИМЕНОВАНИЯ
- Имена вершин — ТОЛЬКО одиночные заглавные латинские буквы: A, B, C, D, …
- Двухбуквенные сочетания (AB, BC) — это ОТРЕЗКИ, а не вершины.

ВКЛЮЧАЙ В JSON ТОЛЬКО ТО, ЧТО ЯВНО ЕСТЬ В УСЛОВИИ
- Не добавляй высот, биссектрис, дополнительных точек, если они не упомянуты.
- Подписи длин — только те числа, что даны.
- Подписи углов — только те, что даны.
- Отметки равенства (штрихи, двойные дуги) — только если в условии прямо
  сказано «равные», «равнобедренный», «равносторонний» и т.п.

СХЕМА ВЫХОДА (строгий JSON, никакого Markdown)
{
  "figure_type": "triangle"|"quadrilateral"|"polygon"|"other",
  "vertices": [{"name":"A"}, ...],
  "given": {
    "sides":          [{"from":"A","to":"B","length":<число>}],
    "angles":         [{"at":"A","from":"B","to":"C","degrees":<число>}],
    "right_angles":   [{"at":"B","from":"A","to":"C"}],
    "equal_segments": [{"segments":[["A","M"],["M","B"]], "ticks":1}],
    "equal_angles":   [{"angles":[{"at":"A","from":"B","to":"C"}], "arcs":1}]
  },
  "segments_to_draw": [["A","B"], ["A","C"], ["B","C"]]
}

Поля, для которых нет данных, оставляй пустыми массивами.
В "segments_to_draw" перечисли ВСЕ стороны и отрезки, которые надо нарисовать
(для треугольника ABC — три стороны; если упомянута медиана AM, то ещё ["A","M"];
и так далее).

Верни ТОЛЬКО JSON, начиная с { и заканчивая }.
"""


class GeometryParseError(Exception):
    pass


def parse_problem_to_spec(problem_text: str) -> dict:
    """
    Ask LLM to extract the structured spec. Returns the raw spec dict.

    Raises GeometryParseError if no valid JSON is returned by either model.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": problem_text.strip()},
    ]

    last_err: Optional[str] = None
    for model in (SPEC_MODEL, SPEC_MODEL_FALLBACK):
        try:
            result = openrouter.chat(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
        except OpenRouterError as e:
            last_err = f"{model}: {e}"
            logger.warning(f"[geometry_spec] {model} failed: {e}")
            continue
        except Exception as e:  # pragma: no cover
            last_err = f"{model}: {e}"
            logger.exception(f"[geometry_spec] {model} unexpected")
            continue

        content = (result.get("content") or "").strip()
        spec = _try_extract_json(content)
        if spec is not None:
            spec["_meta"] = {
                "model": model,
                "cost_usd": result.get("cost_usd", 0.0),
                "usage": result.get("usage", {}),
            }
            return spec
        last_err = f"{model}: invalid JSON: {content[:200]}"
        logger.warning(f"[geometry_spec] {model}: could not parse JSON")

    raise GeometryParseError(last_err or "no LLM returned valid JSON")


def _try_extract_json(text: str) -> Optional[dict]:
    """Be lenient: strip ```json fences, extract first {...} block."""
    if not text:
        return None
    # Strip code fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text.strip())
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # Find first {...} balanced block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    return None


# ─── Deterministic coordinate solver ──────────────────────────────────────────

def build_render_spec(parsed: dict) -> dict:
    """
    Turn the LLM-parsed spec into the concrete renderer spec (with coords).

    Strategy
    --------
    1. Build a graph of given sides (lengths) and given angles (degrees).
    2. Place vertices greedily:
       - First vertex → origin.
       - Second vertex → along +X axis at distance = side length.
       - Subsequent vertices → trilateration / SAS using known constraints.
       - If a vertex cannot be placed deterministically, fall back to a
         regular polygon layout for the remaining unknowns.
    3. Emit segments / labels / arcs ready for matplotlib.
    """
    given = parsed.get("given") or {}
    sides: List[dict] = given.get("sides") or []
    angles: List[dict] = given.get("angles") or []
    right_angles_in: List[dict] = given.get("right_angles") or []
    equal_segments_in: List[dict] = given.get("equal_segments") or []
    equal_angles_in: List[dict] = given.get("equal_angles") or []
    segments_to_draw: List[list] = parsed.get("segments_to_draw") or []

    vertex_names: List[str] = []
    for v in parsed.get("vertices") or []:
        name = (v or {}).get("name")
        if isinstance(name, str) and len(name) == 1 and name.isalpha():
            if name not in vertex_names:
                vertex_names.append(name)

    if not vertex_names:
        # Try to harvest from segments_to_draw
        for seg in segments_to_draw:
            if isinstance(seg, (list, tuple)) and len(seg) == 2:
                for n in seg:
                    if isinstance(n, str) and len(n) == 1 and n.isalpha() \
                            and n not in vertex_names:
                        vertex_names.append(n)

    if not vertex_names:
        raise GeometryParseError("no vertices found in parsed spec")

    # ── Build adjacency: side lengths ──────────────────────────────────────
    length: Dict[Tuple[str, str], float] = {}
    for s in sides:
        a, b = s.get("from"), s.get("to")
        try:
            L = float(s["length"])
        except (KeyError, TypeError, ValueError):
            continue
        if a and b and L > 0:
            length[(a, b)] = L
            length[(b, a)] = L

    angle_at: Dict[Tuple[str, str, str], float] = {}
    for a in angles:
        v, p1, p2 = a.get("at"), a.get("from"), a.get("to")
        try:
            deg = float(a["degrees"])
        except (KeyError, TypeError, ValueError):
            continue
        if v and p1 and p2:
            angle_at[(v, p1, p2)] = deg
            angle_at[(v, p2, p1)] = deg

    # Treat right angles as 90° entries
    for ra in right_angles_in:
        v, p1, p2 = ra.get("at"), ra.get("from"), ra.get("to")
        if v and p1 and p2:
            angle_at[(v, p1, p2)] = 90.0
            angle_at[(v, p2, p1)] = 90.0

    # ── Place vertices ─────────────────────────────────────────────────────
    pos: Dict[str, Tuple[float, float]] = {}

    placed_order = _place_vertices(vertex_names, length, angle_at, pos)

    # ── Compose render-spec ────────────────────────────────────────────────
    render_vertices = [{"name": n, "x": pos[n][0], "y": pos[n][1]}
                       for n in placed_order]

    # Build the set of segments to actually draw
    seg_set: List[Tuple[str, str]] = []
    seen = set()

    def _add_seg(a, b, label=None):
        if a == b or a not in pos or b not in pos:
            return
        key = tuple(sorted((a, b)))
        if key in seen:
            # Update label if missing
            for s in seg_set_dicts:
                if tuple(sorted((s["from"], s["to"]))) == key and label and not s.get("label"):
                    s["label"] = label
            return
        seen.add(key)
        seg_set.append((a, b))

    seg_set_dicts: List[dict] = []
    # First: explicit segments_to_draw
    for ref in segments_to_draw:
        if isinstance(ref, (list, tuple)) and len(ref) == 2:
            a, b = ref
            if a in pos and b in pos:
                key = tuple(sorted((a, b)))
                if key not in seen:
                    seen.add(key)
                    seg_set_dicts.append({"from": a, "to": b})

    # Then: every "given" side must be drawn even if LLM forgot it
    for (a, b), L in list(length.items()):
        if a > b:
            continue
        if a in pos and b in pos:
            key = tuple(sorted((a, b)))
            if key not in seen:
                seen.add(key)
                seg_set_dicts.append({"from": a, "to": b})

    # Apply length labels
    for seg in seg_set_dicts:
        L = length.get((seg["from"], seg["to"]))
        if L is not None:
            seg["label"] = _fmt_num(L)

    # Angle arcs (only the GIVEN ones, not the auto-fill 90° equivalents)
    render_angles = []
    seen_ang = set()
    for a in angles:
        v, p1, p2 = a.get("at"), a.get("from"), a.get("to")
        try:
            deg = float(a["degrees"])
        except Exception:
            continue
        if v in pos and p1 in pos and p2 in pos:
            k = (v, tuple(sorted((p1, p2))))
            if k in seen_ang:
                continue
            seen_ang.add(k)
            render_angles.append({
                "at": v, "from": p1, "to": p2,
                "label": f"{_fmt_num(deg)}°",
            })

    # Right-angle squares
    render_right = []
    for ra in right_angles_in:
        v, p1, p2 = ra.get("at"), ra.get("from"), ra.get("to")
        if v in pos and p1 in pos and p2 in pos:
            render_right.append({"at": v, "from": p1, "to": p2})

    # Equal-segment ticks (validate references)
    render_eq_seg = []
    for grp in equal_segments_in:
        seg_refs = []
        for ref in grp.get("segments") or []:
            if isinstance(ref, (list, tuple)) and len(ref) == 2:
                a, b = ref
                if a in pos and b in pos:
                    seg_refs.append([a, b])
        if seg_refs:
            render_eq_seg.append({
                "segments": seg_refs,
                "ticks": int(grp.get("ticks", 1) or 1),
            })

    # Equal-angle arcs (validate references)
    render_eq_ang = []
    for grp in equal_angles_in:
        ang_refs = []
        for a in grp.get("angles") or []:
            v, p1, p2 = a.get("at"), a.get("from"), a.get("to")
            if v in pos and p1 in pos and p2 in pos:
                ang_refs.append({"at": v, "from": p1, "to": p2})
        if ang_refs:
            render_eq_ang.append({
                "angles": ang_refs,
                "arcs": int(grp.get("arcs", 1) or 1),
            })

    return {
        "vertices": render_vertices,
        "segments": seg_set_dicts,
        "angles": render_angles,
        "right_angles": render_right,
        "equal_segments": render_eq_seg,
        "equal_angles": render_eq_ang,
        "circles": [],
        "_meta": parsed.get("_meta", {}),
    }


def _fmt_num(x: float) -> str:
    if abs(x - round(x)) < 1e-6:
        return str(int(round(x)))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def _try_place_triangle_sas(
    names: List[str],
    length: Dict[Tuple[str, str], float],
    angle_at: Dict[Tuple[str, str, str], float],
    pos: Dict[str, Tuple[float, float]],
) -> Optional[List[str]]:
    """
    Canonical SAS fast-path for triangles.

    Layout (apex always points up so labels read naturally):
        V  = (0, 0)                                    # vertex of given angle
        P1 = (|V P1|, 0)                               # on positive X axis
        P2 = (|V P2| * cos(alpha), |V P2| * sin(alpha))

    Returns the placement order, or None if the case doesn't match.
    """
    if len(names) != 3:
        return None
    for v in names:
        others = [n for n in names if n != v]
        if len(others) != 2:
            continue
        p1, p2 = others
        L1 = length.get((v, p1))
        L2 = length.get((v, p2))
        if L1 is None or L2 is None:
            continue
        deg = angle_at.get((v, p1, p2))
        if deg is None:
            deg = angle_at.get((v, p2, p1))
        if deg is None:
            continue
        a = math.radians(float(deg))
        pos[v] = (0.0, 0.0)
        pos[p1] = (float(L1), 0.0)
        pos[p2] = (float(L2) * math.cos(a), float(L2) * math.sin(a))
        return [v, p1, p2]
    return None


def _place_vertices(
    names: List[str],
    length: Dict[Tuple[str, str], float],
    angle_at: Dict[Tuple[str, str, str], float],
    pos: Dict[str, Tuple[float, float]],
) -> List[str]:
    """
    Greedy placement.

    Tries to start from two vertices connected by a known segment, then
    place the rest using SAS (one neighbour + included angle) or trilateration
    (two neighbours with known distances).

    Falls back to a regular polygon layout for whatever cannot be placed.
    """
    if not names:
        return []

    # Fast path: classic SAS triangle (two sides + included angle).
    sas = _try_place_triangle_sas(names, length, angle_at, pos)
    if sas is not None:
        return sas

    placed: List[str] = []

    # Pick the first edge with a known length to anchor the figure
    anchor: Optional[Tuple[str, str]] = None
    for (a, b), L in length.items():
        if a < b and a in names and b in names:
            anchor = (a, b)
            break

    if anchor:
        a, b = anchor
        L = length[(a, b)]
        pos[a] = (0.0, 0.0)
        pos[b] = (L, 0.0)
        placed = [a, b]
    else:
        # No known lengths → put first vertex at origin, others on a unit circle
        pos[names[0]] = (0.0, 0.0)
        placed = [names[0]]

    remaining = [n for n in names if n not in placed]

    # Iteratively try to place
    progress = True
    while remaining and progress:
        progress = False
        for n in list(remaining):
            placed_xy = _try_place_vertex(n, placed, length, angle_at, pos)
            if placed_xy is not None:
                pos[n] = placed_xy
                placed.append(n)
                remaining.remove(n)
                progress = True

    # Anything left → place on a circle around the centroid of placed pts
    if remaining:
        cx = sum(pos[p][0] for p in placed) / max(len(placed), 1)
        cy = sum(pos[p][1] for p in placed) / max(len(placed), 1)
        radius = 1.0
        # Estimate a sensible radius from existing extents
        if placed:
            ext = max(
                max(abs(pos[p][0] - cx) for p in placed),
                max(abs(pos[p][1] - cy) for p in placed),
                1.0,
            )
            radius = ext * 1.2
        for i, n in enumerate(remaining):
            ang = 2 * math.pi * i / max(len(remaining), 1) + math.pi / 6
            pos[n] = (cx + radius * math.cos(ang), cy + radius * math.sin(ang))
            placed.append(n)
        remaining = []

    return placed


def _try_place_vertex(
    n: str,
    placed: List[str],
    length: Dict[Tuple[str, str], float],
    angle_at: Dict[Tuple[str, str, str], float],
    pos: Dict[str, Tuple[float, float]],
) -> Optional[Tuple[float, float]]:
    """
    Try multiple strategies in order:
      1. SAS: placed neighbour P with known length |PN| AND known angle at P
              between (some other placed Q) and N.
      2. Trilateration: two placed neighbours P, Q with known |PN|, |QN|.
      3. Single neighbour P with known |PN| but no angle → place along
         a default direction (45° from positive X) — best-effort fallback.
    """
    # 1) SAS
    for p in placed:
        Lpn = length.get((p, n))
        if Lpn is None:
            continue
        for q in placed:
            if q == p:
                continue
            deg = angle_at.get((p, q, n))
            if deg is None:
                continue
            # Direction from p to q
            dx = pos[q][0] - pos[p][0]
            dy = pos[q][1] - pos[p][1]
            base = math.atan2(dy, dx)
            # Rotate by ±angle; pick CCW first
            theta = math.radians(deg)
            # Choose sign that yields y >= placed centroid (keeps figure tidy)
            cand1 = (pos[p][0] + Lpn * math.cos(base + theta),
                     pos[p][1] + Lpn * math.sin(base + theta))
            cand2 = (pos[p][0] + Lpn * math.cos(base - theta),
                     pos[p][1] + Lpn * math.sin(base - theta))
            # Prefer the candidate that doesn't coincide with existing pts
            return _pick_better(cand1, cand2, pos)

    # 2) Trilateration
    neighbours = [(p, length.get((p, n))) for p in placed if length.get((p, n))]
    if len(neighbours) >= 2:
        (p1, r1), (p2, r2) = neighbours[0], neighbours[1]
        cand = _trilaterate(pos[p1], r1, pos[p2], r2)
        if cand:
            c1, c2 = cand
            return _pick_better(c1, c2, pos)

    # 3) Single neighbour fallback
    if neighbours:
        p, r = neighbours[0]
        return (pos[p][0] + r * math.cos(math.pi / 4),
                pos[p][1] + r * math.sin(math.pi / 4))

    return None


def _trilaterate(c1, r1, c2, r2) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Two intersection points of circles (c1,r1) and (c2,r2)."""
    x1, y1 = c1
    x2, y2 = c2
    d = math.hypot(x2 - x1, y2 - y1)
    if d < 1e-9 or d > r1 + r2 + 1e-6 or d < abs(r1 - r2) - 1e-6:
        return None
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h2 = max(r1 * r1 - a * a, 0.0)
    h = math.sqrt(h2)
    xm = x1 + a * (x2 - x1) / d
    ym = y1 + a * (y2 - y1) / d
    rx = -(y2 - y1) * (h / d)
    ry = (x2 - x1) * (h / d)
    return ((xm + rx, ym + ry), (xm - rx, ym - ry))


def _pick_better(c1, c2, pos):
    """Choose the candidate that lies above (y > average) for a nicer layout."""
    if not pos:
        return c1
    avg_y = sum(p[1] for p in pos.values()) / len(pos)
    return c1 if c1[1] >= avg_y else c2


# ─── Top-level convenience ────────────────────────────────────────────────────

def problem_text_to_render_spec(problem_text: str) -> dict:
    """One-shot: text → render-ready spec dict."""
    parsed = parse_problem_to_spec(problem_text)
    spec = build_render_spec(parsed)
    return spec
