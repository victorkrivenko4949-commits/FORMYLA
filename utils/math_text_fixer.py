"""Fixes plain-text math from OCR olympiad tasks."""
import re

# Unicode -> LaTeX mapping
_UNICODE_MAP = {
    "\u2220": r"\angle ",
    "\u00b0": r"^{\circ}",
    "\u2260": r"\neq ",
    "\u2264": r"\leq ",
    "\u2265": r"\geq ",
    "\u00b7": r"\cdot ",
    "\u2022": r"\cdot ",
    "\u00d7": r"\times ",
    "\u00f7": r"\div ",
    "\u221e": r"\infty ",
    "\u03b1": r"\alpha ",
    "\u03b2": r"\beta ",
    "\u03b3": r"\gamma ",
    "\u03b4": r"\delta ",
    "\u03c0": r"\pi ",
    "\u03c6": r"\varphi ",
    "\u2208": r"\in ",
    "\u2209": r"\notin ",
    "\u2282": r"\subset ",
    "\u2286": r"\subseteq ",
    "\u222a": r"\cup ",
    "\u2229": r"\cap ",
    "\u2205": r"\emptyset ",
    "\u221a": r"\sqrt",
    "\u00b2": "^{2}",
    "\u00b3": "^{3}",
    "\u2074": "^{4}",
    "\u2075": "^{5}",
    "\u2076": "^{6}",
    "\u2077": "^{7}",
    "\u2078": "^{8}",
    "\u2079": "^{9}",
    "\u2081": "_{1}",
    "\u2082": "_{2}",
    "\u2083": "_{3}",
    "\u2084": "_{4}",
    "\u2192": r"\to ",
    "\u21d2": r"\Rightarrow ",
    "\u2026": r"\ldots ",
    "\u2032": "'",
    "\u2033": "''",
}

# Patterns for bare powers: x2 -> x^{2}, ab3 -> ab^{3}
# Matches a letter followed by a digit that looks like a power
_BARE_POWER_RE = re.compile(
    r'(?<=[a-zA-Z])(\d)(?=[\s\)\],;:.\+\-\*\/\=\<\>]|$)'
)

# Patterns that indicate math content needing wrapping
_MATH_INDICATORS = [
    r'[a-zA-Z]\s*[\+\-\*\/\=]\s*[a-zA-Z0-9]',  # a + b, x = 5
    r'\d+[a-zA-Z]',  # 2x, 3y
    r'[a-zA-Z]\d',   # x2, y3
    r'\\[a-zA-Z]+',  # \sqrt, \frac
    r'\^',           # powers
    r'_\{',          # subscripts
]


def fix_plain_math(text):
    """Replace unicode math symbols and fix bare powers.
    Returns text with properly wrapped LaTeX expressions.
    """
    if not text:
        return text

    # If already well-formatted with many LaTeX delimiters, skip
    if text.count('$') >= 6:
        return text

    result = text

    # Step 0: Fix common LaTeX command errors first (\sqrta -> \sqrt{a} etc.)
    result = fix_latex_commands(result)

    # Step 1: Replace unicode math symbols
    for uni_char, latex_cmd in _UNICODE_MAP.items():
        if uni_char in result:
            result = result.replace(uni_char, latex_cmd)

    # Step 2: Fix bare powers like x2 -> x^{2}, but not in words like "log2"
    # Only apply if the text has math-like content
    has_math = any(re.search(pat, result) for pat in [r'\\', r'\^', r'_'])

    if has_math or _looks_like_math(result):
        result = _fix_bare_powers(result)

    # Step 3: Wrap math segments in $ if not already wrapped
    result = _ensure_dollar_wrap(result)

    return result


def _looks_like_math(text):
    """Heuristic: does this text contain math-like patterns?"""
    indicators = 0
    if re.search(r'[a-zA-Z]\d', text):
        indicators += 1
    if re.search(r'\d+[a-zA-Z]', text):
        indicators += 1
    if re.search(r'[=<>]', text):
        indicators += 1
    if re.search(r'[\+\-\*/]', text):
        indicators += 1
    return indicators >= 2


def _fix_bare_powers(text):
    """Fix patterns like x2, y3, a2b -> x^{2}, y^{3}, a^{2}b.
    Only applies outside of existing $ delimiters.
    """
    segments = text.split('$')
    for i in range(0, len(segments), 2):  # only outside $
        seg = segments[i]
        # Fix single-letter followed by single digit (likely power)
        # But not after common words or inside normal text
        seg = re.sub(
            r'(?<![a-zA-Z]{2})([a-zA-Z])(\d)(?![a-zA-Z\d])',
            lambda m: m.group(1) + '^{' + m.group(2) + '}',
            seg
        )
        segments[i] = seg
    return '$'.join(segments)


