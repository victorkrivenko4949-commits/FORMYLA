"""Конвейер GeoExact: 9 этапов от текста задачи до SVG.

1 нормализация+кэш · 2 классификация(LLM) · 3 маршрутизация · 4 формализация(LLM)
5 валидация схемы · 6 решение ограничений · 7 гейт корректности
8 гейт наглядности+ранжирование · 9 рендер+кэш

Этапы 2 и 4 — единственные с LLM. Остальные 7 детерминированы.
"""
from __future__ import annotations

import hashlib
import threading
import numpy as np
import math
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
ENGINE_VERSION = "2.6"


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


SIMPLIFY_FEEDBACK = (
    "Все предыдущие планы не удалось построить. Построй УПРОЩЁННЫЙ, но "
    "гарантированно исполнимый план: основная фигура из free_point, точки на "
    "сторонах через divide_segment, пересечения через line_intersect, "
    "середины через midpoint. Используй только простые операции и не больше "
    "одной dist для масштаба. Условия, которые не удаётся выразить, НЕ "
    "добавляй, а перечисли одной строкой в notes. Никогда не возвращай error."
)

# Wall-clock limit for starting one more LLM attempt (worker alarm is 590 s).
_EXTRA_ATTEMPT_DEADLINE = 300.0
# Whole request, all model attempts included. When it runs out the best
# drawing found so far (or a keyword sketch) is returned instead of waiting.
TIME_LIMIT = float(os.getenv("GEOEXACT_TIME_LIMIT", "170"))


def _finite_coords(sol) -> bool:
    import math
    coords = getattr(sol, "coords", None) or {}
    try:
        values = [float(v) for p in coords.values() for v in p]
    except (TypeError, ValueError):
        return False
    return len(coords) >= 2 and all(math.isfinite(v) and abs(v) < 1e9 for v in values)


class _NoModel:
    uncertain = True


def _collapsed(sol) -> bool:
    """A degenerate drawing: coinciding points or a figure squeezed into a line."""
    try:
        pts = np.array([np.asarray(v, float) for v in sol.coords.values()])
        ext = np.ptp(pts, axis=0)
        if ext.max() <= 0 or ext.min() < 0.03 * ext.max():
            return True
        span = float(ext.max())
        d = np.linalg.norm(pts[:, None] - pts[None], axis=2) + np.eye(len(pts)) * 1e9
        return bool(d.min() < 0.005 * span)
    except Exception:  # noqa: BLE001
        return True


def _sketch_result(text: str, with_aux: bool, base: "Result | None", aux=None) -> "Result | None":
    """Deterministic keyword sketch when nothing else is drawable (no LLM)."""
    from .sketch import sketch_plan
    from .constructions import execute
    from .solver import Solution
    from .render import render_svg
    try:
        built = sketch_plan(text)
        if built is None:
            return None
        plan, free = built
        coords = execute(plan, free_values=free)
        sol = Solution(coords=coords, residual=0.0, ok=True)
        if not _finite_coords(sol):
            return None
        try:
            from .auxplan import add_named_circles
            plan, _c = add_named_circles(plan, sol.coords, text)
            if len(_c) != len(sol.coords):
                sol = Solution(coords=_c, residual=sol.residual, ok=sol.ok)
        except Exception:  # noqa: BLE001 - an optional addition
            pass
        if with_aux:
            # sess/budget/start when the model may still be asked; otherwise rules only
            sess, budget, t0 = aux or (None, _NoModel(), time.time())
            plan, sol = _auxiliary_layer(plan, sol, text, sess, budget, t0)
        svg = render_svg(plan, sol, gate=None, show_aux=with_aux)
    except Exception:  # noqa: BLE001 - a sketch must never break the pipeline
        return None
    return Result(True, "9-render-sketch", "", "", svg=svg, svg_base=svg,
                  plan=plan.to_dict(), with_aux=with_aux,
                  cls=getattr(base, "cls", "") or "",
                  warnings=["SKETCH: построен схематичный чертёж по ключевым словам "
                            "условия; пропорции условные, проверьте его по тексту задачи."],
                  notes=plan.notes, verification="sketch")


def _key(text: str, with_aux: bool) -> str:
    return hashlib.sha256(f"{ENGINE_VERSION}|{text}|{int(with_aux)}".encode()).hexdigest()[:20]


