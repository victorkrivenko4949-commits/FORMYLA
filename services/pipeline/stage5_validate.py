# -*- coding: utf-8 -*-
"""
Stage 5: Валидация LaTeX (pure regex, без LLM).

Проверяет корректность KaTeX 0.16 в тексте задачи.
Возвращает ValidationResult с человекочитаемыми ошибками,
которые Stage 4 получит в следующей попытке через previous_errors.
"""
import logging
import re
from typing import List
from .types import ProcessedTask, ValidationResult

logger = logging.getLogger(__name__)


# Команды LaTeX, требующие аргумента в {}
COMMANDS_WITH_BRACES = {
    'sqrt', 'frac', 'dfrac', 'tfrac', 'binom',
    'overline', 'underline', 'hat', 'tilde',
    'vec', 'bar', 'dot', 'widehat', 'widetilde',
}

# Юникод-символы, которые должны быть LaTeX-командами внутри $...$
UNICODE_TO_LATEX_HINT = {
    '≥': r'\geq',
    '≤': r'\leq',
    '≠': r'\neq',
    '±': r'\pm',
    '×': r'\times',
    '÷': r'\div',
    '∠': r'\angle',
    '△': r'\triangle',
    '∞': r'\infty',
    '∈': r'\in',
    '∉': r'\notin',
    '⊂': r'\subset',
    '⊃': r'\supset',
    '∪': r'\cup',
    '∩': r'\cap',
    '∑': r'\sum',
    '∏': r'\prod',
    '∫': r'\int',
    '·': r'\cdot',
}

# Команды которые НЕ поддерживаются KaTeX 0.16
UNSUPPORTED_COMMANDS = {
    'align', 'align*', 'eqnarray', 'gather',
    'multline', 'mathds',
}