def _ensure_dollar_wrap(text):
    """Wrap LaTeX commands that are outside $ delimiters."""
    # Split by existing $ pairs
    segments = text.split('$')

    for i in range(0, len(segments), 2):  # process only outside-$ segments
        seg = segments[i]
        # If segment contains LaTeX commands, wrap them
        if re.search(r'\\(sqrt|frac|angle|cdot|times|div|leq|geq|neq|pi|alpha|beta|gamma|delta|varphi|infty|in|notin|subset|cup|cap|emptyset|to|Rightarrow|ldots)', seg):
            # Wrap the whole segment or individual commands
            seg = _wrap_latex_in_segment(seg)
        segments[i] = seg

    return '$'.join(segments)


def _wrap_latex_in_segment(seg):
    """Find LaTeX commands in a text segment and wrap them with $."""
    # Pattern: sequence containing backslash commands, braces, powers, etc.
    pattern = re.compile(
        r'(\\[a-zA-Z]+(?:\{[^}]*\})*(?:\s*[a-zA-Z0-9\^\{\}\_\+\-\=\s]*\\[a-zA-Z]+(?:\{[^}]*\})*)*'
        r'(?:\s*[a-zA-Z0-9\^\{\}\_\+\-\=\(\)\s]*)?)'
    )

    def replacer(m):
        expr = m.group(0).strip()
        if expr:
            return ' $' + expr + '$ '
        return m.group(0)

    result = pattern.sub(replacer, seg)
    # Clean up double spaces
    result = re.sub(r'\s{2,}', ' ', result)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# fix_latex_commands — починка распространённых ошибок DeepSeek в LaTeX
# ──────────────────────────────────────────────────────────────────────────────

def fix_latex_commands(text):
    r"""Починить типичные ошибки LaTeX-команд из ответов LLM.

    Что чинит:
      • \sqrta        → \sqrt{a}        (буква без скобок)
      • \sqrtab       → \sqrt{ab}
      • \sqrt 45      → \sqrt{45}       (пробел перед аргументом)
      • \sqrt(x+1)    → \sqrt{x+1}      (круглые скобки вместо фигурных)
      • \frac a b     → \frac{a}{b}     (два простых аргумента через пробел)
      • \frac{1}2     → \frac{1}{2}     (второй аргумент не в скобках)

    Идемпотентность: если LaTeX уже правильный (\sqrt{a}, \frac{1}{2}) —
    функция возвращает текст без изменений.

    None / '' / not-string — пропускаем без падений.
    """
    if text is None or text == '':
        return text
    if not isinstance(text, str):
        return text

    s = text

    # 1. \sqrt(x+1) → \sqrt{x+1}.   Скобки могут содержать что угодно
    #    кроме самих круглых скобок (1 уровень — большинства случаев хватает).
    s = re.sub(r'\\sqrt\(([^()]+)\)', r'\\sqrt{\1}', s)

    # 2. \sqrt 45  /  \sqrt  abc  → \sqrt{45} / \sqrt{abc}.
    #    Аргумент: подряд идущие буквы/цифры после одного-нескольких пробелов.
    s = re.sub(r'\\sqrt\s+([A-Za-z0-9]+)', r'\\sqrt{\1}', s)

    # 3. \sqrta / \sqrtab → \sqrt{a} / \sqrt{ab}.
    #    Аргумент: буквы/цифры, идущие СРАЗУ за \sqrt без пробела/скобки.
    #    (Если уже идёт «{» — ничего не делаем, regex не сматчится.)
    s = re.sub(r'\\sqrt([A-Za-z][A-Za-z0-9]*)', r'\\sqrt{\1}', s)
    # Числа: \sqrt2 → \sqrt{2}
    s = re.sub(r'\\sqrt(\d+)', r'\\sqrt{\1}', s)

    # 4. \frac a b → \frac{a}{b}  (оба аргумента — одиночные буквы/цифры).
    s = re.sub(
        r'\\frac\s+([A-Za-z0-9]+)\s+([A-Za-z0-9]+)',
        r'\\frac{\1}{\2}',
        s,
    )

    # 5. \frac{1}2 → \frac{1}{2}  (первый аргумент в скобках, второй нет).
    s = re.sub(
        r'\\frac(\{[^{}]+\})(\s*)([A-Za-z0-9])(?![A-Za-z0-9{])',
        lambda m: '\\frac' + m.group(1) + '{' + m.group(3) + '}',
        s,
    )
    # 5b. И симметричный кейс: \frac a{b}
    s = re.sub(
        r'\\frac(\s*)([A-Za-z0-9])(\{[^{}]+\})',
        lambda m: '\\frac{' + m.group(2) + '}' + m.group(3),
        s,
    )

    return s


# Alias for backward compatibility
fix_bare_latex = fix_plain_math
