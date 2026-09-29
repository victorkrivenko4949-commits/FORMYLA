"""Verified ratio marks and the standard parallel-line auxiliary construction.

Two things a figure for "BD : DC = 1 : 2" must show even when the model
returned a bare figure:

* the given ratios as marks x / 2x on the segments (checked against the
  solved coordinates, never taken on trust);
* in the auxiliary mode, for two cevians XD and YE with D and E on sides:
  the line through D parallel to YE up to the side of E (Thales / Menelaus
  step). Equalities of collinear segments produced by it are marked only
  after they are verified numerically; collinear equalities are affine
  invariants, so they hold for every triangle of the same kind.
"""
from __future__ import annotations

import copy
import re

import numpy as np

from .schema import Construction

_NAME = r"[A-Z](?:_?\d{1,2})?"
_NUM = r"\d+(?:[.,]\d+)?"
_ASKED = re.compile(r"найд|доказ|докаж|покаж|вычисл|определ|чему\s+равн|каково|каков", re.I)
_LETTERS = "xyzt"


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _given_ratios(text: str) -> list[tuple[list[tuple[str, str]], list[float]]]:
    """Chains 'XP : PY = a : b (: c)' from sentences that state data, not goals."""
    text = (text or "").replace("$", " ").replace("\\(", " ").replace("\\)", " ")
    out = []
    for sentence in re.split(r"(?<=[.;!?])\s+|\n+", text):
        if _ASKED.search(sentence):
            continue
        for m in re.finditer(
                rf"((?:{_NAME}{_NAME})(?:\s*[:/]\s*(?:{_NAME}{_NAME}))+)\s*=\s*"
                rf"({_NUM}(?:\s*[:/]\s*{_NUM})+)", sentence):
            segs = [re.fullmatch(rf"({_NAME})({_NAME})", p.strip())
                    for p in re.split(r"[:/]", m[1])]
            nums = [_num(x) for x in re.split(r"\s*[:/]\s*", m[2])]
            if all(segs) and len(segs) == len(nums) and min(nums) > 0 and len(nums) <= 3:
                out.append(([(s[1], s[2]) for s in segs], nums))
    return out


def _supported(plan, coords, a, b) -> bool:
    """[a, b] lies inside a drawn segment (either layer)."""
    for field in ("segments", "aux_segments"):
        for u, v in getattr(plan.draw, field):
            if u not in coords or v not in coords:
                continue
            A, B = np.asarray(coords[u], float), np.asarray(coords[v], float)
            d = B - A
            den = float(d @ d)
            if den < 1e-20:
                continue
            ok = True
            for name in (a, b):
                p = np.asarray(coords[name], float) - A
                t = float(p @ d) / den
                if abs(float(d[0] * p[1] - d[1] * p[0])) > 1e-7 * den or not -1e-7 <= t <= 1 + 1e-7:
                    ok = False
            if ok:
                return True
    return False


