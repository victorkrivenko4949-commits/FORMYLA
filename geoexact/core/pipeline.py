"""Конвейер GeoExact: 9 этапов от текста задачи до SVG.

1 нормализация+кэш · 2 классификация(LLM) · 3 маршрутизация · 4 формализация(LLM)
5 валидация схемы · 6 решение ограничений · 7 гейт корректности
8 гейт наглядности+ранжирование · 9 рендер+кэш

Этапы 2 и 4 — единственные с LLM. Остальные 7 детерминированы.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import time
import os
import tempfile
from dataclasses import dataclass, field

from .schema import FigurePlan, PlanError, validate_plan
from . import llm as L

CACHE = pathlib.Path(__file__).resolve().parent.parent / "cache"
CACHE.mkdir(exist_ok=True)
ENGINE_VERSION = "2.1"


@dataclass
class Result:
    ok: bool
    stage: str = ""                 # где остановились
    reason: str = ""                # код отказа
    detail: str = ""
    svg: str | None = None
    plan: dict | None = None
    measured: float | None = None   # величина, измеренная на чертеже
    cls: str = ""
    with_aux: bool = False
    cost: float = 0.0
    seconds: float = 0.0
    from_cache: bool = False
    retries: int = 0
    warnings: list[str] = field(default_factory=list)
    usage: list[dict] = field(default_factory=list)
    notes: str = ""
    svg_base: str | None = None
    svg_detail: str | None = None
    space: str = "plane"
    cost_uncertain: bool = False
    verification: str = "constraints_only"
    measurement_range: list[float] = field(default_factory=list)

    def brief(self) -> str:
        head = "OK " if self.ok else f"ОТКАЗ[{self.stage}:{self.reason}] "
        return f"{head}{self.cls}{'+aux' if self.with_aux else ''} ${self.cost:.5f} {self.seconds:.1f}с"


def _norm(text: str) -> str:
    """Этап 1: нормализация текста."""
    t = text.replace("\u00a0", " ").replace("−", "-").replace("×", "*")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _key(text: str, with_aux: bool) -> str:
    return hashlib.sha256(f"{ENGINE_VERSION}|{text}|{int(with_aux)}".encode()).hexdigest()[:20]


def generate(problem: str, with_aux: bool = False, *, sess=None, budget=None,
             use_cache: bool = True, n_seeds: int = 24, max_retries: int = 2) -> Result:
    from . import constructions  # noqa: F401  (регистрация операций)
    from .solver import solve
    from .gates import rank_solutions
    from .render import render_svg

    t_start = time.time()
    sess = sess or L.make_session()
    budget = budget or L.Budget()

    # ---------------------------------------------------------- этап 1
    if not isinstance(problem, str):
        return Result(False, "1-normalize", "INVALID_INPUT", "условие должно быть текстом")
    try:
        problem.encode("utf-8")
    except UnicodeEncodeError:
        return Result(False, "1-normalize", "INVALID_UNICODE", "условие содержит некорректный Unicode")
    text = _norm(problem)
    if len(text) > 12000:
        return Result(False, "1-normalize", "INPUT_TOO_LONG", "максимум 12 000 символов")
    if len(text) < 10:
        return Result(False, "1-normalize", "EMPTY_INPUT", "условие слишком короткое")
    ck = _key(text, with_aux)
    cf = CACHE / f"{ck}.json"
    if use_cache and cf.exists():
        try:
            d = json.loads(cf.read_text())
            return Result(**{**d, "from_cache": True, "cost": 0.0, "usage": [],
                             "seconds": time.time() - t_start})
        except (ValueError, TypeError):
            pass  # damaged cache is not a user-facing failure

    def finish(res: Result) -> Result:
        res.cost = round(budget.spent, 6)
        res.seconds = round(time.time() - t_start, 2)
        res.usage = [vars(u) for u in budget.calls]
        res.cost_uncertain = budget.uncertain
        if res.ok and use_cache:
            d = dict(vars(res)); d.pop("from_cache", None)
            fd, temp = tempfile.mkstemp(dir=CACHE, prefix=ck, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(d, f, ensure_ascii=False)
                os.replace(temp, cf)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        return res

    # A narrow, exactly specified theorem family needs no stochastic model
    # plan: the second intersection of the angle bisector with (ABC) is a
    # deterministic construction, not bisector_point (which lies on BC).
    from .semantics import theorem_plan, semantic_failures
    special_plan = theorem_plan(text, with_aux)
    if special_plan is None:
        # ------------------------------------------------------ этап 2
        try:
            c = L.classify(sess, text, budget)
        except PlanError as e:
            return finish(Result(False, "2-classify", e.code, str(e)))
    else:
        c = {"ok": True, "class": "M", "space": "plane"}
    if not c.get("ok", True):
        return finish(Result(False, "2-classify", "BAD_PROBLEM",
                             c.get("reason", "условие некорректно")))
    if c.get("space") == "space":
        from .space3d import build_scene
        last = None
        feedback = ""
        prev_code = ""
        for attempt in range(max_retries + 1):
            try:
                data = L.formalize_space(sess, text, c["class"], with_aux, budget, feedback, prev_code)
                scene = build_scene(data, show_aux=with_aux)
                base = build_scene(data, show_aux=False) if with_aux else scene
                return finish(Result(True, "9-render-3D", svg=scene["svg"],
                    svg_base=base["svg"], plan=data, measured=scene.get("measured"),
                    warnings=scene.get("warnings", []), notes=scene.get("notes", ""),
                    cls=c["class"], space="space", with_aux=with_aux, retries=attempt,
                    verification="parametric_3d"))
            except PlanError as e:
                last = Result(False, "6-space", e.code, str(e), cls=c["class"],
                              space="space", with_aux=with_aux, retries=attempt)
                feedback = str(e)
                prev_code = e.code
                if budget.uncertain or e.code in ("BUDGET_EXCEEDED", "API_ERROR", "NEEDS_CLARIFICATION"):
                    break
        return finish(last)
    cls = c.get("class", "M")

    # ---------------------------------------------------------- этапы 3-8
    feedback, last, prev_code = "", None, ""
    for attempt in range((0 if special_plan is not None else max_retries) + 1):
        # этап 3 маршрутизация + этап 4 формализация + этап 5 валидация
        try:
            if special_plan is not None:
                plan = special_plan
                warn = [w for w in validate_plan(plan)
                        if not w.startswith("UNDERDETERMINED:")]
            else:
                plan, warn = L.formalize(sess, text, cls, with_aux, budget, feedback, prev_code)
        except PlanError as e:
            last = Result(False, "4-formalize" if e.code not in
                          ("BUDGET_EXCEEDED",) else "3-route", e.code, str(e),
                          cls=cls, with_aux=with_aux, retries=attempt)
            feedback = str(e)
            prev_code = e.code
            if budget.uncertain or e.code in ("BUDGET_EXCEEDED", "API_ERROR"):
                break
            continue

        # этап 6 решение ограничений
        try:
            # Convert free points fixed by side+angle into exact ray/side
            # intersections first. This avoids slow, ill-conditioned
            # five-free-point solves; every candidate is checked against
            # ALL original constraints and the correctness/readability gates.
            from .repair import angle_side_variants
            variants = angle_side_variants(plan)
            sols = []
            for candidate in variants:
                candidate_sols = solve(candidate, n_seeds=min(n_seeds, 8), seed=0)
                candidate_good = [s for s in candidate_sols if s.ok]
                if candidate_good and rank_solutions(
                        candidate, candidate_good, strict_readability=False):
                    plan = candidate
                    warn = warn + validate_plan(plan)
                    sols = candidate_sols
                    break
            if not sols:
                sols = solve(plan, n_seeds=n_seeds, seed=0)
        except PlanError as e:
            last = Result(False, "6-solve", e.code, str(e), plan=plan.to_dict(),
                          cls=cls, with_aux=with_aux, retries=attempt)
            feedback = f"движок не построил фигуру — {e}"
            continue
        good = [s for s in sols if s.ok]
        if not good:
            why = sols[0].reason if sols else "NO_SOLUTION"
            last = Result(False, "6-solve", why,
                          "система ограничений не имеет допустимого решения",
                          plan=plan.to_dict(), cls=cls, with_aux=with_aux, retries=attempt)
            feedback = "не удалось удовлетворить ограничения"
            if sols and sols[0].coords:
                try:
                    from .solver import residuals
                    errors = residuals(plan, sols[0].coords)
                    failures = sorted(
                        ((abs(float(value)), c) for c, value in zip(plan.constraints, errors)),
                        key=lambda pair: pair[0], reverse=True,
                    )
                    significant = [
                        f"{c.type}({','.join(c.args)})={c.value}: невязка {error:.3g}"
                        for error, c in failures[:3] if error > 1e-7
                    ]
                    if significant:
                        feedback += ": " + "; ".join(significant)
                except (PlanError, ValueError, TypeError):
                    pass
            feedback += (". Проверь правильность угловых вершин и ветвей; "
                         "если точка на стороне определяется лучом из вершины, "
                         "используй angle_ray с 2 аргументами и line_intersect.")
            continue

        # The numeric gates validate the *plan*, not its fidelity to the
        # wording. For a named incenter/arc configuration, independently
        # reject a model's W on BC (or invented equality) before rendering.
        semantic_errors: list[str] = []
        faithful = []
        for s in good:
            failures = semantic_failures(text, plan, s.coords)
            if failures:
                semantic_errors.extend(failures)
            else:
                faithful.append(s)
        if not faithful:
            details = "; ".join(dict.fromkeys(semantic_errors))
            last = Result(False, "7-semantics", "SEMANTIC_MISMATCH",
                          details, plan=plan.to_dict(), cls=cls,
                          with_aux=with_aux, retries=attempt)
            feedback = ("План не соответствует исходному условию: " + details
                        + ". Используй bisector_circumcircle(W,[A,B,C]), "
                        "не bisector_point; не выдумывай длины сторон.")
            continue
        good = faithful

        # этапы 7-8 гейты и ранжирование
        ranked = rank_solutions(plan, good, strict_readability=False)
        if not ranked:
            # Отказ без причины бесполезен: собираем фактические нарушения
            # лучшей конфигурации — именно они скажут, что починить в плане.
            from .gates import gate_correctness
            why = []
            for s in good[:3]:
                g0 = gate_correctness(plan, s)
                why.extend(g0.failures)
            uniq: list[str] = []
            for w in why:
                if w not in uniq:
                    uniq.append(w)
            det = "; ".join(uniq[:6]) or "причина не определена"
            last = Result(False, "7-correctness", "GATE_CORRECTNESS", det,
                          plan=plan.to_dict(), cls=cls, with_aux=with_aux, retries=attempt)
            feedback = "построенная фигура не прошла проверку: " + det
            continue
        sol, gate = ranked[0]
        if special_plan is not None:
            gate.warnings = [w for w in gate.warnings
                             if not w.startswith(
                                 "UNDECLARED_INCIDENCE: I лежит на AW")]
        if not gate.ok:
            last = Result(False, "8-readability", "GATE_READABILITY",
                          "; ".join(gate.failures), plan=plan.to_dict(),
                          cls=cls, with_aux=with_aux, retries=attempt)
            feedback = "фигура получается вырожденной/нечитаемой: " + "; ".join(gate.failures)
            continue

        # ---------------------------------------------------------- этап 9
        from .completion import complete_intersection_support
        plan, completion_warn = complete_intersection_support(plan, sol)
        warn.extend(completion_warn)
        try:
            svg = render_svg(plan, sol, gate=gate, show_aux=with_aux)
            svg_base = render_svg(plan, sol, gate=gate, show_aux=False) if with_aux else svg
        except PlanError as e:
            last = Result(False, "9-render", e.code, str(e), cls=cls,
                          with_aux=with_aux, retries=attempt, plan=plan.to_dict())
            feedback = str(e)
            continue
        values = [g.measured for _, g in ranked if g.measured is not None]
        value_range = [min(values), max(values)] if values else []
        if values and max(values) - min(values) > 1e-5 * max(1.0, abs(min(values)), abs(max(values))):
            warn.append("AMBIGUOUS_MEASUREMENT: допустимые конфигурации дают разные значения; "
                        "чертёж иллюстративный, измеренное значение не является доказанным ответом")
        # Renderer collision notices must not live only inside hidden SVG comments.
        render_warn = re.findall(r"<!--\s*((?:LABEL_COLLISION|ANGLE_LABEL|MARK_COLLISION)[^\n]*?)\s*-->", svg)
        from .detail import detail_view
        svg_detail=detail_view(plan,sol,show_aux=with_aux)
        if svg_detail:
            warn.append("DETAIL_VIEW: исходная фигура мала на общем виде; приложен увеличенный фрагмент")
        return finish(Result(True, "9-render", "", "", svg=svg, plan=plan.to_dict(),
                             svg_base=svg_base, svg_detail=svg_detail, measurement_range=value_range,
                             measured=gate.measured, cls=cls, with_aux=with_aux,
                             retries=attempt, warnings=warn + gate.warnings + render_warn,
                             notes=plan.notes))

    return finish(last or Result(False, "4-formalize", "UNKNOWN", ""))
