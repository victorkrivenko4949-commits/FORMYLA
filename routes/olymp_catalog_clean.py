"""Non-destructive catalog audit. Source texts are not repaired by heuristics."""
from pathlib import Path
import re

STATUS_LABEL = {
    "official_found": "официальное", "official": "официальное",
    "AI_verified": "проверено ИИ", "gemini_solved": "Gemini",
    "official_variant": "вариант источника", "AI_generated": "сгенерировано",
    "AI_generated_with_hints": "набросок", "unresolved": "не решено",
    "broken_text": "условие повреждено", "figure_only": "только рисунок",
}
QA_KEYS = ("tasks", "task_block_removed", "solution_in_text", "text_dup_in_solution",
           "solution_truncated", "text_truncated", "fig_missing", "fig_not_linked", "no_solution",
           "garbled", "needs_review", "ocr_suspected", "pdf_boundary_suspected")

# FIGS_AUDIT: текст ссылается на рисунок, а файлов рисунков у задачи нет
FIG_WORDS = re.compile(
    r"рисун|чертеж|чертёж|см\.\s*рис|на\s+картинк|изображ[её]н|закрашен|заштрихован|серы[хе]\s+клет|"
    r"ч[её]рны[ехм]\s+клет|клет(?:ки|ок)\s+ч[её]рн|бел(?:ые|ых)\s+клет|фигурк|показан[оа]?\s+на|"
    r"приведен[оа]?\s+на\s+рис|диаграмм|на\s+доске\s+(?:нарисован|изображ)|развёртк|разверт", re.IGNORECASE)


def new_qa():
    return dict.fromkeys(QA_KEYS, 0)


def norm_tex(value):
    return value if isinstance(value, str) else "" if value is None else str(value)


def cut_tail(text, min_keep=120):
    return text, False


def garbled_score(text):
    return len(re.findall(r"[\ufffd\uffff\ue000-\uf8ff]", norm_tex(text)))


def inspect_task(t, fig_dir):
    issues = []
    for field in ("text", "solution", "answer"):
        value = norm_tex(t.get(field))
        if garbled_score(value):
            issues.append({"field": field, "code": "ocr_suspected"})
        if re.search(r"©\s*МФТИ|Ответы и решения", value):
            issues.append({"field": field, "code": "pdf_boundary_suspected"})
    text = norm_tex(t.get("text"))
    if re.search(r"(?:^|[\s.])(?:Решение|Ответ)\s*[.:]|\\begin\{solution\}", text):
        issues.append({"field": "text", "code": "solution_in_text"})
    root = Path(fig_dir).resolve()
    for field in ("fig_statement", "fig_solution"):
        values = t.get(field) or []
        if not isinstance(values, list):
            issues.append({"field": field, "code": "invalid_figure_list"})
            continue
        for value in values:
            try:
                path = (root / str(value).replace("\\", "/")).resolve()
                valid = path.is_relative_to(root) and path.is_file()
            except (OSError, ValueError, RuntimeError):
                valid = False
            if not valid:
                issues.append({"field": field, "code": "fig_missing", "path": value})
    if not (t.get("fig_statement") or t.get("fig_solution")) and not t.get("fig_none_in_source"):
        blob = text + " " + norm_tex(t.get("solution"))
        m = FIG_WORDS.search(blob)
        if m:
            issues.append({"field": "text", "code": "fig_not_linked", "hint": m.group(0)})
    return issues


def clean_task(t, qa, fig_dir):
    issues = inspect_task(t, fig_dir)
    t["quality_issues"] = issues
    t["needs_review"] = bool(issues)
    t["fig_missing"] = sum(x["code"] == "fig_missing" for x in issues)
    t["fig_not_linked"] = any(x["code"] == "fig_not_linked" for x in issues)
    # Disable unverified reconstruction and automatic solution spoilers.
    t["garbled"] = False
    qa["fig_missing"] += t["fig_missing"]
    qa["fig_not_linked"] += bool(t["fig_not_linked"])
    qa["no_solution"] += not bool(norm_tex(t.get("solution")).strip())
    qa["needs_review"] += bool(issues)
    for code in ("solution_in_text", "ocr_suspected", "pdf_boundary_suspected"):
        qa[code] += any(x["code"] == code for x in issues)
    return t