def _reduce(nums: list[float]) -> list[str]:
    scale = 1
    while scale < 1000 and any(abs(n * scale - round(n * scale)) > 1e-9 for n in nums):
        scale *= 10
    ints = [int(round(n * scale)) for n in nums]
    from math import gcd
    g = 0
    for i in ints:
        g = gcd(g, i)
    return [str(i // g) for i in ints]


def _coefficient(k: str, letter: str) -> str:
    return letter if k == "1" else f"{k}{letter}"


def add_ratio_marks(plan, coords: dict, text: str):
    """Return plan with verified x / 2x marks for the given ratios."""
    plan = copy.deepcopy(plan)
    d = plan.draw
    marked = {frozenset(m["pts"]) for m in d.length_marks} | \
             {frozenset(m["pts"]) for m in d.equal_marks}
    letters = iter(_LETTERS)
    for segs, nums in _given_ratios(text):
        if any(a not in coords or b not in coords or a == b for a, b in segs):
            continue
        lengths = [float(np.linalg.norm(np.asarray(coords[a], float) - np.asarray(coords[b], float)))
                   for a, b in segs]
        if min(lengths) < 1e-9:
            continue
        if any(abs(l / lengths[0] - n / nums[0]) > 1e-4 * max(n / nums[0], 1e-9)
               for l, n in zip(lengths[1:], nums[1:])):
            continue                               # the figure does not have this ratio: no mark
        if any(frozenset(s) in marked for s in segs) \
                or not all(_supported(plan, coords, a, b) for a, b in segs):
            continue
        letter = next(letters, None)
        if letter is None:
            break
        for (a, b), k in zip(segs, _reduce(nums)):
            d.length_marks.append({"pts": [a, b], "text": _coefficient(k, letter)})
            marked.add(frozenset((a, b)))
    return plan


def _on_side(plan, point: str):
    """(B, C) if point = divide_segment(B, C)."""
    for c in plan.constructions:
        if c.op == "divide_segment" and c.out == point:
            return tuple(c.args)
    return None


def _crossing_cevians(plan):
    """[(O, (X, D), (Y, E))] for O = line_intersect(X, D, Y, E), D and E on sides."""
    found = []
    for c in plan.constructions:
        if c.op != "line_intersect" or len(c.args) != 4:
            continue
        a, b, p, q = c.args
        for first, second in (((a, b), (p, q)), ((b, a), (q, p)), ((a, b), (q, p)),
                              ((b, a), (p, q))):
            x, dd = first
            y, e = second
            side_d, side_e = _on_side(plan, dd), _on_side(plan, e)
            if side_d and side_e and x not in side_d and y not in side_e \
                    and set(side_d) != set(side_e) and x != y:
                found.append((c.out, (x, dd), (y, e)))
                break
    return found


def _line_hit(P, Q, R, S):
    r, s = Q - P, S - R
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-12 * max(np.linalg.norm(r) * np.linalg.norm(s), 1e-12):
        return None
    t = ((R[0] - P[0]) * s[1] - (R[1] - P[1]) * s[0]) / den
    return P + t * r


def add_parallel_aux(plan, solution, text: str):
    """Thales step for crossing cevians. Returns (plan, coords) or the inputs."""
    d = plan.draw
    if d.aux_segments or d.aux_lines or d.aux_rays or d.aux_extensions or d.aux_circles:
        return plan, solution.coords                 # the model already built something
    coords = {k: np.asarray(v, float) for k, v in solution.coords.items()}
    for o, (x, dd), (y, e) in _crossing_cevians(plan):
        side_e = _on_side(plan, e)
        line_a, line_b = side_e
        if not all(n in coords for n in (x, dd, y, e, line_a, line_b)):
            continue
        shift = coords[dd] + (coords[e] - coords[y])         # D + (E - Y): direction of YE
        foot = _line_hit(coords[dd], shift, coords[line_a], coords[line_b])
        if foot is None:
            continue
        span = float(np.linalg.norm(coords[line_b] - coords[line_a]))
        t = float((foot - coords[line_a]) @ (coords[line_b] - coords[line_a])) / span ** 2
        if not -0.02 <= t <= 1.02 or float(np.linalg.norm(foot - coords[dd])) < 0.02 * span:
            continue
        name = next((n for n in "FGHKLMNPQ" if n not in coords and n not in plan.points), None)
        helper = next((f"{n}_p" for n in "PQ" if f"{n}_p" not in plan.points), None)
        if name is None or helper is None:
            continue
        plan = copy.deepcopy(plan)
        plan.points += [helper, name]
        plan.constructions += [
            Construction(op="parallel_point", out=helper, args=[dd, y, e], value=1.0),
            Construction(op="line_intersect", out=name, args=[dd, helper, line_a, line_b]),
        ]
        plan.draw.aux_points.append(name)
        plan.draw.hide_labels.append(helper)
        plan.draw.aux_segments.append([dd, name])
        coords = {**coords, helper: shift, name: foot}
        plan = _mark_collinear_equalities(plan, coords)
        return plan, coords
    return plan, coords


def _mark_collinear_equalities(plan, coords, names=None):
    """Tick equal neighbouring pieces of ONE line (verified, aux layer).

    Only pieces of the same line are compared: an equality of collinear
    segments follows from the ratios, while equal lengths in different
    directions would be an accident of the chosen triangle.
    """
    d = plan.draw
    used = {m.get("count", 1) for m in d.equal_marks}
    marked = {frozenset(m["pts"]) for m in d.equal_marks} | \
             {frozenset(m["pts"]) for m in d.length_marks}
    seen_lines = set()
    for u, v in [tuple(s) for f in ("segments", "aux_segments") for s in getattr(d, f)]:
        if u not in coords or v not in coords:
            continue
        A, B = np.asarray(coords[u], float), np.asarray(coords[v], float)
        dvec = B - A
        den = float(dvec @ dvec)
        if den < 1e-20:
            continue
        on = []
        for n in plan.points:
            if n not in coords or n in d.hide_labels:
                continue
            q = np.asarray(coords[n], float) - A
            t = float(q @ dvec) / den
            if abs(float(dvec[0] * q[1] - dvec[1] * q[0])) <= 1e-7 * den and -1e-7 <= t <= 1 + 1e-7:
                on.append((t, n))
        on.sort()
        key = tuple(n for _, n in on)
        if len(on) < 3 or key in seen_lines:
            continue
        seen_lines.add(key)
        pieces = [(p, q) for (_, p), (_, q) in zip(on, on[1:])]
        length = lambda pq: float(np.linalg.norm(np.asarray(coords[pq[0]], float)
                                                 - np.asarray(coords[pq[1]], float)))
        for mk in list(d.length_marks):
            if mk.get("layer") == "aux" or "text" not in mk:
                continue
            ref = tuple(mk["pts"])
            if ref[0] not in coords or ref[1] not in coords:
                continue
            for pq in pieces:
                if frozenset(pq) in marked or frozenset(pq) == frozenset(ref) \
                        or frozenset(ref) not in {frozenset(x) for x in pieces}:
                    continue
                if abs(length(pq) - length(ref)) <= 1e-6 * max(length(pq), length(ref), 1e-9):
                    d.length_marks.append({"pts": list(pq), "text": mk["text"], "layer": "aux"})
                    marked.add(frozenset(pq))
        groups: list[list[tuple[str, str]]] = []
        for pq in pieces:
            if length(pq) < 1e-9 or frozenset(pq) in marked:
                continue
            for g in groups:
                if abs(length(g[0]) - length(pq)) <= 1e-6 * max(length(g[0]), length(pq)):
                    g.append(pq)
                    break
            else:
                groups.append([pq])
        for g in groups:
            if len(g) < 2:
                continue
            count = next((n for n in (1, 2, 3) if n not in used), None)
            if count is None:
                return plan
            used.add(count)
            for pq in g:
                d.equal_marks.append({"pts": list(pq), "count": count, "layer": "aux"})
                marked.add(frozenset(pq))
    return plan
