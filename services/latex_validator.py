# -*- coding: utf-8 -*-
r"""
LaTeX-валидатор и нормализатор для текста задач.

Назначение
==========
Не дать «сломанным» формулам долететь до пользователя. Раньше встречались
такие проблемы:

  * «7^100» без `$...$` и без `{}` -> отображается как «7^100» (буквально).
  * `7^{100}` без `$...$` -> KaTeX/MathJax не подхватывают.
  * `\frac12` (без фигурных скобок) -> не парсится корректно.
  * Незакрытые `{` или `\(` `\)`.
  * Нечётное число `$` — следующий блок «утекает» в math-режим до конца строки.
  * OCR-артефакты: `x2 + y2 = z2`, `2cdot3` без `\`.

Этот модуль:
  1) `normalize_math_text(text)` — мягкая авто-починка типичных случаев
     (для пайплайна Daily Quest перед сохранением задачи).
  2) `validate_math_text(text)` — возвращает список структурированных
     предупреждений, чтобы пайплайн мог отбраковать совсем плохую задачу.
  3) `is_safe_for_users(text)` — короткое «можно показывать пользователю?».

Все функции чистые (no side-effects) и не требуют Flask/БД.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# Регулярки
# ──────────────────────────────────────────────────────────────────────────────

# Голая степень с многосимвольным показателем: "7^100", "x^25", "n^2024"
# Это самый критичный случай (KaTeX/MathJax вне $...$ просто покажет «7^100»).
_BARE_POWER_MULTI = re.compile(
    r'(?<![\\${\w])'                    # перед — не \, не $, не {, не буква
    r'([A-Za-zА-Яа-я0-9])'              # основание (1 символ)
    r'\^'                               # знак степени
    r'(\d{2,})'                         # 2+ цифр в показателе
    r'(?![A-Za-z0-9])'                  # после — не буква/цифра
)
# Одиночная степень: "x^2", "a^7" — оборачиваем в $...$, чтобы корректно
# отрисовалось. Применяется ПОСЛЕ multi, поэтому "7^100" уже обёрнуто.
_BARE_POWER_SINGLE_IN_TEXT = re.compile(
    r'(?<![\\${\w])'
    r'([A-Za-zА-Яа-я])\^([A-Za-z0-9])'  # ограничиваем основание буквой:
                                        # цифры (7^2) встречаются как «во 2-й степени»
                                        # и часто не нужны как формула.
)

# Голый \frac без $...$
_BARE_FRAC = re.compile(r'(?<!\$)(?<!\\)\\frac\b')

# \frac12 (без фигурных скобок) → \frac{1}{2}
_FRAC_NOBRACES = re.compile(r'\\frac\s*([0-9A-Za-z])\s*([0-9A-Za-z])(?![A-Za-z0-9{])')

# OCR-артефакт «cdot» без обратного слэша
_BARE_CDOT = re.compile(r'(?<![\\A-Za-z])cdot(?![A-Za-z])')
_BARE_TIMES = re.compile(r'(?<![\\A-Za-z])times(?![A-Za-z])')
_BARE_LDOTS = re.compile(r'(?<![\\A-Za-z])ldots(?![A-Za-z])')

# Закрытые LaTeX-блоки $...$  /  $$...$$  /  \(...\)  /  \[...\]
_MATH_SEG = re.compile(
    r'(\$\$[\s\S]+?\$\$|\$[^\$\n]+?\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])'
)


# ──────────────────────────────────────────────────────────────────────────────
# Структура отчёта
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class LatexIssue:
    """Одна найденная проблема."""
    code: str          # короткий код, например 'unbalanced_dollar'
    severity: str      # 'error' | 'warning' | 'info'
    message: str       # человекочитаемое сообщение
    snippet: str = ''  # фрагмент исходного текста

    def to_dict(self) -> dict:
        return {
            'code': self.code,
            'severity': self.severity,
            'message': self.message,
            'snippet': self.snippet[:200],
        }


@dataclass
class LatexReport:
    """Отчёт валидатора."""
    issues: List[LatexIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(i.severity == 'error' for i in self.issues)

    def to_dict(self) -> dict:
        return {
            'has_errors': self.has_errors,
            'issues': [i.to_dict() for i in self.issues],
        }


# ──────────────────────────────────────────────────────────────────────────────
# Сегменты «вне математики»
# ──────────────────────────────────────────────────────────────────────────────

def _split_math_and_text(text: str) -> List[Tuple[str, bool]]:
    """Возвращает список [(segment, is_math), ...] по тексту.

    Внутри math-сегментов мы НЕ трогаем (это уже валидный LaTeX, либо
    пользователь поправит вручную).
    """
    if not text:
        return []
    parts = _MATH_SEG.split(text)
    out: List[Tuple[str, bool]] = []
    for i, p in enumerate(parts):
        if not p:
            continue
        out.append((p, i % 2 == 1))
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Нормализация (мягкая авто-починка)
# ──────────────────────────────────────────────────────────────────────────────

def normalize_math_text(text: str) -> str:
    """Мягко чинит типичные проблемы LaTeX в тексте задач.

    Безопасно идемпотентно: повторный вызов не ухудшает результат.
    """
    if not text:
        return text

    segments = _split_math_and_text(text)
    out: List[str] = []
    for seg, is_math in segments:
        if is_math:
            # Внутри math: нормализуем \frac12 → \frac{1}{2}
            seg = _FRAC_NOBRACES.sub(r'\\frac{\1}{\2}', seg)
            # и канонизируем корни (\sqrt[3] X → \sqrt[3]{X}, ∛ → \sqrt[3]{...},
            # ^{3}\sqrt{...} → \sqrt[3]{...}). Безопасно для корректных формул
            # и идемпотентно — инцидент 2026-06-11 (задача G6.17).
            try:
                from services.latex_root_normalizer import normalize_roots
                seg = normalize_roots(seg)
            except Exception:
                pass
            out.append(seg)
            continue

        # 1. «7^100» (≥2 цифр без {}) → «$7^{100}$»
        seg = _BARE_POWER_MULTI.sub(lambda m: f'${m.group(1)}^{{{m.group(2)}}}$', seg)

        # 2. «x^2» одиночный в тексте → «$x^2$» (только если рядом нет $)
        seg = _BARE_POWER_SINGLE_IN_TEXT.sub(
            lambda m: f'${m.group(1)}^{m.group(2)}$', seg
        )

        # 3. cdot / times / ldots без \
        seg = _BARE_CDOT.sub(r'\\cdot', seg)
        seg = _BARE_TIMES.sub(r'\\times', seg)
        seg = _BARE_LDOTS.sub(r'\\ldots', seg)

        # 4. голый \frac → обернём в $...$ (берём до следующей пробельной/конца строки)
        if _BARE_FRAC.search(seg):
            seg = re.sub(
                r'(\\frac\{[^{}]*\}\{[^{}]*\})',
                r'$\1$',
                seg,
            )

        # 5. \frac12 (две одиночные цифры/буквы) → \frac{1}{2}
        seg = _FRAC_NOBRACES.sub(r'\\frac{\1}{\2}', seg)

        out.append(seg)

    return ''.join(out)


# ──────────────────────────────────────────────────────────────────────────────
# Валидация (структура отчётов)
# ──────────────────────────────────────────────────────────────────────────────

def validate_math_text(text: str) -> LatexReport:
    """Анализирует текст и возвращает структурированный отчёт о проблемах."""
    report = LatexReport()
    if not text:
        return report

    # 1. Нечётное число $ (учитываем экранированный \$)
    raw = re.sub(r'\\\$', '', text)
    dollar_count = raw.count('$$') * 2 + (raw.count('$') - raw.count('$$') * 2)
    if (raw.count('$') - raw.count('$$') * 2) % 2 != 0:
        report.issues.append(LatexIssue(
            code='unbalanced_dollar',
            severity='error',
            message='Нечётное число $ — формула не закрыта.',
            snippet=text[:160],
        ))

    # 2. Несбалансированные \( \)  и \[ \]
    if text.count(r'\(') != text.count(r'\)'):
        report.issues.append(LatexIssue(
            code='unbalanced_paren_math',
            severity='error',
            message=r'Несбалансированные \( и \).',
            snippet=text[:160],
        ))
    if text.count(r'\[') != text.count(r'\]'):
        report.issues.append(LatexIssue(
            code='unbalanced_bracket_math',
            severity='error',
            message=r'Несбалансированные \[ и \].',
            snippet=text[:160],
        ))

    # 3. Несбалансированные { } (грубая проверка — без учёта экранированных)
    open_b = len(re.findall(r'(?<!\\)\{', text))
    close_b = len(re.findall(r'(?<!\\)\}', text))
    if open_b != close_b:
        report.issues.append(LatexIssue(
            code='unbalanced_braces',
            severity='error',
            message=f'Несбалансированные фигурные скобки: {{={open_b}, }}={close_b}.',
            snippet=text[:160],
        ))

    # 4. Голая степень вида «7^100» в тексте (не внутри $...$)
    for seg, is_math in _split_math_and_text(text):
        if is_math:
            continue
        m = _BARE_POWER_MULTI.search(seg)
        if m:
            report.issues.append(LatexIssue(
                code='bare_power',
                severity='warning',
                message=(
                    f'Голая степень «{m.group(0)}» вне $...$. '
                    'Будет отображаться буквально (как 7^100).'
                ),
                snippet=seg[max(0, m.start() - 20):m.end() + 20],
            ))
            break  # одного достаточно для отчёта по типу

    # 5. Голый \frac вне math
    for seg, is_math in _split_math_and_text(text):
        if is_math:
            continue
        if _BARE_FRAC.search(seg):
            report.issues.append(LatexIssue(
                code='bare_frac',
                severity='warning',
                message=r'Команда \frac вне $...$ — KaTeX не сработает.',
                snippet=seg[:160],
            ))
            break

    return report


def is_safe_for_users(text: str) -> bool:
    """True, если задачу безопасно показывать пользователю.

    Считаем безопасной, если нет `error`-проблем. `warning` допустимы:
    их вычистит `normalize_math_text` при пост-обработке.
    """
    return not validate_math_text(text).has_errors


# ──────────────────────────────────────────────────────────────────────────────
# Высокоуровневая обёртка: нормализуй + валидируй
# ──────────────────────────────────────────────────────────────────────────────

def sanitize_for_render(text: str) -> Tuple[str, LatexReport]:
    """Нормализует текст и возвращает (исправленный_текст, отчёт_о_проблемах).

    Используй это в:
      * пайплайне Daily Quest перед сохранением задачи;
      * админских инструментах проверки;
      * Jinja-фильтре перед отдачей пользователю.
    """
    if not text:
        return text, LatexReport()
    fixed = normalize_math_text(text)
    report = validate_math_text(fixed)
    return fixed, report


# ──────────────────────────────────────────────────────────────────────────────
# Совместимость со старым API services/prep_planner.py
# ──────────────────────────────────────────────────────────────────────────────

def is_task_text_renderable(text: str) -> Tuple[bool, List[str]]:
    """Старое API, ожидаемое prep_planner.py.

    Возвращает (ok, reasons), где reasons — список человекочитаемых причин,
    почему текст НЕ годится. Сейчас «годится» = нет error-issues.
    """
    if not text:
        return False, ['empty']
    report = validate_math_text(text)
    if report.has_errors:
        reasons = [i.message for i in report.issues if i.severity == 'error']
        return False, reasons or ['unknown_error']
    return True, []


__all__ = [
    'LatexIssue',
    'LatexReport',
    'normalize_math_text',
    'validate_math_text',
    'is_safe_for_users',
    'sanitize_for_render',
    'is_task_text_renderable',
]