def _auxiliary_layer(plan, sol, text, sess, budget, t_start):
    """Auxiliary construction on the verified figure; never breaks the drawing.

    Order: crossing-cevian rule (done earlier), classical trapezoid rule, then a
    small separate model request that only proposes the auxiliary steps. Every
    step is executed and checked by the engine before it is drawn.
    """
    from . import auxplan
    from .solver import Solution
    try:
        coords = sol.coords
        applied = None
        model_failed = True
        job = getattr(_AUXJOB, "value", None)
        if job is not None:
            answers = job.answers(budget)
            model_failed = not answers
            # A hand-written figure keeps its own auxiliary lines only when the model
            # gave nothing usable; otherwise they are replaced by the model's.
            base = _strip_aux(plan) if getattr(_AUXJOB, "special", False) else plan
            for _name, data in answers:
                applied = auxplan.apply_aux(base, coords, data)
                asked = bool(data.get("steps") or data.get("aux_segments")
                             or data.get("aux_lines") or data.get("aux_circles"))
                if applied is not None or not asked:
                    # a usable answer, or the model's own "nothing to add"
                    model_failed = False
                    if applied is not None:
                        break
                    plan = base          # "nothing to add": no built-in lines either
                else:
                    model_failed = True
        elif not budget.uncertain and time.time() - t_start < TIME_LIMIT - 40:
            try:
                data = L.aux_plan(sess, text, auxplan.describe_figure(plan, coords), budget)
                applied = auxplan.apply_aux(plan, coords, data)
                # An empty or refused answer is the model's decision ("not needed");
                # only a failed request or unusable steps fall back to the rules.
                asked = isinstance(data, dict) and bool(
                    data.get("steps") or data.get("aux_segments") or data.get("aux_lines")
                    or data.get("aux_circles"))
                model_failed = (not isinstance(data, dict)) or (asked and applied is None)
            except (PlanError, ValueError, TypeError, KeyError, AttributeError, OSError):
                model_failed = True
        if applied is None and model_failed and not getattr(_AUXJOB, "special", False):
            rule = auxplan.trapezoid_diagonals(plan, coords, text)
            if rule:
                applied = auxplan.apply_aux(plan, coords, rule)
        if not applied and not auxplan.has_aux(plan) and auxplan.mentions_construction(plan.notes):
            # the text must not claim a construction that is not on the drawing
            import copy
            plan = copy.deepcopy(plan)
            plan.notes = ""
        if applied:
            new_plan, new_coords = applied
            return new_plan, Solution(coords=new_coords, residual=sol.residual, ok=sol.ok,
                                      reason=sol.reason)
    except Exception:  # noqa: BLE001 - the auxiliary layer is optional
        pass
    return plan, sol


_NUMERIC_ERRORS = (ValueError, TypeError, ZeroDivisionError, FloatingPointError,
                   OverflowError, ArithmeticError, KeyError, IndexError, AttributeError)


_AUXJOB = threading.local()


class _AuxJob:
    """The model's auxiliary construction, requested in parallel with the figure.

    Two requests to the strongest model start at once: one with reasoning (the
    mathematically better answer, which on a hard problem can take over a minute)
    and one quick answer without reasoning. The reasoning answer is used when it
    arrives in time and is usable; otherwise the quick one. The answer is checked
    against the real coordinates before anything is drawn. Each request has its own
    small budget, and a request is never repeated.
    """
    DEEP_WAIT = 110.0

    def __init__(self, sess, text: str, deadline: float):
        self.sess, self.text, self.deadline = sess, text, deadline
        self.started = time.time()
        self.slots = {}
        for name, deep in (("deep", True), ("fast", False)):
            slot = {"data": None, "error": None, "done": threading.Event(),
                    "budget": L.Budget(cap=0.06)}
            self.slots[name] = slot
            threading.Thread(target=self._run, args=(slot, deep), daemon=True).start()

    def _run(self, slot, deep):
        try:
            L.set_deadline(self.deadline)
            from .auxplan import STATEMENT_ONLY
            slot["data"] = L.aux_plan(self.sess, self.text, STATEMENT_ONLY, slot["budget"], deep=deep)
        except Exception as exc:  # noqa: BLE001 - reported through the slot
            slot["error"] = exc
        finally:
            slot["done"].set()

    def answers(self, main_budget=None):
        """Usable answers in order of preference: [(name, data)]."""
        stop = min(self.deadline - 4, self.started + self.DEEP_WAIT)
        self.slots["deep"]["done"].wait(max(0.0, stop - time.time()))
        self.slots["fast"]["done"].wait(max(0.0, self.deadline - 4 - time.time()))
        out = []
        for name in ("deep", "fast"):
            slot = self.slots[name]
            if slot["done"].is_set():
                if main_budget is not None and slot["budget"].calls:
                    main_budget.calls.extend(slot["budget"].calls)
                    main_budget.spent += slot["budget"].spent
                    slot["budget"].calls = []
                if slot["error"] is None and isinstance(slot["data"], dict):
                    out.append((name, slot["data"]))
        return out


