"""Fixes plain-text math from AI-generated olympiad tasks.

Main entry point: fix_plain_math(text) -> str
"""
import re

# ─── Unicode subscript/superscript digit maps ────────────────────────────────

_SUPERSCRIPT_DIGITS = {
    '\u2070': '0', '\u00b9': '1', '\u00b2': '2', '\u00b3': '3', '\u2074': '4',
    '\u2075': '5', '\u2076': '6', '\u2077': '7', '\u2078': '8', '\u2079': '9',
}

_SUBSCRIPT_DIGITS = {
    '\u2080': '0', '\u2081': '1', '\u2082': '2', '\u2083': '3', '\u2084': '4',
    '\u2085': '5', '\u2086': '6', '\u2087': '7', '\u2088': '8', '\u2089': '9',
}

# Unicode subscript letters
_SUBSCRIPT_LETTERS = {
    '\u2090': 'a', '\u2091': 'e', '\u2095': 'h', '\u1d62': 'i', '\u2c7c': 'j',
    '\u2096': 'k', '\u2097': 'l', '\u2098': 'm', '\u2099': 'n', '\u2092': 'o',
    '\u209a': 'p', '\u1d63': 'r', '\u209b': 's', '\u209c': 't', '\u1d64': 'u',
    '\u1d65': 'v', '\u2093': 'x',
}

# Unicode superscript letters
_SUPERSCRIPT_LETTERS = {
    '\u207f': 'n', '\u2071': 'i',
}

# All subscript chars (digits + letters)
_ALL_SUBSCRIPT = {**_SUBSCRIPT_DIGITS, **_SUBSCRIPT_LETTERS}
_ALL_SUPERSCRIPT = {**_SUPERSCRIPT_DIGITS, **_SUPERSCRIPT_LETTERS}

# Build regex character classes
_SUB_CHARS_SET = ''.join(_ALL_SUBSCRIPT.keys())
_SUP_CHARS_SET = ''.join(_ALL_SUPERSCRIPT.keys())


def _is_inside_braces(text, pos):
    """Check if position `pos` is inside {...} braces."""
    depth = 0
    for i in range(pos):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
    return depth > 0


def _replace_grouped_scripts(text):
    """Replace consecutive unicode sub/superscript characters with LaTeX.

    Groups like 2022 -> _{2022}, 3 -> ^{3}, n -> _{n}
    Must run BEFORE individual unicode replacement.

    IMPORTANT: If unicode subscript is already inside braces (e.g. _{m+1}),
    just convert the character to ASCII without adding _{...} wrapper.
    """
    if not text:
        return text

    # Replace consecutive subscript chars
    def sub_replacer(m):
        chars = m.group(0)
        converted = ''.join(_ALL_SUBSCRIPT.get(c, c) for c in chars)
        # If inside braces, just convert chars without adding _{...}
        if _is_inside_braces(text, m.start()):
            return converted
        return '_{' + converted + '}'

    if _SUB_CHARS_SET:
        pattern = '[' + re.escape(_SUB_CHARS_SET) + ']+'
        text = re.sub(pattern, sub_replacer, text)

    # Replace consecutive superscript chars
    def sup_replacer(m):
        chars = m.group(0)
        converted = ''.join(_ALL_SUPERSCRIPT.get(c, c) for c in chars)
        # If inside braces, just convert chars without adding ^{...}
        if _is_inside_braces(text, m.start()):
            return converted
        return '^{' + converted + '}'

    if _SUP_CHARS_SET:
        pattern = '[' + re.escape(_SUP_CHARS_SET) + ']+'
        text = re.sub(pattern, sup_replacer, text)

    return text


# ─── Unicode -> LaTeX mapping (non-script symbols) ───────────────────────────

UNICODE_TO_LATEX = {
    '\u2220': r'\angle ',    '\u25b3': r'\triangle ',
    '\u00b0': r'^{\circ} ',  '\u2260': r'\neq ',
    '\u2261': r'\equiv ',    '\u2264': r'\leq ',
    '\u2265': r'\geq ',      '\u00b1': r'\pm ',
    '\u00d7': r'\times ',    '\u00f7': r'\div ',
    '\u2208': r'\in ',       '\u221e': r'\infty ',
    '\u230a': r'\lfloor ',   '\u230b': r'\rfloor ',
    '\u2308': r'\lceil ',    '\u2309': r'\rceil ',
    '\u2211': r'\sum ',      '\u220f': r'\prod ',
    '\u222b': r'\int ',      '\u03c0': r'\pi ',
    '\u03b1': r'\alpha ',    '\u03b2': r'\beta ',
    '\u03b3': r'\gamma ',    '\u03b4': r'\delta ',
    '\u03b8': r'\theta ',    '\u03bb': r'\lambda ',
    '\u03bc': r'\mu ',       '\u03c3': r'\sigma ',
    '\u03c6': r'\varphi ',   '\u03c9': r'\omega ',
    '\u00b7': r'\cdot ',     '\u2022': r'\cdot ',
    '\u2209': r'\notin ',    '\u2282': r'\subset ',
    '\u2286': r'\subseteq ', '\u222a': r'\cup ',
    '\u2229': r'\cap ',      '\u2205': r'\emptyset ',
    '\u221a': r'\sqrt',
    '\u2192': r'\to ',       '\u21d2': r'\Rightarrow ',
    '\u2026': r'\ldots ',    '\u2032': "'",
    '\u2033': "''",
}


