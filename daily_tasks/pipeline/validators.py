# -*- coding: utf-8 -*-
"""
validators.py — Валидация для pipeline «Задачи дня».

1. LaTeX-валидация (строгая: только \(…\) / \[…\], без $…$)
2. JSON Schema-валидация вывода каждого LLM-шага
3. Кросс-валидация spec ↔ task ↔ audit
4. Извлечение JSON из сырого ответа LLM
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 1.  Латекс — строгий режим
# ──────────────────────────────────────────────

_DEPRECATED_DOLLAR_RE = re.compile(r"(?<!\\)\${1,2}(.+?)(?<!\\)\${1,2}")
_BROKEN_COMMANDS_RE = re.compile(
    r"\\(?:"  # literal backslash
    r"frrac|Frrac|"  # \frrac → typo of \frac
    r"sqr|Sqr|"  # \sqr → typo of \sqrt
    r"devide|Devide|"  # \devide → typo of \divide
    r"div|Div"  # \div in text (should not appear in Russian text)
    r")",
    re.IGNORECASE,
)
_BARE_FRAC_RE = re.compile(
    r"\\frac(?![{])"  # \frac not followed by {
)
_BARE_POWER_RE = re.compile(
    r"(?<=[\d)])\^(?![{])"  # 2^3 → should be 2^{3}
)
_UNBALANCED_BRACE_RE = re.compile(
    r"[{}]"  # count braces
)
_LATEX_MATH_ENV_RE = re.compile(
    r"(\\\(.*?\\\)|\\\[.*?\\\])", re.DOTALL
)


@dataclass
class LatexIssue:
    """Одна найденная проблема с LaTeX."""

    code: str
    severity: str  # "low" | "medium" | "high"
    message: str
    snippet: str = ""

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "snippet": self.snippet,
        }


@dataclass
class LatexValidationReport:
    """Отчёт валидации LaTeX."""

    issues: List[LatexIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "high" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(i.severity in ("medium", "low") for i in self.issues)

    def to_dict(self) -> dict:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "has_errors": self.has_errors,
        }


def _find_all_latex_spans(text: str) -> List[Tuple[int, int, str]]:
    """Найти все \(…\) и \[…\] span'ы.
    Возвращает список (start, end, type) где type='inline' или 'display'.
    """
    spans: List[Tuple[int, int, str]] = []
    for m in re.finditer(r"\\\((.+?)\\\)", text, re.DOTALL):
        spans.append((m.start(), m.end(), "inline"))
    for m in re.finditer(r"\\\[(.+?)\\\]", text, re.DOTALL):
        spans.append((m.start(), m.end(), "display"))
    spans.sort(key=lambda x: x[0])
    return spans


def validate_daily_task_latex(text: str) -> LatexValidationReport:
    """Строгая LaTeX-валидация для daily_tasks.

    Проверяет:
      - Нет $ … $ или $$ … $$ (только \(…\) / \[…\])
      - Нет сломанных команд (\frrac, \sqr, \devide)
      - Нет \frac без {}
      - Нет голых степеней 2^3 (должно быть 2^{3})
      - Сбалансированность фигурных скобок внутри math-окружений
      - Внутри math-окружений нет лишнего текста без LaTeX
    """
    report = LatexValidationReport()

    # 1. Запрещённые $ … $
    dollar_matches = list(_DEPRECATED_DOLLAR_RE.finditer(text))
    for m in dollar_matches:
        snippet = text[max(0, m.start() - 10) : m.end() + 10]
        report.issues.append(
            LatexIssue(
                code="deprecated_dollar",
                severity="high",
                message="Найден $…$ / $$…$$ вместо \(…\) / \[…\]",
                snippet=snippet,
            )
        )

    # 2. Сломанные команды
    broken_matches = list(_BROKEN_COMMANDS_RE.finditer(text))
    for m in broken_matches:
        snippet = text[max(0, m.start() - 5) : m.end() + 5]
        report.issues.append(
            LatexIssue(
                code="broken_command",
                severity="high",
                message=f"Сломанная LaTeX-команда: '{m.group()}'",
                snippet=snippet,
            )
        )

    # 3. \frac без {}
    bare_frac_matches = list(_BARE_FRAC_RE.finditer(text))
    for m in bare_frac_matches:
        snippet = text[max(0, m.start() - 5) : m.end() + 5]
        report.issues.append(
            LatexIssue(
                code="bare_frac",
                severity="high",
                message=r"\frac без { } — нужно \frac{}{}",
                snippet=snippet,
            )
        )

    # 4. Голые степени
    bare_power_matches = list(_BARE_POWER_RE.finditer(text))
    for m in bare_power_matches:
        snippet = text[max(0, m.start() - 5) : m.end() + 5]
        report.issues.append(
            LatexIssue(
                code="bare_power",
                severity="medium",
                message="Голая степень '^' без { } — нужно ^{...}",
                snippet=snippet,
            )
        )

    # 5. Сбалансированность {} внутри math-окружений
    spans = _find_all_latex_spans(text)
    for start, end, env_type in spans:
        inner = text[start:end]
        depth = 0
        for ch in inner:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if depth < 0:
                report.issues.append(
                    LatexIssue(
                        code="unbalanced_braces",
                        severity="high",
                        message=f"Несбалансированные {{}} внутри {env_type}-окружения",
                        snippet=inner[:80],
                    )
                )
                break
        if depth != 0:
            report.issues.append(
                LatexIssue(
                    code="unbalanced_braces",
                    severity="high",
                    message=f"Несбалансированные {{}} (глубина {depth}) внутри {env_type}-окружения",
                    snippet=inner[:80],
                )
            )

    return report


def auto_fix_latex(text: str) -> str:
    """Авто-фикс LaTeX для daily_tasks: $ → \(, $$ → \[ и т.д.

    Применяет те же исправления, что и services.task_validator.fix_latex,
    но с дополнительным акцентом на strict-режим.
    """
    # 1. $$ … $$ → \[ … \]
    text = re.sub(r"\$\$(.+?)\$\$", r"\\[\1\\]", text, flags=re.DOTALL)
    # 2. $ … $ → \( … \)
    text = re.sub(r"(?<!\\)\$(.+?)(?<!\\)\$", r"\\(\1\\)", text, flags=re.DOTALL)

    # 3. Двойной обратный слеш → одинарный (но не рушим \\\()
    text = re.sub(r"\\\\\\\\", r"\\\\", text)
    text = re.sub(r"(?<!\\\\)\\\\\\(?!\()", r"\\", text)

    # 4. \frrac → \frac
    text = re.sub(r"\\frrac", r"\\frac", text, flags=re.IGNORECASE)
    text = re.sub(r"\\sqr(?!t)", r"\\sqrt", text, flags=re.IGNORECASE)

    # 5. Буквенные степени → ^{...}
    text = re.sub(r"\^([a-zA-Zа-яА-Я])", r"^{\1}", text)

    # 6. \frac12 → \frac{1}{2}
    text = re.sub(r"\\frac(\d)(\d)", r"\\frac{\1}{\2}", text)

    # 7. Unicode math → LaTeX (основные символы)
    _UNICODE_MATH_MAP = {
        "√": r"\sqrt",
        "≥": r"\geq",
        "≤": r"\leq",
        "≠": r"\neq",
        "×": r"\times",
        "÷": r"\div",
        "±": r"\pm",
        "∞": r"\infty",
        "π": r"\pi",
        "α": r"\alpha",
        "β": r"\beta",
        "γ": r"\gamma",
        "Δ": r"\Delta",
        "δ": r"\delta",
        "θ": r"\theta",
        "λ": r"\lambda",
        "μ": r"\mu",
        "σ": r"\sigma",
        "∑": r"\sum",
        "∏": r"\prod",
        "∫": r"\int",
        "→": r"\rightarrow",
        "←": r"\leftarrow",
        "⇒": r"\Rightarrow",
        "⇔": r"\Leftrightarrow",
        "∈": r"\in",
        "∉": r"\notin",
        "⊂": r"\subset",
        "⊃": r"\supset",
        "⊆": r"\subseteq",
        "⊇": r"\supseteq",
        "∪": r"\cup",
        "∩": r"\cap",
        "∅": r"\emptyset",
        "∠": r"\angle",
        "⊥": r"\perp",
        "∥": r"\parallel",
        "∼": r"\sim",
        "≅": r"\cong",
        "≈": r"\approx",
        "≡": r"\equiv",
        "≢": r"\not\equiv",
        "⋅": r"\cdot",
        "°": r"^{\circ}",
    }
    for uni_char, latex_cmd in _UNICODE_MATH_MAP.items():
        text = text.replace(uni_char, latex_cmd)

    return text


# ──────────────────────────────────────────────
# 2.  JSON Schema-валидаторы для каждого шага
# ──────────────────────────────────────────────

# Допустимые значения
VALID_SLOT_KINDS = {"weak_base", "weak_main", "weak_challenge", "strong_review", "strong_challenge"}
VALID_SUBJECTS = {"algebra", "geometry", "number_theory", "combinatorics", "logic"}
VALID_DIFFICULTY_RANGE = (1, 8)
VALID_VERDICTS = {"approved", "needs_fix"}
VALID_SEVERITIES = {"low", "medium", "high"}
VALID_AUDIT_CODES = {
    "bad_latex",
    "too_easy",
    "too_hard",
    "impossible_task",
    "wrong_answer",
    "spec_mismatch",
    "duplicate_archetype",
    "low_solution_quality",
}

# Обязательные поля для каждого шага
GEMINI_SPEC_REQUIRED_FIELDS = {
    "position", "slot_kind", "subject", "topic", "subtopic",
    "difficulty_level", "task_archetype", "must_use_concepts",
    "must_avoid", "answer_form", "estimated_solve_minutes", "reason_for_student",
}
OPUS_TASK_REQUIRED_FIELDS = {"position", "task_text", "correct_answer", "solution", "hints"}
GPT_AUDIT_ENTRY_REQUIRED_FIELDS = {"position", "verdict", "issues"}
AUDIT_ISSUE_REQUIRED_FIELDS = {"code", "severity", "explanation", "fix_instruction"}


def _is_nonempty_string(val: Any) -> bool:
    return isinstance(val, str) and len(val.strip()) > 0


def _is_list_of_strings(val: Any) -> bool:
    return isinstance(val, list) and all(isinstance(v, str) for v in val)


def _extract_json_from_response(raw_response: str) -> Optional[dict]:
    """Извлечь JSON из сырого ответа LLM.

    Пытается найти JSON в ```json … ``` блоке, затем ищет первый { … }.
    Адаптировано из services/task_validator._extract_json_from_response.
    """
    if not raw_response or not raw_response.strip():
        return None

    text = raw_response.strip()

    # 0. PRE-CLEAN: убираем markdown-fence, если есть (даже без закрывающего)
    # LLM часто возвращают ```json\n{...}\n``` или просто ```\n{...}
    if text.startswith("```"):
        # Снимаем первую строку с fence
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :].strip()
        # Снимаем закрывающий fence, если есть
        if text.endswith("```"):
            text = text[:-3].strip()

    # 1. ```json … ``` (с закрывающим fence)
    json_block_match = re.search(
        r"```(?:json)?\s*\n?(.*?)\n?```", raw_response, re.DOTALL | re.IGNORECASE
    )
    if json_block_match:
        candidate = json_block_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 2. ``` … ``` (без json)
    code_block_match = re.search(r"```\s*\n?(.*?)\n?```", raw_response, re.DOTALL)
    if code_block_match:
        candidate = code_block_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 3. Первый { … }
    brace_start = text.find("{")
    if brace_start != -1:
        brace_depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                brace_depth += 1
            elif text[i] == "}":
                brace_depth -= 1
            if brace_depth == 0:
                candidate = text[brace_start : i + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    # Пробуем починить: убрать лишние запятые
                    try:
                        fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
                        return json.loads(fixed)
                    except json.JSONDecodeError:
                        pass
                    break  # не нашли валидный JSON

    return None


def _truncate_for_log(data: Any, max_len: int = 200) -> str:
    """Обрезать данные для логирования."""
    s = json.dumps(data, ensure_ascii=False, default=str)
    if len(s) > max_len:
        return s[:max_len] + "..."
    return s


# ─── Gemini Plan ──────────────────────────────


@dataclass
class GeminiSpecValidation:
    """Результат валидации одного spec'а от Gemini."""

    position: int
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "position": self.position,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class GeminiPlanValidation:
    """Результат валидации всего ответа Gemini."""

    valid: bool
    entries: List[GeminiSpecValidation] = field(default_factory=list)
    global_errors: List[str] = field(default_factory=list)

    @property
    def all_errors(self) -> List[str]:
        errs = list(self.global_errors)
        for e in self.entries:
            errs.extend(e.errors)
        return errs

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "global_errors": self.global_errors,
            "entries": [e.to_dict() for e in self.entries],
        }


def validate_gemini_plan(raw_response: str) -> GeminiPlanValidation:
    """Валидировать ответ Gemini (шаг 1: планирование 10 spec'ов)."""
    result = GeminiPlanValidation(valid=False)

    data = _extract_json_from_response(raw_response)
    if data is None:
        result.global_errors.append("Не удалось извлечь JSON из ответа Gemini")
        return result

    # Проверяем структуру верхнего уровня
    if not isinstance(data, dict):
        result.global_errors.append("Ответ Gemini не является JSON-объектом")
        return result

    specs = data.get("specs")
    if specs is None:
        result.global_errors.append('Отсутствует ключ "specs" в ответе Gemini')
        return result

    if not isinstance(specs, list):
        result.global_errors.append('"specs" не является массивом')
        return result

    if len(specs) != 10:
        result.global_errors.append(
            f'"specs" содержит {len(specs)} элементов, ожидалось 10'
        )
        # Продолжаем проверку с тем, что есть

    seen_positions: set = set()
    seen_topic_subtopic: set = set()

    for i, spec in enumerate(specs):
        entry = GeminiSpecValidation(position=i + 1, valid=True)

        if not isinstance(spec, dict):
            entry.valid = False
            entry.errors.append(f"spec[{i}] не является объектом")
            result.entries.append(entry)
            continue

        # Проверка обязательных полей
        missing = GEMINI_SPEC_REQUIRED_FIELDS - set(spec.keys())
        if missing:
            entry.valid = False
            entry.errors.append(f"Отсутствуют поля: {', '.join(sorted(missing))}")

        # position
        pos = spec.get("position")
        if pos is None:
            entry.errors.append("Отсутствует position")
            entry.valid = False
        elif not isinstance(pos, int) or pos < 1 or pos > 10:
            entry.errors.append(f"position={pos} вне диапазона 1..10")
            entry.valid = False
        elif pos in seen_positions:
            entry.errors.append(f"Дубликат position={pos}")
            entry.valid = False
        else:
            seen_positions.add(pos)

        # slot_kind
        slot_kind = spec.get("slot_kind")
        if slot_kind is not None and slot_kind not in VALID_SLOT_KINDS:
            entry.errors.append(
                f"slot_kind='{slot_kind}' недопустим (допустимые: {', '.join(sorted(VALID_SLOT_KINDS))})"
            )
            entry.valid = False

        # subject
        subject = spec.get("subject")
        if subject is not None and subject not in VALID_SUBJECTS:
            entry.warnings.append(
                f"subject='{subject}' не входит в известный список {sorted(VALID_SUBJECTS)}"
            )

        # topic + subtopic — проверка на уникальность
        topic = spec.get("topic")
        subtopic = spec.get("subtopic")
        if topic and subtopic:
            ts_key = f"{topic}::{subtopic}"
            if ts_key in seen_topic_subtopic:
                entry.warnings.append(
                    f"Дубликат (topic, subtopic) = ('{topic}', '{subtopic}')"
                )
            else:
                seen_topic_subtopic.add(ts_key)

        # difficulty_level
        diff = spec.get("difficulty_level")
        if diff is not None:
            if not isinstance(diff, int) or diff < VALID_DIFFICULTY_RANGE[0] or diff > VALID_DIFFICULTY_RANGE[1]:
                entry.errors.append(
                    f"difficulty_level={diff} вне диапазона {VALID_DIFFICULTY_RANGE}"
                )
                entry.valid = False

        # must_use_concepts
        muc = spec.get("must_use_concepts")
        if muc is not None and not _is_list_of_strings(muc):
            entry.errors.append("must_use_concepts должен быть списком строк")
            entry.valid = False

        # must_avoid
        ma = spec.get("must_avoid")
        if ma is not None and not _is_list_of_strings(ma):
            entry.errors.append("must_avoid должен быть списком строк")
            entry.valid = False

        # answer_form
        af = spec.get("answer_form")
        if af is not None and not _is_nonempty_string(af):
            entry.errors.append("answer_form должен быть непустой строкой")
            entry.valid = False

        # estimated_solve_minutes
        esm = spec.get("estimated_solve_minutes")
        if esm is not None:
            if not isinstance(esm, (int, float)) or esm < 1 or esm > 60:
                entry.warnings.append(f"estimated_solve_minutes={esm} выглядит подозрительно (обычно 1..60)")

        # reason_for_student
        rfs = spec.get("reason_for_student")
        if rfs is not None and not _is_nonempty_string(rfs):
            entry.errors.append("reason_for_student должен быть непустой строкой")
            entry.valid = False

        # task_archetype
        ta = spec.get("task_archetype")
        if ta is not None and not _is_nonempty_string(ta):
            entry.errors.append("task_archetype должен быть непустой строкой")
            entry.valid = False

        result.entries.append(entry)

    result.valid = all(e.valid for e in result.entries) and len(result.global_errors) == 0
    return result


# ─── Opus Generation ──────────────────────────


@dataclass
class OpusTaskValidation:
    """Результат валидации одной задачи от Opus."""

    position: int
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    latex_report: Optional[LatexValidationReport] = None

    def to_dict(self) -> dict:
        return {
            "position": self.position,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "latex_report": self.latex_report.to_dict() if self.latex_report else None,
        }


@dataclass
class OpusGenerationValidation:
    """Результат валидации всего ответа Opus."""

    valid: bool
    entries: List[OpusTaskValidation] = field(default_factory=list)
    global_errors: List[str] = field(default_factory=list)

    @property
    def all_errors(self) -> List[str]:
        errs = list(self.global_errors)
        for e in self.entries:
            errs.extend(e.errors)
        return errs

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "global_errors": self.global_errors,
            "entries": [e.to_dict() for e in self.entries],
        }