class Stage5Validate:
    """Валидирует LaTeX в задаче с помощью регулярных выражений."""

    def validate(self, processed: ProcessedTask) -> ValidationResult:
        """
        Проверяет корректность LaTeX в тексте задачи.

        Args:
            processed: задача из Stage 4

        Returns:
            ValidationResult с is_valid и списком ошибок
        """
        text = processed.processed_text
        errors: List[str] = []

        # Проверки общего текста
        errors.extend(self._check_paired_dollars(text))
        errors.extend(self._check_empty_math(text))

        # Извлекаем регионы
        math_regions = self._extract_math_regions(text)
        plain_regions = self._extract_plain_regions(text)

        # Проверки математических регионов
        for region in math_regions:
            errors.extend(self._check_sqrt_braces(region))
            errors.extend(self._check_frac_braces(region))
            errors.extend(self._check_commands_with_braces(region))
            errors.extend(self._check_long_sub_sup(region))
            errors.extend(self._check_double_index(region))
            errors.extend(self._check_unicode_in_math(region))
            errors.extend(self._check_unsupported_commands(region))

        # Проверки обычного текста
        for region in plain_regions:
            errors.extend(self._check_plain_has_backslash(region))

        is_valid = len(errors) == 0
        if is_valid:
            logger.info("Stage5: LaTeX passed all checks")
        else:
            logger.warning(f"Stage5: found {len(errors)} issues")

        return ValidationResult(is_valid=is_valid, errors=errors)

    # ─────────────── Вспомогательные извлечения ───────────────

    def _extract_math_regions(self, text: str) -> List[str]:
        """Вырезает содержимое $...$ и $$...$$."""
        regions = []
        # Сначала display $$...$$
        for m in re.finditer(r'\$\$(.+?)\$\$', text, re.DOTALL):
            regions.append(m.group(1))
        # Убираем display, ищем inline $...$
        text_no_display = re.sub(r'\$\$.+?\$\$', '', text, flags=re.DOTALL)
        for m in re.finditer(r'\$([^$]+?)\$', text_no_display):
            regions.append(m.group(1))
        return regions

    def _extract_plain_regions(self, text: str) -> List[str]:
        """Текст вне $...$."""
        no_display = re.sub(r'\$\$.+?\$\$', '§§§', text, flags=re.DOTALL)
        no_inline = re.sub(r'\$[^$]+?\$', '§§§', no_display)
        return no_inline.split('§§§')

    # ─────────────── Проверки общего текста ───────────────

    def _check_paired_dollars(self, text: str) -> List[str]:
        """Проверяет что все $ парные."""
        # Убираем $$...$$ и $...$, проверяем что не осталось $
        t = re.sub(r'\$\$.+?\$\$', '', text, flags=re.DOTALL)
        t = re.sub(r'\$[^$]+?\$', '', t)
        if '$' in t:
            idx = t.index('$')
            ctx = t[max(0, idx - 20):idx + 20]
            return [f"Непарный $ возле: «{ctx}»"]
        return []

    def _check_empty_math(self, text: str) -> List[str]:
        """Проверяет пустые формулы $ $ и $$ $$."""
        errors = []
        # Сначала проверяем пустые display $$\s*$$
        if re.search(r'\$\$\s*\$\$', text):
            errors.append("Пустая display-формула $$ $$")
        # Убираем display, потом проверяем пустые inline $\s*$
        text_no_display = re.sub(r'\$\$.+?\$\$', '', text, flags=re.DOTALL)
        if re.search(r'\$\s*\$', text_no_display):
            errors.append("Пустая формула $ $")
        return errors

    # ─────────────── Проверки математических регионов ───────────────

    def _check_sqrt_braces(self, math: str) -> List[str]:
        """\\sqrt без фигурных скобок."""
        errors = []
        # \sqrt за которым сразу идёт буква/цифра без {
        for m in re.finditer(r'\\sqrt(?!\{|\[)([a-zA-Z0-9])', math):
            errors.append(
                f"\\sqrt без фигурных скобок: \\sqrt{m.group(1)}... "
                f"(нужно \\sqrt{{...}})"
            )
        # \sqrt пробел символ
        for m in re.finditer(r'\\sqrt\s+([a-zA-Z0-9])', math):
            errors.append(
                f"\\sqrt с пробелом вместо скобок: \\sqrt {m.group(1)}... "
                f"(нужно \\sqrt{{...}})"
            )
        return errors

    def _check_frac_braces(self, math: str) -> List[str]:
        """\\frac без двух аргументов в {}."""
        errors = []
        # \frac или \dfrac или \tfrac
        for m in re.finditer(r'\\[dt]?frac', math):
            idx = m.end()
            rest = math[idx:idx + 60]
            # Ожидаем: \s*\{...\}\s*\{...\}
            if not re.match(r'\s*\{[^}]*\}\s*\{[^}]*\}', rest):
                snippet = math[m.start():min(m.start() + 30, len(math))]
                errors.append(
                    f"\\frac без двух аргументов в скобках: "
                    f"«{snippet}» (нужно \\frac{{a}}{{b}})"
                )
        return errors

    def _check_commands_with_braces(self, math: str) -> List[str]:
        """Другие команды (overline, hat, etc.) без {}."""
        errors = []
        for cmd in COMMANDS_WITH_BRACES:
            if cmd in ('sqrt', 'frac', 'dfrac', 'tfrac'):
                continue  # обработаны отдельно
            # \cmd за которым НЕ { — ошибка (но только если за ним буква/цифра)
            pattern = rf'\\{cmd}(?!\{{)([a-zA-Z0-9])'
            for m in re.finditer(pattern, math):
                errors.append(
                    f"\\{cmd} без скобок: \\{cmd}{m.group(1)}... "
                    f"(нужно \\{cmd}{{...}})"
                )
        return errors

    def _check_long_sub_sup(self, math: str) -> List[str]:
        """Степень/индекс длиннее 1 символа без {}."""
        errors = []
        # x^12 -> плохо, x^{12} -> ок
        for m in re.finditer(r'[\^_](\d{2,})', math):
            errors.append(
                f"Степень/индекс без скобок: «...{m.group(0)}» "
                f"(нужно ^{{{m.group(1)}}} или _{{{m.group(1)}}})"
            )
        # x^ab — две буквы тоже нужны в {}
        for m in re.finditer(r'[\^_]([a-zA-Z]{2,})(?![a-zA-Z])', math):
            # Исключаем: \circ, \infty и другие команды после ^
            if m.group(1).startswith('\\'):
                continue
            errors.append(
                f"Степень/индекс с длинным выражением без скобок: "
                f"«...{m.group(0)}»"
            )
        return errors

    def _check_double_index(self, math: str) -> List[str]:
        """Подчерк/шляпка после +, −, =, · — двойной индекс."""
        errors = []
        for m in re.finditer(r'[+\-=]\s*_\{', math):
            errors.append(
                f"Двойной индекс: подчерк после знака: «{m.group(0)}...» "
                f"— индексы должны быть ВНУТРИ {{...}}"
            )
        for m in re.finditer(r'[+\-=]\s*\^\{', math):
            errors.append(
                f"Двойная степень: ^ после знака: «{m.group(0)}...»"
            )
        return errors

    def _check_unicode_in_math(self, math: str) -> List[str]:
        """Юникод-символы внутри формулы вместо LaTeX-команд."""
        errors = []
        for uni, cmd in UNICODE_TO_LATEX_HINT.items():
            if uni in math:
                errors.append(
                    f"Юникод «{uni}» внутри формулы — замени на {cmd}"
                )
        return errors

    def _check_unsupported_commands(self, math: str) -> List[str]:
        """Команды не поддерживаемые KaTeX 0.16."""
        errors = []
        for cmd in UNSUPPORTED_COMMANDS:
            if re.search(rf'\\begin\{{{re.escape(cmd)}\}}', math):
                hint = {
                    'align': 'aligned',
                    'align*': 'aligned',
                }.get(cmd, '?')
                errors.append(
                    f"\\begin{{{cmd}}} не поддерживается KaTeX "
                    f"(используй \\begin{{{hint}}} внутри $$...$$)"
                )
        return errors

    # ─────────────── Проверки обычного текста ───────────────

    def _check_plain_has_backslash(self, plain: str) -> List[str]:
        """В обычном тексте (вне $) не должно быть LaTeX-команд."""
        errors = []
        m = re.search(r'\\[a-zA-Z]{2,}', plain)
        if m:
            ctx = plain[max(0, m.start() - 15):m.end() + 15]
            errors.append(
                f"LaTeX-команда вне $...$: «{ctx}» — оберни формулу в $"
            )
        return errors