def replace_unicode_math(text):
    """Replace unicode math symbols with LaTeX equivalents.

    IMPORTANT: Grouped subscripts/superscripts are handled FIRST
    (2022 -> _{2022}), then individual symbols.
    """
    if not text:
        return text

    # Step 1: Group consecutive unicode sub/superscripts FIRST
    text = _replace_grouped_scripts(text)

    # Step 2: Replace remaining unicode symbols
    for u, l in UNICODE_TO_LATEX.items():
        if u in text:
            text = text.replace(u, l)

    return text


# ─── LaTeX command fixer ─────────────────────────────────────────────────────

def fix_latex_commands(text):
    """Fix common AI LaTeX errors like \\sqrta -> \\sqrt{a},
    \\frac a b -> \\frac{a}{b}, etc.

    This function ALWAYS runs, even on partially-formatted text.
    """
    if not text:
        return text

    # 1. \sqrta, \sqrtab -> \sqrt{a}, \sqrt{ab}
    #    But NOT \sqrt{...} (already correct)
    text = re.sub(
        r'\\sqrt([a-zA-Z][a-zA-Z0-9]*)',
        lambda m: r'\sqrt{' + m.group(1) + '}',
        text
    )

    # 2. \sqrt N (space + content) -> \sqrt{N}
    text = re.sub(
        r'\\sqrt\s+([a-zA-Z0-9]+)',
        r'\\sqrt{\1}',
        text
    )

    # 3. \sqrt(...) -> \sqrt{...} (parens to braces)
    text = re.sub(
        r'\\(sqrt|text|mathrm|mathbf|mathbb|overline|underline|hat|tilde|vec)\(([^)]*)\)',
        r'\\\1{\2}',
        text
    )

    # 4. \frac a b -> \frac{a}{b}
    text = re.sub(
        r'\\frac\s+([a-zA-Z0-9])\s+([a-zA-Z0-9])',
        r'\\frac{\1}{\2}',
        text
    )

    # 5. \frac{a}b -> \frac{a}{b} (second arg missing braces)
    text = re.sub(
        r'(\\frac\{[^}]+\})\s*([a-zA-Z0-9])(?![a-zA-Z0-9}])',
        r'\1{\2}',
        text
    )

    # 6. \frac a{b} -> \frac{a}{b} (first arg missing braces)
    text = re.sub(
        r'\\frac\s*([a-zA-Z0-9])\s*(\{[^}]+\})',
        r'\\frac{\1}\2',
        text
    )

    return text


# ─── Dollar wrapping ─────────────────────────────────────────────────────────

# LaTeX commands that indicate math content
LATEX_COMMANDS = (
    r'sqrt|frac|dfrac|tfrac|binom|'
    r'angle|triangle|lfloor|rfloor|lceil|rceil|'
    r'geq|leq|neq|equiv|pm|mp|times|div|cdot|'
    r'sum|prod|int|lim|log|ln|sin|cos|tan|'
    r'infty|pi|alpha|beta|gamma|delta|theta|lambda|mu|'
    r'sigma|phi|varphi|omega|psi|chi|'
    r'in|notin|subset|supset|cup|cap|emptyset|'
    r'overline|underline|hat|tilde|vec|bar|dot|'
    r'ldots|cdots|vdots|ddots|'
    r'left|right|text|mathrm|mathbf|mathbb|operatorname|'
    r'to|Rightarrow|forall|exists|partial|nabla'
)


def _split_by_math(text):
    """Split text into segments: math (inside $/$$/\\(\\)/\\[\\]) and non-math.

    Returns list where odd indices are math segments (untouchable),
    even indices are plain text segments (can be modified).
    """
    pattern = re.compile(
        r'(\$\$[\s\S]+?\$\$|\$[^\$\n]+?\$|\\\([\s\S]+?\\\)|\\\[[\s\S]+?\\\])'
    )
    return pattern.split(text)


# Standalone operators (no arguments, just wrap individually)
_STANDALONE_OPS = (
    r'geq|leq|neq|equiv|pm|mp|times|div|cdot|'
    r'infty|pi|alpha|beta|gamma|delta|theta|lambda|mu|'
    r'sigma|phi|varphi|omega|psi|chi|'
    r'in|notin|subset|supset|cup|cap|emptyset|'
    r'ldots|cdots|vdots|ddots|'
    r'to|Rightarrow|forall|exists|partial|nabla|'
    r'angle|triangle'
)