def generate(problem: str, with_aux: bool = False, **kwargs) -> Result:
    """Public entry point: never raises; an internal fault degrades to a sketch."""
    try:
        deadline = time.time() + TIME_LIMIT
        L.set_deadline(deadline)
        _AUXJOB.value = None
        _AUXJOB.special = False
        if with_aux and isinstance(problem, str) and problem.strip() and kwargs.get("sess") is not None:
            _AUXJOB.value = _AuxJob(kwargs["sess"], _norm(problem), deadline - 6)
        return _generate(problem, with_aux, **kwargs)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:  # noqa: BLE001 - last line of defence for the user
        import logging
        logging.getLogger(__name__).exception("GeoExact internal error")
        text = _norm(problem) if isinstance(problem, str) else ""
        failed = Result(False, "0-internal", "INTERNAL_ERROR",
                        f"внутренняя ошибка построения ({type(exc).__name__})")
        sketch = _sketch_result(text, with_aux, failed) if text else None
        if sketch is not None:
            sketch.warnings.append(f"INTERNAL: {type(exc).__name__}")
            return sketch
        return failed
    finally:
        L.set_deadline(None)
        _AUXJOB.value = None
        _AUXJOB.special = False


def _strip_invented_labels(text: str, plan) -> None:
    """Numbers on the drawing must come from the statement: a number-free problem
    gets no numeric length labels the model made up for its sample sizes."""
    try:
        if re.search(r"\d", re.sub(r"[A-Z](?:_?\d{1,2})?(?![A-Za-z])", "", text)):
            return
        plan.draw.length_marks = [m for m in plan.draw.length_marks
                                  if not re.search(r"\d", str(m.get("text", "")))]
    except Exception:  # noqa: BLE001
        return


def _strip_aux(plan):
    import copy
    plan = copy.deepcopy(plan)
    d = plan.draw
    for f in ("aux_segments", "aux_lines", "aux_rays", "aux_extensions", "aux_circles", "aux_points"):
        setattr(d, f, [])
    for f in ("length_marks", "angle_marks", "equal_marks"):
        setattr(d, f, [m for m in getattr(d, f) if m.get("layer", "main") != "aux"])
    d.arcs = [a for a in d.arcs if a.get("layer", "main") != "aux"]
    return plan


def _connect_orphans(plan) -> None:
    """A point that is constructed but touches nothing on the drawing (a bisector
    continued to the circle, a reflected point, a foot) is joined to the point it
    was built from, so it does not float in the picture."""
    try:
        d = plan.draw
        touched = set()
        for f in ("segments", "aux_segments", "lines", "aux_lines", "rays", "aux_rays",
                  "extensions", "aux_extensions", "circles", "aux_circles"):
            for item in getattr(d, f):
                touched.update(x for x in item if isinstance(x, str))
        for c in plan.constructions:
            if c.out in touched or c.out in d.hide_labels or c.out in d.aux_points:
                continue
            src = None
            if c.op in ("line_circle", "line_circle_other") and len(c.args) == 4:
                src = c.args[0]
            elif c.op == "foot" and len(c.args) == 3:
                src = c.args[0]
            elif c.op == "reflect_point" and len(c.args) == 2:
                src = c.args[0]
            if src and src in plan.points and src != c.out:
                d.segments.append([src, c.out])
                touched.update((src, c.out))
    except Exception:  # noqa: BLE001
        return


def _coerce_formalized(res):
    """The model adapter must return (FigurePlan, warnings); anything else is BAD_JSON."""
    from .schema import FigurePlan
    if (not isinstance(res, tuple) or len(res) != 2
            or not isinstance(res[0], FigurePlan)):
        raise PlanError("BAD_JSON", "модель вернула не план чертежа")
    plan, warn = res
    return plan, [str(w) for w in (warn or []) if isinstance(w, str)]