def validate_opus_generation(raw_response: str) -> OpusGenerationValidation:
    """Валидировать ответ Opus (шаг 2: генерация 10 задач)."""
    result = OpusGenerationValidation(valid=False)

    data = _extract_json_from_response(raw_response)
    if data is None:
        result.global_errors.append("Не удалось извлечь JSON из ответа Opus")
        return result

    if not isinstance(data, dict):
        result.global_errors.append("Ответ Opus не является JSON-объектом")
        return result

    tasks = data.get("tasks")
    if tasks is None:
        result.global_errors.append('Отсутствует ключ "tasks" в ответе Opus')
        return result

    if not isinstance(tasks, list):
        result.global_errors.append('"tasks" не является массивом')
        return result

    if len(tasks) != 10:
        result.global_errors.append(
            f'"tasks" содержит {len(tasks)} элементов, ожидалось 10'
        )

    seen_positions: set = set()

    for i, task in enumerate(tasks):
        entry = OpusTaskValidation(position=i + 1, valid=True)

        if not isinstance(task, dict):
            entry.valid = False
            entry.errors.append(f"tasks[{i}] не является объектом")
            result.entries.append(entry)
            continue

        missing = OPUS_TASK_REQUIRED_FIELDS - set(task.keys())
        if missing:
            entry.valid = False
            entry.errors.append(f"Отсутствуют поля: {', '.join(sorted(missing))}")

        # position
        pos = task.get("position")
        if pos is None:
            entry.errors.append("Отсутствует position")
            entry.valid = False
        elif not isinstance(pos, int) or pos < 1 or pos > 10:
            entry.errors.append(f"position={pos} вне диапазона 1..10")
            entry.valid = False
        elif pos in seen_positions:
            entry.errors.append(f"Дубликат position={pos}")
            entry.valid = False
        else:
            seen_positions.add(pos)

        # task_text — обязательное непустое
        task_text = task.get("task_text")
        if task_text is not None:
            if not _is_nonempty_string(task_text):
                entry.errors.append("task_text пуст или не строка")
                entry.valid = False
            else:
                # LaTeX-валидация текста задачи
                latex_report = validate_daily_task_latex(task_text)
                entry.latex_report = latex_report
                if latex_report.has_errors:
                    entry.errors.append(
                        f"LaTeX ошибки: {[i.code for i in latex_report.issues if i.severity == 'high']}"
                    )
                    entry.valid = False
                if latex_report.has_warnings:
                    entry.warnings.append(
                        f"LaTeX предупреждения: {[i.code for i in latex_report.issues if i.severity != 'high']}"
                    )
        else:
            entry.errors.append("Отсутствует task_text")
            entry.valid = False

        # correct_answer
        ca = task.get("correct_answer")
        if ca is not None and not _is_nonempty_string(str(ca)):
            entry.errors.append("correct_answer пуст или не строка")
            entry.valid = False

        # solution
        solution = task.get("solution")
        if solution is not None and not _is_nonempty_string(str(solution)):
            entry.errors.append("solution пуст или не строка")
            entry.valid = False

        # hints — массив из 1-3 строк
        hints = task.get("hints")
        if hints is not None:
            if not isinstance(hints, list):
                entry.errors.append("hints должен быть массивом")
                entry.valid = False
            elif len(hints) < 1 or len(hints) > 3:
                entry.warnings.append(f"hints содержит {len(hints)} элементов (ожидалось 1-3)")
            else:
                if not all(isinstance(h, str) for h in hints):
                    entry.errors.append("Все hints должны быть строками")
                    entry.valid = False

        result.entries.append(entry)

    result.valid = all(e.valid for e in result.entries) and len(result.global_errors) == 0
    return result