# Commands that take arguments ({...})
_ARG_COMMANDS = (
    r'sqrt|frac|dfrac|tfrac|binom|'
    r'lfloor|rfloor|lceil|rceil|'
    r'sum|prod|int|lim|log|ln|sin|cos|tan|'
    r'overline|underline|hat|tilde|vec|bar|dot|'
    r'left|right|text|mathrm|mathbf|mathbb|operatorname'
)


def ensure_dollar_wrapping(text):
    """Wrap bare LaTeX commands and expressions in $...$ if outside math delimiters."""
    if not text:
        return text

    # Quick check: if no backslash, no ^{, no _{  -> nothing to wrap
    if '\\' not in text and '^{' not in text and '_{' not in text:
        return text

    parts = _split_by_math(text)

    # Pattern for letter + subscript/superscript: a_{2022}, n^{3}, x_{n}
    # Must run FIRST so these are wrapped before command patterns try to grab them
    script_pattern = re.compile(
        r'([a-zA-Z](?:\s*[_^]\{[^}]*\})+)'
    )

    # Pattern for standalone operators (\geq, \leq, \pi, etc.) — no arguments
    standalone_pattern = re.compile(
        rf'(\\(?:{_STANDALONE_OPS}))\b'
    )

    # Pattern for commands with arguments (\sqrt{...}, \frac{...}{...})
    arg_cmd_pattern = re.compile(
        rf'(\\(?:{_ARG_COMMANDS})'
        rf'(?:\{{[^{{}}]*\}}|\[[^\]]*\])*'
        rf'(?:\s*[_^]\s*(?:\{{[^{{}}]*\}}|[a-zA-Z0-9]))*'
        rf')'
    )

    for i in range(0, len(parts), 2):  # only process non-math segments
        seg = parts[i]
        if not seg:
            continue

        # 1. First wrap letter+subscript/superscript (a_{2022}, n^{3})
        seg = script_pattern.sub(lambda m: '$' + m.group(1) + '$', seg)

        # 2. Then wrap standalone operators (\geq, \leq, etc.)
        seg = standalone_pattern.sub(lambda m: '$' + m.group(1) + '$', seg)

        # 3. Then wrap commands with arguments (\sqrt{...}, \frac{...}{...})
        seg = arg_cmd_pattern.sub(lambda m: '$' + m.group(1) + '$', seg)

        # Clean up empty $$ pairs and merge adjacent
        seg = re.sub(r'\$\s*\$', ' ', seg)

        parts[i] = seg

    return ''.join(parts)


# ─── Bare powers fixer ───────────────────────────────────────────────────────

def fix_powers(text):
    """Fix bare powers like x2 -> $x^{2}$ outside of math delimiters."""
    if not text:
        return text

    parts = _split_by_math(text)

    for i in range(0, len(parts), 2):  # only outside math
        seg = parts[i]
        if not seg:
            continue
        # Fix single-letter followed by single digit (likely power)
        # But not after 2+ letters (avoids "log2", "step3")
        seg = re.sub(
            r'(?<![a-zA-Z]{2})([a-zA-Z])(\d)(?![a-zA-Z\d])',
            lambda m: '$' + m.group(1) + '^{' + m.group(2) + '}$',
            seg
        )
        parts[i] = seg

    return ''.join(parts)


# ─── Main pipeline ───────────────────────────────────────────────────────────

def fix_plain_math(text):
    """Main pipeline for fixing AI-generated math text.

    Steps:
    1. Replace unicode math symbols (grouping subscripts/superscripts)
    2. Fix broken LaTeX commands (\\sqrta -> \\sqrt{a}) - ALWAYS runs
    3. Wrap bare LaTeX in $...$ delimiters
    4. Fix bare powers (x2 -> $x^{2}$)

    NOTE: No early-exit based on $ count - we ALWAYS fix LaTeX commands
    because text can be partially formatted.
    """
    if not text:
        return text

    # Step 1: Replace unicode math symbols (groups ₂₀₂₂ -> _{2022} first!)
    text = replace_unicode_math(text)

    # Step 2: Fix broken LaTeX commands - ALWAYS runs
    text = fix_latex_commands(text)

    # Step 3: Wrap bare LaTeX commands in $...$
    text = ensure_dollar_wrapping(text)

    # Step 4: Fix bare powers (x2 -> $x^{2}$) - only outside math delimiters
    has_math = bool(re.search(r'\\|[\^_]\{', text))
    if has_math or _looks_like_math(text):
        text = fix_powers(text)

    # Final cleanup: remove empty $$ pairs
    text = re.sub(r'\$\s*\$', '', text)

    return text


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


# Alias for backward compatibility
fix_bare_latex = fix_plain_math