def _generate(problem: str, with_aux: bool = False, *, sess=None, budget=None,
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
    from .semantics import preflight_condition_error
    condition_error = preflight_condition_error(text)
    if condition_error:
        failed = Result(False, "1-normalize", "INVALID_CONDITION", condition_error)
        sketch = _sketch_result(text, with_aux, failed)
        if sketch is None:
            return failed
        # Draw the figure anyway, but never build on an impossible value.
        sketch.warnings.insert(0, "INVALID_CONDITION: " + condition_error)
        return sketch
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
        if res.ok and use_cache and res.verification not in ("approximate", "simplified", "sketch"):
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
    from .semantics import (common_plan, proof_parallelogram_plan, trisected_parallel_plan,
                            requests_circumcircle,
                            requests_incircle, requests_rhombus,
                            _claims_incenter_arc_bisector as _claims_bisector_arc,
                            semantic_failures, theorem_plan)
    special_plan = (theorem_plan(text, with_aux)
                    or common_plan(text, with_aux)
                    or proof_parallelogram_plan(text, with_aux)
                    or trisected_parallel_plan(text, with_aux))
    if special_plan is not None and with_aux:
        # The hand-written figure stays (it is verified), but its built-in auxiliary
        # constructions are not ours to decide: the model proposes them below.
        _AUXJOB.special = True
    if special_plan is None:
        # ------------------------------------------------------ этап 2
        try:
            c = L.classify(sess, text, budget)
            if not isinstance(c, dict):
                raise PlanError("BAD_JSON", "классификатор вернул не объект")
        except PlanError as e:
            failed = Result(False, "2-classify", e.code, str(e))
            return finish(_sketch_result(text, with_aux, failed) or failed)
        except _NUMERIC_ERRORS + (RuntimeError, OSError) as e:
            failed = Result(False, "2-classify", "API_ERROR", type(e).__name__)
            return finish(_sketch_result(text, with_aux, failed) or failed)
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
    # Candidates for a best-effort drawing when strict verification fails:
    # (priority, attempt, plan, solution, reasons). Lower priority is better:
    # 0 — only derived annotations failed; 1 — readability only; 2 — the
    # wording check failed although plan constraints hold; 3 — correctness
    # gate failed; 4 — the solver did not converge (approximate coordinates).
    candidates: list[tuple] = []

    def keep(priority, plan_, sol_, reasons):
        if sol_ is not None and _finite_coords(sol_):
            candidates.append((priority, len(candidates), plan_, sol_,
                               [r for r in reasons if r][:4]))

    total_attempts = (1 if special_plan is not None else max_retries + 2)
    for attempt in range(total_attempts):
        simplified = False
        if attempt and time.time() - t_start > TIME_LIMIT - 30:
            break          # no time for another model answer: use what we have
        if special_plan is None and attempt == total_attempts - 1:
            # Last resort: a simplified but executable plan, only when no
            # earlier attempt produced anything drawable.
            if (candidates or budget.uncertain
                    or time.time() - t_start > min(_EXTRA_ATTEMPT_DEADLINE, TIME_LIMIT - 60)
                    or (last is not None and last.reason in
                        ("BUDGET_EXCEEDED", "API_ERROR", "NETWORK_UNCERTAIN", "TIME_LIMIT"))):
                break
            feedback = SIMPLIFY_FEEDBACK + (f" Предыдущая ошибка: {feedback}" if feedback else "")
            prev_code = "SIMPLIFY"
            simplified = True
        # этап 3 маршрутизация + этап 4 формализация + этап 5 валидация
        try:
            if special_plan is not None:
                plan = special_plan
                warn = [w for w in validate_plan(plan)
                        if not w.startswith("UNDERDETERMINED:")]
            else:
                try:
                    plan, warn = _coerce_formalized(
                        L.formalize(sess, text, cls, with_aux, budget, feedback, prev_code))
                    _strip_invented_labels(text, plan)
                    _connect_orphans(plan)
                    validate_plan(plan)
                except PlanError:
                    raise
                except _NUMERIC_ERRORS + (RuntimeError, OSError) as e:
                    raise PlanError("BAD_JSON", f"ответ модели не разобран ({type(e).__name__})") from e
        except PlanError as e:
            last = Result(False, "4-formalize" if e.code not in
                          ("BUDGET_EXCEEDED",) else "3-route", e.code, str(e),
                          cls=cls, with_aux=with_aux, retries=attempt)
            feedback = str(e)
            prev_code = e.code
            if budget.uncertain or e.code in ("BUDGET_EXCEEDED", "API_ERROR", "TIME_LIMIT"):
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
        except (PlanError,) + _NUMERIC_ERRORS as e:
            if not isinstance(e, PlanError):
                e = PlanError("DEGENERATE", f"план не исполняется ({type(e).__name__})")
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
            if sols:
                best = min(sols, key=lambda s: getattr(s, "residual", float("inf")))
                keep(4, plan, best, ["условия выполнены лишь приближённо"])
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
            ranked_any = rank_solutions(plan, good, strict_readability=False)
            keep(2, plan, ranked_any[0][0] if ranked_any else good[0],
                 list(dict.fromkeys(semantic_errors)))
            last = Result(False, "7-semantics", "SEMANTIC_MISMATCH",
                          details, plan=plan.to_dict(), cls=cls,
                          with_aux=with_aux, retries=attempt)
            if requests_incircle(text):
                advice = (". Построй I=incenter(A,B,C), T=foot(I,B,C); "
                          "в основном draw.circles добавь [I,T]. "
                          "Окружность радиуса IA не является вписанной.")
            elif requests_circumcircle(text):
                advice = (". Построй O=circumcenter(A,B,C), добавь [O,A] "
                          "в основной draw.circles.")
            elif requests_rhombus(text):
                advice = (". Построй невырожденный ромб с равными сторонами "
                          "AB=BC=CD=DA и покажи все четыре стороны в draw.segments. "
                          "Не ссылайся на точки до их построения.")
            elif "OVER_SPECIALIZED" in details:
                advice = (". Ты сузил фигуру до частного случая. Не задавай точку сразу через "
                          "translate/parallel_point и равенство длин dist_eq: для «AP = AB и "
                          "PB ∥ AC» строй H=translate(B,A,C), P=line_circle_other(B,H,A,B). "
                          "Свободных точек A,B,C достаточно, произвольный треугольник.")
            elif _claims_bisector_arc(text):
                advice = (". Используй bisector_circumcircle(W,[A,B,C]), "
                          "не bisector_point; не выдумывай длины сторон.")
            else:
                advice = (". Исправь именно эти отношения: точки на сторонах "
                          "строй divide_segment/line_intersect, отношения вида "
                          "BD:DC=1:2 — divide_segment(B,C,value=1/3); "
                          "не выдумывай длин, которых нет в условии.")
            feedback = "План не соответствует исходному условию: " + details + advice
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
            keep(3, plan, good[0], uniq[:3] or ["проверка корректности не пройдена"])
            last = Result(False, "7-correctness", "GATE_CORRECTNESS", det,
                          plan=plan.to_dict(), cls=cls, with_aux=with_aux, retries=attempt)
            feedback = "построенная фигура не прошла проверку: " + det
            continue
        sol, gate = ranked[0]
        if special_plan is not None:
            gate.warnings = [w for w in gate.warnings
                             if not (
                                 w.startswith("UNDECLARED_INCIDENCE: I лежит на AW")
                                 or (w.startswith("POINT_ON_SEGMENT: O ")
                                     and "O" in plan.draw.hide_labels)
                             )]
        if not gate.ok:
            keep(1, plan, sol, ["чертёж может быть плохо читаемым: " + "; ".join(gate.failures[:2])])
            last = Result(False, "8-readability", "GATE_READABILITY",
                          "; ".join(gate.failures), plan=plan.to_dict(),
                          cls=cls, with_aux=with_aux, retries=attempt)
            feedback = "фигура получается вырожденной/нечитаемой: " + "; ".join(gate.failures)
            continue

        # ---------------------------------------------------------- этап 9
        from .annotations import enrich_annotations
        plain_plan = plan
        plan = enrich_annotations(plan, sol, with_aux=with_aux, problem_text=text)
        # Given ratios as x / 2x marks, and in the auxiliary mode the standard
        # parallel line for crossing cevians. Best effort: never breaks the drawing.
        try:
            from .ratios import add_parallel_aux, add_ratio_marks
            from .solver import Solution as _Solution
            marked = add_ratio_marks(plan, sol.coords, text)
            if with_aux:
                marked, extra = add_parallel_aux(marked, sol, text)
                if len(extra) != len(sol.coords):
                    sol = _Solution(coords=extra, residual=sol.residual, ok=sol.ok,
                                    reason=sol.reason)
            plan = marked
        except Exception:  # noqa: BLE001
            pass
        model_notes = plan.notes
        try:
            from .auxplan import add_named_circles
            from .solver import Solution as _Sol
            plan, _c = add_named_circles(plan, sol.coords, text)
            if len(_c) != len(sol.coords):
                sol = _Sol(coords=_c, residual=sol.residual, ok=sol.ok, reason=sol.reason)
        except Exception:  # noqa: BLE001 - an optional addition
            pass
        if with_aux:
            plan, sol = _auxiliary_layer(plan, sol, text, sess, budget, t_start)
        from .completion import complete_intersection_support
        plan, completion_warn = complete_intersection_support(plan, sol)
        warn.extend(completion_warn)
        # Derived marks and support lines are checked too; the pre-render
        # correctness gate only saw the un-annotated model plan.
        from .gates import gate_correctness
        after_marks = gate_correctness(plan, sol)
        if not after_marks.ok:
            keep(0, plain_plan, sol, ["часть автоматических отметок не показана"])
            last = Result(False, "9-annotations", "GATE_CORRECTNESS",
                          "; ".join(after_marks.failures), plan=plan.to_dict(),
                          cls=cls, with_aux=with_aux, retries=attempt)
            feedback = "добавленные метки не прошли проверку: " + last.detail
            continue
        try:
            svg = render_svg(plan, sol, gate=gate, show_aux=with_aux)
            svg_base = render_svg(plan, sol, gate=gate, show_aux=False) if with_aux else svg
        except PlanError as e:
            keep(0, plain_plan, sol, ["часть оформления не удалось показать"])
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
        if special_plan is not None:
            # A sub-unit placement preference is not an actual collision.
            render_warn = [
                w for w in render_warn
                if not (w.startswith("LABEL_COLLISION:")
                        and (m := re.search(r"штраф ([\d.]+)", w))
                        and float(m.group(1)) < 1.0)
            ]
        from .detail import detail_view
        svg_detail=detail_view(plan,sol,show_aux=with_aux)
        if svg_detail:
            warn.append("DETAIL_VIEW: исходная фигура мала на общем виде; приложен увеличенный фрагмент")
        if simplified:
            warn.insert(0, "SIMPLIFIED: чертёж построен по упрощённой схеме; часть условий "
                           "могла быть опущена" + (f" ({model_notes})" if model_notes else ""))
        return finish(Result(True, "9-render", "", "", svg=svg, plan=plan.to_dict(),
                             svg_base=svg_base, svg_detail=svg_detail, measurement_range=value_range,
                             measured=None if simplified else gate.measured,
                             cls=cls, with_aux=with_aux,
                             retries=attempt, warnings=warn + gate.warnings + render_warn,
                             notes=plan.notes,
                             verification="simplified" if simplified else "constraints_only"))

    # ------------------------------------------------------ best-effort
    # Strict verification failed on every attempt. Instead of an error, show
    # the most trustworthy drawing that exists, labelled as not fully checked.
    from .gates import measure_target
    for priority, _, cplan, csol, reasons in sorted(candidates, key=lambda c: c[:2]):
        if priority >= 3 and _collapsed(csol) and _sketch_result(text, with_aux, None) is not None:
            continue                      # a squeezed drawing is worse than the sketch
        if with_aux:
            cplan, csol = _auxiliary_layer(cplan, csol, text, sess, budget, t_start)
        try:
            svg = render_svg(cplan, csol, gate=None, show_aux=with_aux)
            svg_base = render_svg(cplan, csol, gate=None, show_aux=False) if with_aux else svg
        except Exception:  # noqa: BLE001 - try the next candidate
            continue
        measured = None
        if priority <= 1:
            try:
                measured = measure_target(cplan, csol.coords)
            except Exception:  # noqa: BLE001
                measured = None
        if priority == 0:
            warns = ["APPROXIMATE: чертёж проверен, часть автоматических отметок не показана"]
        else:
            warns = ["APPROXIMATE: не подтверждено автоматически: "
                     + ("; ".join(reasons) or "часть условия")]
        if priority >= 3:
            warns.append("Размеры и углы на рисунке могут быть неточными.")
        return finish(Result(True, "9-render-fallback", "", "", svg=svg,
                             svg_base=svg_base, plan=cplan.to_dict(),
                             measured=measured if isinstance(measured, (int, float))
                             and math.isfinite(measured) else None,
                             cls=cls, with_aux=with_aux, retries=attempt,
                             warnings=warns, notes=cplan.notes,
                             verification="approximate"))

    last = last or Result(False, "4-formalize", "UNKNOWN", "")
    return finish(_sketch_result(text, with_aux, last, (sess, budget, t_start)) or last)