# ─── GPT Audit ────────────────────────────────


@dataclass
class AuditIssueValidation:
    """Результат валидации одной issues в аудите."""

    valid: bool
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"valid": self.valid, "errors": self.errors}


@dataclass
class AuditEntryValidation:
    """Результат валидации одной записи аудита."""

    position: int
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    issues_validation: List[AuditIssueValidation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "position": self.position,
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "issues_validation": [iv.to_dict() for iv in self.issues_validation],
        }


@dataclass
class GPTAuditValidation:
    """Результат валидации всего ответа GPT-аудита."""

    valid: bool
    entries: List[AuditEntryValidation] = field(default_factory=list)
    global_errors: List[str] = field(default_factory=list)

    @property
    def all_errors(self) -> List[str]:
        errs = list(self.global_errors)
        for e in self.entries:
            errs.extend(e.errors)
        return errs

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "global_errors": self.global_errors,
            "entries": [e.to_dict() for e in self.entries],
        }


def validate_gpt_audit(raw_response: str) -> GPTAuditValidation:
    """Валидировать ответ GPT-аудита (шаг 3)."""
    result = GPTAuditValidation(valid=False)

    data = _extract_json_from_response(raw_response)
    if data is None:
        result.global_errors.append("Не удалось извлечь JSON из ответа GPT-аудита")
        return result

    if not isinstance(data, dict):
        result.global_errors.append("Ответ GPT-аудита не является JSON-объектом")
        return result

    audit = data.get("audit")
    if audit is None:
        result.global_errors.append('Отсутствует ключ "audit" в ответе GPT')
        return result

    if not isinstance(audit, list):
        result.global_errors.append('"audit" не является массивом')
        return result

    # NB: validate_gpt_audit вызывается per-batch (1..N items) с тех пор как
    # Step 3 распараллелен на 5 воркеров. Жёсткое требование "==10" ломало
    # каждый batch (где их по 2). Теперь принимаем 1..10 включительно —
    # cross-validation (полная сумма по позициям) делается в orchestrator-е.
    if len(audit) < 1 or len(audit) > 10:
        result.global_errors.append(
            f'"audit" содержит {len(audit)} элементов, ожидалось 1..10'
        )

    seen_positions: set = set()

    for i, entry_data in enumerate(audit):
        entry = AuditEntryValidation(position=i + 1, valid=True)

        if not isinstance(entry_data, dict):
            entry.valid = False
            entry.errors.append(f"audit[{i}] не является объектом")
            result.entries.append(entry)
            continue

        missing = GPT_AUDIT_ENTRY_REQUIRED_FIELDS - set(entry_data.keys())
        if missing:
            entry.valid = False
            entry.errors.append(f"Отсутствуют поля: {', '.join(sorted(missing))}")

        # position
        pos = entry_data.get("position")
        if pos is None:
            entry.errors.append("Отсутствует position")
            entry.valid = False
        elif not isinstance(pos, int) or pos < 1 or pos > 10:
            entry.errors.append(f"position={pos} вне диапазона 1..10")
            entry.valid = False
        elif pos in seen_positions:
            entry.errors.append(f"Дубликат position={pos}")
            entry.valid = False
        else:
            seen_positions.add(pos)

        # verdict
        verdict = entry_data.get("verdict")
        if verdict is not None and verdict not in VALID_VERDICTS:
            entry.errors.append(
                f"verdict='{verdict}' недопустим (допустимые: {', '.join(sorted(VALID_VERDICTS))})"
            )
            entry.valid = False

        # issues
        issues = entry_data.get("issues")
        if issues is not None:
            if not isinstance(issues, list):
                entry.errors.append("issues должен быть массивом")
                entry.valid = False
            else:
                if verdict == "approved" and len(issues) > 0:
                    entry.warnings.append(
                        f"verdict='approved', но issues содержит {len(issues)} проблем"
                    )
                for j, iss in enumerate(issues):
                    iss_val = AuditIssueValidation(valid=True)
                    if not isinstance(iss, dict):
                        iss_val.valid = False
                        iss_val.errors.append(f"issues[{j}] не является объектом")
                    else:
                        iss_missing = AUDIT_ISSUE_REQUIRED_FIELDS - set(iss.keys())
                        if iss_missing:
                            iss_val.valid = False
                            iss_val.errors.append(
                                f"Отсутствуют поля: {', '.join(sorted(iss_missing))}"
                            )
                        # code
                        code = iss.get("code")
                        if code is not None and code not in VALID_AUDIT_CODES:
                            entry.warnings.append(
                                f"Неизвестный код ошибки: '{code}'"
                            )
                        # severity
                        sev = iss.get("severity")
                        if sev is not None and sev not in VALID_SEVERITIES:
                            entry.warnings.append(
                                f"Неизвестный severity: '{sev}'"
                            )
                    entry.issues_validation.append(iss_val)

        result.entries.append(entry)

    result.valid = all(e.valid for e in result.entries) and len(result.global_errors) == 0
    return result


