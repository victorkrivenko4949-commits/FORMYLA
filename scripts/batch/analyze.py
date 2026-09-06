# -*- coding: utf-8 -*-
"""scripts/batch/analyze.py — агрегаты и сверка ответов (блоки 3-5).

Читает out/results.jsonl + out/sample_100.jsonl, пишет out/METRICS.md.

Блок 3: численная сверка solver_answer / measured_answer с dataset_answer.
Блок 4: агрегаты (общее, по группам, классам, aux, качество, модели, ошибки).
Блок 5: кластеры дефектов, корреляции, категории задач.
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(_SCRIPT_DIR, "out")
RESULTS_PATH = os.path.join(OUT_DIR, "results.jsonl")
SAMPLE_PATH = os.path.join(OUT_DIR, "sample_100.jsonl")
METRICS_PATH = os.path.join(OUT_DIR, "METRICS.md")

RUB_PER_USD = 86.0


# ── Ответы: разбор и сверка ─────────────────────────────────────────────────

# Нормализация кодов ошибок: job.error хранит русские сообщения, но коды
# в stage.error_codes / _record_stage уже стабильны (LLM_*, CONDITION_*, ...).
# Здесь приводим сырые строки к устойчивым кодам для кластеризации.
_ERROR_NORM = [
    (r"(?i)LLM_NO_JSON", "LLM_NO_JSON"),
    (r"(?i)LLM_AUTH", "LLM_AUTH_ERROR"),
    (r"(?i)LLM_RATE", "LLM_RATE_LIMIT"),
    (r"(?i)LLM_SERVER", "LLM_SERVER_ERROR"),
    (r"(?i)LLM_EMPTY", "LLM_EMPTY_CONTENT"),
    (r"(?i)SOLVER_EMPTY", "SOLVER_EMPTY_RESPONSE"),
    (r"(?i)SOLVER_BAD_JSON", "SOLVER_BAD_JSON"),
    (r"(?i)MISSING_CONDITION_POINT", "MISSING_CONDITION_POINT"),
    (r"(?i)CONDITION_NOT_REALIZED", "CONDITION_NOT_REALIZED"),
    (r"(?i)LABEL_CONTRADICTS_GEOMETRY", "LABEL_CONTRADICTS_GEOMETRY"),
    (r"(?i)LABEL_COLLISION", "LABEL_COLLISION"),
    (r"(?i)AUX_.*?(NOT_NEEDED|DROPPED|BUILD_FAILED|PLAN_REJECTED|ROLLED_BACK|UNSUPPORTED|EXTRACT_FAILED)", "AUX_LAYER_REJECT"),
    (r"(?i)ANSWER_MISMATCH", "ANSWER_MISMATCH"),
    (r"(?i)Геометрические ограничения", "ENGINE_CONSTRAINT_VIOLATION"),
    (r"(?i)Не удалось разобрать base-план", "BASE_PLAN_PARSE_FAILED"),
    (r"(?i)Модель не смогла создать корректный base-план", "BASE_PLAN_INVALID"),
    (r"(?i)Модель не смогла исправить aux-план", "AUX_PLAN_REJECTED"),
    (r"(?i)Модель не вернула JSON", "LLM_NO_JSON"),
    (r"(?i)Сервис генерации временно недоступен", "LLM_SERVICE_UNAVAILABLE"),
]


def normalize_error_code(raw: str) -> str:
    if not raw:
        return "UNKNOWN"
    raw = raw.strip()
    for pat, code in _ERROR_NORM:
        if re.search(pat, raw):
            return code
    # Если это уже похоже на код — вернуть как есть.
    if re.match(r"^[A-Z][A-Z0-9_]{2,}", raw):
        return raw.split(":")[0]
    return "OTHER"

def _clean(s: str) -> str:
    s = (s or "").strip()
    s = s.replace("\\,", "").replace("\\ ", " ")
    # LaTeX inline wrapper \( ... \) (в JSONL это \\( ... \\)).
    s = re.sub(r"^\\\(+|\\\)+$", "", s.strip())
    s = s.strip()
    return s


def _is_angle(s: str) -> bool:
    return ("°" in (s or "")) or ("\\circ" in (s or ""))


def _parse_simple(s: str) -> Optional[float]:
    s = _clean(s)
    if not s:
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_math_value(raw: Any) -> Optional[float]:
    """Распарсить ответ в число (None — не удалось)."""
    if raw is None:
        return None
    s = _clean(str(raw))
    if not s:
        return None
    # Отрезать хвостовую пунктуацию.
    s = re.sub(r"[.…:;,!?]+$", "", s).strip()
    # Слова-хвосты и единицы.
    s = re.sub(
        r"(?i)(сантиметр|миллиметр|метр|единиц[а-я]*|ед\.?|градус[а-я]*|"
        r"ответ\s*[:=]?)\s*$", "", s).strip()
    s = re.sub(r"(?i)^ответ\s*[:=]\s*", "", s).strip()
    # Углы/градусы — просто срезаем символ, численное значение остаётся.
    s = s.replace("°", "").replace("\\circ", "").strip()

    # Если есть "=" — берём правую часть.
    if "=" in s:
        s = s.split("=", 1)[1].strip()

    # Дробь a/b.
    m = re.fullmatch(r"([-+]?\d*\.?\d+)\s*/\s*([-+]?\d*\.?\d+)", s)
    if m:
        b = float(m.group(2))
        return float(m.group(1)) / b if b != 0 else None
    # Отношение a:b.
    m = re.fullmatch(r"([-+]?\d*\.?\d+)\s*:\s*([-+]?\d*\.?\d+)", s)
    if m:
        b = float(m.group(2))
        return float(m.group(1)) / b if b != 0 else None
    # LaTeX \frac{a}{b}.
    m = re.fullmatch(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", s)
    if m:
        a = _parse_simple(m.group(1))
        b = _parse_simple(m.group(2))
        return (a / b) if (a is not None and b) else None
    # k \sqrt{n}.
    m = re.fullmatch(r"([-+]?\d*\.?\d*)\s*\\sqrt\s*\{([^{}]+)\}", s)
    if m:
        coef_str = m.group(1)
        if coef_str in ("", "+", "-"):
            coef = 1.0 if coef_str != "-" else -1.0
        else:
            coef = float(coef_str)
        inner = _parse_simple(m.group(2))
        return coef * math.sqrt(inner) if (inner is not None and inner >= 0) else None
    # \sqrt{n} без коэффициента.
    m = re.fullmatch(r"\\sqrt\s*\{([^{}]+)\}", s)
    if m:
        inner = _parse_simple(m.group(1))
        return math.sqrt(inner) if (inner is not None and inner >= 0) else None
    # k\sqrt{n} без скобок-фигурных (sqrt21).
    m = re.fullmatch(r"([-+]?\d*\.?\d*)\s*\\sqrt\s*(\d+\.?\d*)", s)
    if m:
        coef_str = m.group(1)
        coef = 1.0 if coef_str in ("", "+", "-") else float(coef_str)
        if coef_str == "-":
            coef = -1.0
        inner = float(m.group(2))
        return coef * math.sqrt(inner)
    # Простое число.
    return _parse_simple(s)


def compare_answers(dataset_raw: Any, solver_raw: Any) -> str:
    """match | mismatch | unparsable (углы 0.5°, длины/числа отн. 1%)."""
    d = parse_math_value(dataset_raw)
    s = parse_math_value(solver_raw)
    if d is None or s is None:
        return "unparsable"
    if _is_angle(str(dataset_raw)):
        return "match" if abs(d - s) <= 0.5 else "mismatch"
    tol = max(abs(d) * 0.01, 1e-6)
    return "match" if abs(d - s) <= tol else "mismatch"


# ── Загрузка ─────────────────────────────────────────────────────────────────

def load_jsonl(path: str) -> List[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _pct(num: float, den: float) -> Optional[float]:
    if den <= 0:
        return None
    return round(100.0 * num / den, 1)


def _median(values: List[float]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _percentile(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    d0 = s[int(f)] * (c - k)
    d1 = s[int(c)] * (k - f)
    return d0 + d1


# ── Блок 3: сверка ответов ──────────────────────────────────────────────────

def reconciliation(results: List[dict]) -> dict:
    """Вернуть матрицу сверки + примеры D1."""
    matrix = Counter()          # (solver_vs, measured_vs)
    solver_verdicts = Counter() # match/mismatch/unparsable
    figure_verdicts = Counter()
    d1_examples = []

    for r in results:
        ds = r.get("dataset_answer")
        sol = r.get("solver_answer")
        meas = r.get("measured_answer")

        if ds not in (None, "") and sol not in (None, ""):
            sv = compare_answers(ds, sol)
            solver_verdicts[sv] += 1
        else:
            sv = None

        if ds not in (None, "") and meas not in (None, ""):
            mv = compare_answers(ds, meas)
            figure_verdicts[mv] += 1
        else:
            mv = None

        if sv is not None and mv is not None:
            matrix[(sv, mv)] += 1
            if sv == "match" and mv == "mismatch":
                d1_examples.append({
                    "task_id": r.get("task_id"),
                    "grade": r.get("grade"),
                    "dataset_answer": ds,
                    "solver_answer": sol,
                    "measured_answer": meas,
                })

    return {
        "matrix": dict(matrix),
        "solver_verdicts": dict(solver_verdicts),
        "figure_verdicts": dict(figure_verdicts),
        "d1_examples": d1_examples,
    }


# ── Блок 4: агрегаты ────────────────────────────────────────────────────────

def _status_counts(results: List[dict]) -> dict:
    c = Counter(r.get("status") for r in results)
    return {
        "total": len(results),
        "done": c.get("done", 0),
        "failed": c.get("failed", 0),
        "timeout": c.get("timeout", 0),
    }


def _group_stats(results: List[dict], group: str) -> dict:
    rs = [r for r in results if r.get("group") == group]
    done = [r for r in rs if r.get("status") == "done"]
    times = [r["total_ms"] for r in done if r.get("total_ms") is not None]
    cost = sum(r.get("total_cost_usd") or 0.0 for r in rs)
    return {
        "total": len(rs),
        "done": len(done),
        "failed": sum(1 for r in rs if r.get("status") == "failed"),
        "timeout": sum(1 for r in rs if r.get("status") == "timeout"),
        "success_rate": _pct(len(done), len(rs)),
        "median_ms": _median(times),
        "p90_ms": _percentile(times, 0.90),
        "p99_ms": _percentile(times, 0.99),
        "cost_usd": cost,
        "cost_per_done_usd": (cost / len(done)) if done else 0.0,
        "cost_per_done_rub": (cost / len(done) * RUB_PER_USD) if done else 0.0,
    }


def _grade_stats(results: List[dict]) -> List[dict]:
    rows = []
    for g in sorted({r.get("grade") for r in results if r.get("grade") is not None}):
        rs = [r for r in results if r.get("grade") == g]
        done = [r for r in rs if r.get("status") == "done"]
        cov = [r["coverage_score"] for r in done if r.get("coverage_score") is not None]
        vis = [r["visual_score"] for r in done if r.get("visual_score") is not None]
        times = [r["total_ms"] for r in done if r.get("total_ms") is not None]
        aux_needed = sum(1 for r in done if r.get("has_aux") or r.get("aux_source") in ("template", "solver"))
        rows.append({
            "grade": g,
            "total": len(rs),
            "success_rate": _pct(len(done), len(rs)),
            "median_coverage": _median(cov),
            "median_visual": _median(vis),
            "median_ms": _median(times),
            "aux_needed_rate": _pct(aux_needed, len(done)),
        })
    return rows


def _aux_stats(results: List[dict]) -> dict:
    done = [r for r in results if r.get("status") == "done"]
    from_template = sum(1 for r in done if r.get("aux_source") == "template")
    from_solver = sum(1 for r in done if r.get("aux_source") == "solver")
    dropped = sum(1 for r in done if r.get("aux_status") == "AUX_DROPPED")
    reasons = Counter(r.get("aux_dropped_reason") for r in done if r.get("aux_status") == "AUX_DROPPED")
    usefulness = [r["aux_usefulness"] for r in results if r.get("aux_usefulness") is not None]
    template_ids = Counter(r.get("aux_template_id") for r in results if r.get("aux_template_id"))
    return {
        "from_template_rate": _pct(from_template, len(done)),
        "from_solver_rate": _pct(from_solver, len(done)),
        "dropped_rate": _pct(dropped, len(done)),
        "drop_reasons": dict(reasons),
        "median_usefulness": _median(usefulness),
        "template_ids": dict(template_ids),
    }


def _quality_stats(results: List[dict], recon: dict) -> dict:
    done = [r for r in results if r.get("status") == "done"]
    verified = sum(1 for r in results if r.get("answer_verdict") == "verified")
    # solver_accuracy (блок 3.1): match / (match+mismatch).
    sv = recon["solver_verdicts"]
    sv_total = sv.get("match", 0) + sv.get("mismatch", 0)
    # figure_correctness (блок 3.2).
    fv = recon["figure_verdicts"]
    fv_total = fv.get("match", 0) + fv.get("mismatch", 0)

    def _has_code(code: str) -> int:
        return sum(1 for r in results if code in (r.get("error_codes") or []))

    # LABEL_COLLISION до/после автофикса — по стадиям.
    before = 0
    after = 0
    for r in results:
        has_coll = any(s.get("label_collisions", 0) > 0 for s in r.get("stages", []))
        fixed = any(s.get("autofix_applied") for s in r.get("stages", []))
        if has_coll:
            before += 1
        if has_coll and fixed:
            after += 1

    return {
        "answer_verified_rate": _pct(verified, len(done)),
        "solver_accuracy": _pct(sv.get("match", 0), sv_total) if sv_total else None,
        "figure_correctness": _pct(fv.get("match", 0), fv_total) if fv_total else None,
        "condition_not_realized": _has_code("CONDITION_NOT_REALIZED"),
        "label_contradicts": _has_code("LABEL_CONTRADICTS_GEOMETRY"),
        "label_collision_before": before,
        "label_collision_after_autofix": after,
    }


def _model_stats(results: List[dict]) -> dict:
    """Аналог SQL GROUP BY role, provider, model по стадиям."""
    agg: Dict[Tuple, dict] = {}
    odirouter_fallback = 0
    for r in results:
        for s in r.get("stages", []):
            key = (s.get("role"), s.get("provider"), s.get("model"))
            if key not in agg:
                agg[key] = {
                    "count": 0, "latency_sum": 0.0, "latency_n": 0,
                    "coverage_sum": 0.0, "coverage_n": 0,
                    "cost_usd": 0.0, "fallback": 0,
                }
            a = agg[key]
            a["count"] += 1
            if s.get("latency_ms") is not None:
                a["latency_sum"] += s["latency_ms"]
                a["latency_n"] += 1
            if s.get("coverage_score") is not None:
                a["coverage_sum"] += s["coverage_score"]
                a["coverage_n"] += 1
            a["cost_usd"] += s.get("estimated_cost_usd") or 0.0
            if s.get("fallback_used"):
                a["fallback"] += 1
                if s.get("provider") == "odirouter":
                    odirouter_fallback += 1

    rows = []
    for (role, provider, model), a in sorted(agg.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]), str(kv[0][2]))):
        rows.append({
            "role": role,
            "provider": provider,
            "model": model,
            "count": a["count"],
            "avg_latency_ms": round(a["latency_sum"] / a["latency_n"], 1) if a["latency_n"] else None,
            "avg_coverage": round(a["coverage_sum"] / a["coverage_n"], 4) if a["coverage_n"] else None,
            "cost_usd": round(a["cost_usd"], 6),
            "fallback_used": a["fallback"],
        })
    return {"rows": rows, "odirouter_fallback": odirouter_fallback}


def _error_stats(results: List[dict]) -> List[dict]:
    c: Dict[str, List[str]] = defaultdict(list)
    for r in results:
        for code in (r.get("error_codes") or []):
            if code:
                c[normalize_error_code(code)].append(str(r.get("task_id")))
    ranked = sorted(c.items(), key=lambda kv: -len(kv[1]))
    out = []
    for code, tids in ranked[:20]:
        out.append({
            "code": code,
            "count": len(tids),
            "examples": tids[:2],
        })
    return out


# ── Блок 5: дефекты ─────────────────────────────────────────────────────────

def _cluster_failures(results: List[dict]) -> List[dict]:
    """Кластеры неудач по error_codes размером >= 3."""
    c: Dict[str, List[str]] = defaultdict(list)
    for r in results:
        if r.get("status") in ("failed", "timeout"):
            codes = [normalize_error_code(x) for x in (r.get("error_codes") or [])]
            if not codes:
                c["NO_ERROR_CODE"].append(str(r.get("task_id")))
            for code in codes:
                c[code].append(str(r.get("task_id")))
    clusters = []
    for code, tids in sorted(c.items(), key=lambda kv: -len(kv[1])):
        if len(tids) >= 3:
            clusters.append({"code": code, "size": len(tids), "task_ids": tids[:3]})
    return clusters


def _condition_features(sample: List[dict]) -> Dict[str, dict]:
    """Словарь task_id -> признаки условия (для корреляций)."""
    feats = {}
    for r in sample:
        cond = r.get("condition") or ""
        feats[r.get("task_id")] = {
            "condition": cond,
            "len": len(cond),
            "grade": r.get("grade"),
            "has_circle": bool(re.search(r"(?i)окруж|круг|circle|circum", cond)),
            "point_count": len(set(re.findall(r"\b([A-Z])\b", cond))),
            "has_latex": bool(re.search(r"\\\(|\\\[|\\frac|\\sqrt|\\circ|\\angle", cond)),
            "stereometry": bool(re.search(r"(?i)стереометр|пирамид|куб[еа]|параллелепипед|призм|конус|цилиндр|шар[ае]?|сфер", cond)),
            "construction": bool(re.search(r"(?i)постро|провед|построй|соедин|продл|опуст", cond)),
            "parameter": bool(re.search(r"(?i)параметр|при каких", cond)),
            "no_numeric": not re.search(r"\d", cond),
        }
    return feats


def _correlations(results: List[dict], feats: Dict[str, dict]) -> dict:
    """success_rate в зависимости от признаков условия."""
    def rate(subset_ids):
        rs = [r for r in results if r.get("task_id") in subset_ids]
        done = sum(1 for r in rs if r.get("status") == "done")
        return _pct(done, len(rs)) if rs else None

    by_len = {"short": set(), "long": set()}
    for tid, f in feats.items():
        (by_len["short"] if f["len"] <= 300 else by_len["long"]).add(tid)

    def bin_rate(ids, key):
        sub = {tid for tid, f in feats.items() if f[key]}
        comp = {tid for tid, f in feats.items() if not f[key]}
        return {"yes": rate(sub), "no": rate(comp)}

    return {
        "by_condition_length": {
            "short_<=300": rate(by_len["short"]),
            "long_>300": rate(by_len["long"]),
        },
        "has_circle": bin_rate(None, "has_circle"),
        "has_latex": bin_rate(None, "has_latex"),
        "stereometry": bin_rate(None, "stereometry"),
        "construction": bin_rate(None, "construction"),
        "parameter": bin_rate(None, "parameter"),
        "no_numeric": bin_rate(None, "no_numeric"),
    }


# ── Рендер METRICS.md ───────────────────────────────────────────────────────

def _md_table(headers: List[str], rows: List[List[Any]]) -> str:
    lines = ["| " + " | ".join(str(h) for h in headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join("" if v is None else str(v) for v in r) + " |")
    return "\n".join(lines)


def _fmt(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.2f}"
    return str(x)


def build_metrics(results: List[dict], sample: List[dict], recon: dict) -> str:
    L: List[str] = []
    sc = _status_counts(results)

    L.append("# METRICS — пакетный прогон geometry 7-11\n")

    L.append("## 4.1 Общее\n")
    done = sc["done"]
    total = sc["total"]
    finished = done + sc["failed"]
    times = [r["total_ms"] for r in results if r.get("status") == "done" and r.get("total_ms") is not None]
    cost = sum(r.get("total_cost_usd") or 0.0 for r in results)
    L.append(_md_table(
        ["Метрика", "Значение"],
        [
            ["Всего задач", total],
            ["Done", done],
            ["Failed", sc["failed"]],
            ["Timeout", sc["timeout"]],
            ["First-pass success rate", _pct(done, finished) if finished else None],
            ["Median total_ms", _fmt(_median(times))],
            ["p90 total_ms", _fmt(_percentile(times, 0.90))],
            ["p99 total_ms", _fmt(_percentile(times, 0.99))],
            ["Cost per done job (USD)", _fmt(cost / done if done else 0.0)],
            ["Cost per done job (₽, курс 86)", _fmt(cost / done * RUB_PER_USD if done else 0.0)],
        ],
    ))
    L.append("")

    L.append("## 4.2 По группам (A=с решением, B=без решения)\n")
    gA = _group_stats(results, "A")
    gB = _group_stats(results, "B")
    L.append(_md_table(
        ["Метрика", "GROUP_A (condition_solution)", "GROUP_B (solver_aux)"],
        [
            ["Всего", gA["total"], gB["total"]],
            ["Done", gA["done"], gB["done"]],
            ["Failed", gA["failed"], gB["failed"]],
            ["Timeout", gA["timeout"], gB["timeout"]],
            ["Success rate, %", _fmt(gA["success_rate"]), _fmt(gB["success_rate"])],
            ["Median ms", _fmt(gA["median_ms"]), _fmt(gB["median_ms"])],
            ["p90 ms", _fmt(gA["p90_ms"]), _fmt(gB["p90_ms"])],
            ["p99 ms", _fmt(gA["p99_ms"]), _fmt(gB["p99_ms"])],
            ["Cost/done USD", _fmt(gA["cost_per_done_usd"]), _fmt(gB["cost_per_done_usd"])],
            ["Cost/done ₽", _fmt(gA["cost_per_done_rub"]), _fmt(gB["cost_per_done_rub"])],
        ],
    ))
    L.append("")

    L.append("## 4.3 По классам 7-11\n")
    gs = _grade_stats(results)
    L.append(_md_table(
        ["Класс", "Всего", "Success %", "Median coverage", "Median visual", "Median ms", "Aux needed %"],
        [[g["grade"], g["total"], _fmt(g["success_rate"]),
          _fmt(g["median_coverage"]), _fmt(g["median_visual"]),
          _fmt(g["median_ms"]), _fmt(g["aux_needed_rate"])] for g in gs],
    ))
    # Вопрос: есть ли класс заметно хуже.
    rates = {g["grade"]: g["success_rate"] for g in gs if g["success_rate"] is not None}
    if rates:
        worst = min(rates, key=rates.get)
        best = max(rates, key=rates.get)
        L.append(f"\nХудший класс по success_rate: **{worst}** ({_fmt(rates[worst])}%), "
                 f"лучший: **{best}** ({_fmt(rates[best])}%).\n")
    L.append("")

    L.append("## 4.4 Доп. построения\n")
    aux = _aux_stats(results)
    L.append(_md_table(
        ["Метрика", "Значение"],
        [
            ["aux_from_template_rate, %", _fmt(aux["from_template_rate"])],
            ["aux_from_solver_rate, %", _fmt(aux["from_solver_rate"])],
            ["aux_dropped_rate, %", _fmt(aux["dropped_rate"])],
            ["median aux_usefulness", _fmt(aux["median_usefulness"])],
        ],
    ))
    if aux["drop_reasons"]:
        L.append("\nРазбивка aux_dropped_reason:\n")
        L.append(_md_table(["Причина", "Кол-во"], [[k, v] for k, v in sorted(aux["drop_reasons"].items(), key=lambda kv: -kv[1])]))
    if aux["template_ids"]:
        L.append("\nРаспределение template_id (какие шаблоны сработали):\n")
        L.append(_md_table(["template_id", "Кол-во"], [[k, v] for k, v in sorted(aux["template_ids"].items(), key=lambda kv: -kv[1])]))
    L.append("")

    L.append("## 4.5 Качество\n")
    q = _quality_stats(results, recon)
    L.append(_md_table(
        ["Метрика", "Значение", "Цель"],
        [
            ["answer_verified_rate, %", _fmt(q["answer_verified_rate"]), ">= 85"],
            ["solver_accuracy, %", _fmt(q["solver_accuracy"]), ">= 85"],
            ["figure_correctness, %", _fmt(q["figure_correctness"]), "= 100"],
            ["CONDITION_NOT_REALIZED (задач)", q["condition_not_realized"], "0"],
            ["LABEL_CONTRADICTS_GEOMETRY (задач)", q["label_contradicts"], "0"],
            ["LABEL_COLLISION до автофикса", q["label_collision_before"], "—"],
            ["LABEL_COLLISION после автофикса", q["label_collision_after_autofix"], "—"],
        ],
    ))
    L.append("")

    L.append("## 4.6 По моделям и ролям\n")
    ms = _model_stats(results)
    L.append(_md_table(
        ["Role", "Provider", "Model", "Count", "AVG latency_ms", "AVG coverage", "Cost USD", "Fallback"],
        [[m["role"], m["provider"], m["model"], m["count"],
          _fmt(m["avg_latency_ms"]), _fmt(m["avg_coverage"]),
          _fmt(m["cost_usd"]), m["fallback_used"]] for m in ms["rows"]],
    ))
    L.append(f"\nOdiRouter fallback: **{ms['odirouter_fallback']}** раз.\n")

    L.append("## 4.7 Топ-20 кодов ошибок\n")
    errs = _error_stats(results)
    if errs:
        L.append(_md_table(
            ["Код", "Частота", "Примеры task_id"],
            [[e["code"], e["count"], ", ".join(e["examples"])] for e in errs],
        ))
    else:
        L.append("(нет ошибок)")
    L.append("")

    L.append("## 3.3 Матрица сверки ответов (КЛЮЧЕВАЯ)\n")
    matrix = recon["matrix"]
    order = [("match", "match"), ("match", "mismatch"), ("mismatch", "match"), ("mismatch", "mismatch")]
    L.append(_md_table(
        ["solver vs dataset", "measured vs dataset", "Смысл", "Кол-во"],
        [
            ["match", "match", "всё верно", matrix.get(("match", "match"), 0)],
            ["match", "mismatch", "ЧЕРТЁЖ неверен (D1)", matrix.get(("match", "mismatch"), 0)],
            ["mismatch", "match", "solver ошибся, чертёж ок", matrix.get(("mismatch", "match"), 0)],
            ["mismatch", "mismatch", "двойная ошибка", matrix.get(("mismatch", "mismatch"), 0)],
        ],
    ))
    L.append("\nЯчейка «match/mismatch» — главный индикатор нерешённого D1: "
             f"**{matrix.get(('match', 'mismatch'), 0)}** задач.\n")
    L.append("")

    L.append("## 5.1 Кластеры неудач (>= 3 по error_codes)\n")
    clusters = _cluster_failures(results)
    if clusters:
        L.append(_md_table(
            ["Кластер (error_code)", "Размер", "Примеры task_id"],
            [[c["code"], c["size"], ", ".join(c["task_ids"])] for c in clusters],
        ))
    else:
        L.append("(нет кластеров размером >= 3)")
    L.append("")

    L.append("## 5.2 Корреляции success_rate\n")
    feats = _condition_features(sample)
    corr = _correlations(results, feats)
    L.append(_md_table(
        ["Признак", "Да", "Нет"],
        [
            ["Наличие окружностей", _fmt(corr["has_circle"]["yes"]), _fmt(corr["has_circle"]["no"])],
            ["LaTeX-разметка", _fmt(corr["has_latex"]["yes"]), _fmt(corr["has_latex"]["no"])],
            ["Стереометрия", _fmt(corr["stereometry"]["yes"]), _fmt(corr["stereometry"]["no"])],
            ["Задача на построение", _fmt(corr["construction"]["yes"]), _fmt(corr["construction"]["no"])],
            ["Задача с параметром", _fmt(corr["parameter"]["yes"]), _fmt(corr["parameter"]["no"])],
            ["Без числовых данных", _fmt(corr["no_numeric"]["yes"]), _fmt(corr["no_numeric"]["no"])],
        ],
    ))
    L.append("\nПо длине условия: короткие (<=300) " +
             f"{_fmt(corr['by_condition_length']['short_<=300'])}%, длинные (>300) " +
             f"{_fmt(corr['by_condition_length']['long_>300'])}%.\n")

    return "\n".join(L)


def main() -> int:
    results = load_jsonl(RESULTS_PATH)
    sample = load_jsonl(SAMPLE_PATH)
    if not results:
        print("[analyze] results.jsonl пуст или отсутствует.", file=sys.stderr)
        return 1
    recon = reconciliation(results)
    md = build_metrics(results, sample, recon)
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(METRICS_PATH, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"[analyze] METRICS.md -> {METRICS_PATH}")
    print(f"[analyze] матрица: {recon['matrix']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