# ─── Opus Fix ─────────────────────────────────


@dataclass
class OpusFixValidation:
    """Результат валидации ответа Opus-fix (шаг 4 / итерация fix)."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    latex_report: Optional[LatexValidationReport] = None
    fixed_position: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "latex_report": self.latex_report.to_dict() if self.latex_report else None,
            "fixed_position": self.fixed_position,
        }


def validate_opus_fix(raw_response: str) -> OpusFixValidation:
    """Валидировать ответ Opus-fix (исправление одной задачи)."""
    result = OpusFixValidation(valid=False)

    data = _extract_json_from_response(raw_response)
    if data is None:
        result.errors.append("Не удалось извлечь JSON из ответа Opus-fix")
        return result

    if not isinstance(data, dict):
        result.errors.append("Ответ Opus-fix не является JSON-объектом")
        return result

    # Может быть либо объект задачи напрямую, либо {"task": {...}}
    task = data.get("task", data)

    if not isinstance(task, dict):
        result.errors.append("task не является объектом")
        return result

    missing = OPUS_TASK_REQUIRED_FIELDS - set(task.keys())
    if missing:
        result.errors.append(f"Отсутствуют поля: {', '.join(sorted(missing))}")

    # position
    pos = task.get("position")
    if pos is not None:
        if not isinstance(pos, int) or pos < 1 or pos > 10:
            result.errors.append(f"position={pos} вне диапазона 1..10")
        else:
            result.fixed_position = pos

    # task_text — LaTeX-валидация
    task_text = task.get("task_text")
    if task_text is not None:
        if not _is_nonempty_string(task_text):
            result.errors.append("task_text пуст или не строка")
        else:
            latex_report = validate_daily_task_latex(task_text)
            result.latex_report = latex_report
            if latex_report.has_errors:
                result.errors.append(
                    f"LaTeX ошибки: {[i.code for i in latex_report.issues if i.severity == 'high']}"
                )
            if latex_report.has_warnings:
                result.warnings.append(
                    f"LaTeX предупреждения: {[i.code for i in latex_report.issues if i.severity != 'high']}"
                )
    else:
        result.errors.append("Отсутствует task_text")

    # correct_answer
    ca = task.get("correct_answer")
    if ca is not None and not _is_nonempty_string(str(ca)):
        result.errors.append("correct_answer пуст или не строка")

    # solution
    solution = task.get("solution")
    if solution is not None and not _is_nonempty_string(str(solution)):
        result.errors.append("solution пуст или не строка")

    # hints
    hints = task.get("hints")
    if hints is not None:
        if not isinstance(hints, list):
            result.errors.append("hints должен быть массивом")
        elif len(hints) < 1 or len(hints) > 3:
            result.warnings.append(f"hints содержит {len(hints)} элементов (ожидалось 1-3)")
        elif not all(isinstance(h, str) for h in hints):
            result.errors.append("Все hints должны быть строками")

    result.valid = len(result.errors) == 0
    return result


# ──────────────────────────────────────────────
# 3.  Кросс-валидация
# ──────────────────────────────────────────────


@dataclass
class CrossValidationResult:
    """Результат кросс-валидации spec ↔ task ↔ audit."""

    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def cross_validate_specs_and_tasks(
    specs: List[dict],
    tasks: List[dict],
) -> CrossValidationResult:
    """Сверить spec'ы с сгенерированными задачами.

    Проверяет:
      - Каждому spec'у соответствует задача с тем же position
      - Количество spec'ов == количеству задач
    """
    result = CrossValidationResult(valid=True)

    if not specs or not tasks:
        result.errors.append("specs или tasks пусты")
        result.valid = False
        return result

    spec_by_pos: Dict[int, dict] = {}
    for s in specs:
        p = s.get("position")
        if p is not None:
            spec_by_pos[p] = s

    task_by_pos: Dict[int, dict] = {}
    for t in tasks:
        p = t.get("position")
        if p is not None:
            task_by_pos[p] = t

    # Проверяем, что каждый position из spec'ов есть в задачах
    for pos in spec_by_pos:
        if pos not in task_by_pos:
            result.errors.append(f"Нет задачи для position={pos}")
            result.valid = False

    # И наоборот
    for pos in task_by_pos:
        if pos not in spec_by_pos:
            result.warnings.append(f"Нет spec'а для position={pos} (лишняя задача)")

    return result


def cross_validate_audit_with_specs(
    audit_entries: List[dict],
    specs: List[dict],
) -> CrossValidationResult:
    """Сверить audit-записи с spec'ами.

    Проверяет:
      - Аудированы все position'ы из spec'ов
      - Не аудированы лишние position'ы
    """
    result = CrossValidationResult(valid=True)

    if not audit_entries or not specs:
        result.errors.append("audit_entries или specs пусты")
        result.valid = False
        return result

    spec_positions = {s.get("position") for s in specs if s.get("position") is not None}
    audit_positions = {a.get("position") for a in audit_entries if a.get("position") is not None}

    missing = spec_positions - audit_positions
    if missing:
        result.errors.append(
            f"Не проаудированы position'ы: {sorted(missing)}"
        )
        result.valid = False

    extra = audit_positions - spec_positions
    if extra:
        result.warnings.append(
            f"Лишние position'ы в аудите (нет в spec'ах): {sorted(extra)}"
        )

    return result


def cross_validate_all(
    specs: List[dict],
    tasks: List[dict],
    audit_entries: Optional[List[dict]] = None,
) -> CrossValidationResult:
    """Полная кросс-валидация всех трёх массивов.

    Если audit_entries == None, проверка аудита пропускается.
    """
    result = CrossValidationResult(valid=True)

    # 1. Specs ↔ Tasks
    st = cross_validate_specs_and_tasks(specs, tasks)
    result.errors.extend(st.errors)
    result.warnings.extend(st.warnings)
    if not st.valid:
        result.valid = False

    # 2. Audit ↔ Specs (пропускаем, если аудит не проводился)
    if audit_entries is not None:
        audit_check = cross_validate_audit_with_specs(audit_entries, specs)
        result.errors.extend(audit_check.errors)
        result.warnings.extend(audit_check.warnings)
        if not audit_check.valid:
            result.valid = False

    return result


# ──────────────────────────────────────────────
# 4.  Валидация pipeline — полный цикл
# ──────────────────────────────────────────────


@dataclass
class PipelineValidationResult:
    """Сводный результат валидации всего pipeline."""

    valid: bool
    gemini: GeminiPlanValidation
    opus: OpusGenerationValidation
    gpt_audit: Optional[GPTAuditValidation] = None
    opus_fix: Optional[OpusFixValidation] = None
    cross: Optional[CrossValidationResult] = None

    def to_dict(self) -> dict:
        d: dict = {
            "valid": self.valid,
            "gemini": self.gemini.to_dict(),
            "opus": self.opus.to_dict(),
        }
        if self.gpt_audit:
            d["gpt_audit"] = self.gpt_audit.to_dict()
        if self.opus_fix:
            d["opus_fix"] = self.opus_fix.to_dict()
        if self.cross:
            d["cross"] = self.cross.to_dict()
        return d


def validate_full_pipeline(
    gemini_response: str,
    opus_response: str,
    gpt_audit_response: Optional[str] = None,
    opus_fix_response: Optional[str] = None,
) -> PipelineValidationResult:
    """Полная валидация всего pipeline — от Gemini до фикса.

    Выполняет:
      1. Валидацию Gemini plan
      2. Валидацию Opus generation
      3. Валидацию GPT audit (если передан)
      4. Валидацию Opus fix (если передан)
      5. Кросс-валидацию
    """
    gemini_result = validate_gemini_plan(gemini_response)
    opus_result = validate_opus_generation(opus_response)

    result = PipelineValidationResult(
        valid=True,
        gemini=gemini_result,
        opus=opus_result,
    )

    if not gemini_result.valid or not opus_result.valid:
        result.valid = False
        # Продолжаем, чтобы собрать все ошибки

    # Извлекаем данные для кросс-валидации
    gemini_data = _extract_json_from_response(gemini_response)
    opus_data = _extract_json_from_response(opus_response)
    specs = (gemini_data or {}).get("specs", []) if gemini_data else []
    tasks = (opus_data or {}).get("tasks", []) if opus_data else []

    # GPT audit
    if gpt_audit_response:
        gpt_result = validate_gpt_audit(gpt_audit_response)
        result.gpt_audit = gpt_result
        if not gpt_result.valid:
            result.valid = False

    # Opus fix
    if opus_fix_response:
        fix_result = validate_opus_fix(opus_fix_response)
        result.opus_fix = fix_result
        if not fix_result.valid:
            result.valid = False

    # Cross-validation — only include audit if response was provided
    if gpt_audit_response:
        gpt_data = _extract_json_from_response(gpt_audit_response)
        audit_entries = (gpt_data or {}).get("audit", []) if gpt_data else []
    else:
        audit_entries = None

    cross = cross_validate_all(specs, tasks, audit_entries)
    result.cross = cross
    if not cross.valid:
        result.valid = False

    return result


# ──────────────────────────────────────────────
# 5.  Утилиты
# ──────────────────────────────────────────────


def extract_json_safe(raw_response: str) -> Optional[dict]:
    """Безопасное извлечение JSON (обёртка над _extract_json_from_response).

    Возвращает None при любой ошибке.
    """
    try:
        return _extract_json_from_response(raw_response)
    except Exception as exc:
        logger.warning("extract_json_safe: %s", exc)
        return None


def has_solution_leak(task_text: str, correct_answer: str) -> Tuple[bool, str]:
    """Проверить, не содержит ли условие задачи верный ответ.

    Упрощённая версия — проверяет вхождение correct_answer в task_text.
    Возвращает (True, snippet) если найден, иначе (False, "").
    """
    if not task_text or not correct_answer:
        return False, ""

    answer_clean = correct_answer.strip().lower()
    text_lower = task_text.lower()

    # Не проверяем односимвольные ответы (буквы, цифры) — слишком много ложных срабатываний
    if len(answer_clean) <= 2:
        return False, ""

    if answer_clean in text_lower:
        idx = text_lower.index(answer_clean)
        start = max(0, idx - 20)
        end = min(len(task_text), idx + len(answer_clean) + 20)
        snippet = task_text[start:end]
        return True, snippet

    return False, ""


def validate_all_task_texts_latex(tasks: List[dict]) -> Dict[int, LatexValidationReport]:
    """Проверить LaTeX во всех задачах сразу.

    Возвращает dict {position: LatexValidationReport}.
    """
    reports: Dict[int, LatexValidationReport] = {}
    for task in tasks:
        if not isinstance(task, dict):
            continue
        pos = task.get("position")
        text = task.get("task_text", "")
        if pos is not None and text:
            reports[pos] = validate_daily_task_latex(text)
    return reports
