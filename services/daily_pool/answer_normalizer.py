# -*- coding: utf-8 -*-
"""
Robust answer extraction & comparison for olympiad solver verification.

Three public functions:

  extract_answer(text)  → str   Pull the final answer from a free-form solution.
  normalize_answer(s)   → str   Canonicalize a single answer string.
  answers_equal(a, b)   → bool  Robust semantic equality (sympy when possible).

Designed to be tolerant of:
  - \\boxed{...} (last occurrence wins)
  - "Ответ: ...", "Answer: ...", "**Ответ:**", "Итог: ..."
  - markdown bold/italic markers (**, __, *, _)
  - LaTeX delimiters \\(, \\), \\[, \\], $, $$
  - \\dfrac vs \\frac vs \\tfrac
  - rationalize-the-denominator forms: 96/sqrt(217)  ↔  96*sqrt(217)/217
  - inline numeric multiplication (\\cdot, ·, ×, *)

Falls back gracefully if sympy parsing fails.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import sympy
    from sympy.parsing.latex import parse_latex  # noqa: F401  (optional)
    _HAVE_SYMPY = True
except Exception:  # pragma: no cover
    sympy = None  # type: ignore
    _HAVE_SYMPY = False


# ─────────────────────────────────────────────────────────────────────────────
# 1. EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

# Russian + English answer-line markers (case-insensitive, may have ** wraps)
_ANSWER_LINE_RE = re.compile(
    r"(?:\*\*|__|\*|_)?\s*"
    r"(?:ответ|итог|итого|финальный\s+ответ|answer|final\s+answer|result)"
    r"\s*(?:\*\*|__|\*|_)?\s*[:=]\s*"
    r"(.+?)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _find_all_boxed(text: str) -> list[str]:
    """Return contents of every \\boxed{...} (balanced braces)."""
    out: list[str] = []
    i = 0
    while True:
        idx = text.find(r"\boxed", i)
        if idx == -1:
            break
        # Skip past \boxed
        j = idx + len(r"\boxed")
        # Skip optional whitespace
        while j < len(text) and text[j] in " \t":
            j += 1
        if j >= len(text) or text[j] != "{":
            i = idx + 1
            continue
        # Walk to matching }
        depth = 1
        j += 1
        start = j
        while j < len(text) and depth > 0:
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if depth == 0:
            out.append(text[start:j])
        i = j + 1
    return out


def _strip_md_and_latex_wrappers(s: str) -> str:
    """Strip $, $$, \\(, \\), \\[, \\], leading/trailing **, __, *, _, spaces.

    Also removes leading/trailing markdown emphasis even when not symmetric
    (e.g. trailing ``**`` after the answer with no opening one).
    """
    if not s:
        return s
    s = s.strip()
    # Strip math delimiters wrapping the whole thing, repeatedly
    for _ in range(8):
        before = s
        s = s.strip()
        if s.startswith("$$") and s.endswith("$$") and len(s) >= 4:
            s = s[2:-2].strip()
        elif s.startswith("$") and s.endswith("$") and len(s) >= 2:
            s = s[1:-1].strip()
        if s.startswith(r"\(") and s.endswith(r"\)"):
            s = s[2:-2].strip()
        if s.startswith(r"\[") and s.endswith(r"\]"):
            s = s[2:-2].strip()
        # Symmetric markdown emphasis
        for mk in ("**", "__", "*", "_"):
            if s.startswith(mk) and s.endswith(mk) and len(s) > 2 * len(mk):
                s = s[len(mk):-len(mk)].strip()
        # Asymmetric: just trim leading/trailing emphasis & dollar signs
        s = re.sub(r"^(?:\*\*|__|\*|_|\$\$?)+", "", s).strip()
        s = re.sub(r"(?:\*\*|__|\*|_|\$\$?)+$", "", s).strip()
        # Trim leading/trailing math delimiters that may have been left over
        if s.startswith(r"\("):
            s = s[2:].strip()
        if s.endswith(r"\)"):
            s = s[:-2].strip()
        if s.startswith(r"\["):
            s = s[2:].strip()
        if s.endswith(r"\]"):
            s = s[:-2].strip()
        if s == before:
            break
    # Also remove a trailing period / comma / semicolon
    s = s.rstrip(".,; \t")
    return s


def extract_answer(text: str) -> str:
    """Extract the final answer from a free-form solution.

    Priority:
      (A) The LAST \\boxed{...} occurrence in the text.
      (B) The LAST "Ответ:" / "Answer:" / "Итог:" line.
      (C) The LAST display-mode formula \\[...\\] in the text.
      (D) The last non-empty line.

    Always strips markdown/LaTeX wrappers from the result.
    """
    if not text:
        return ""

    # (A) boxed
    boxed = _find_all_boxed(text)
    if boxed:
        return _strip_md_and_latex_wrappers(boxed[-1])

    # (B) answer-line markers
    matches = list(_ANSWER_LINE_RE.finditer(text))
    if matches:
        raw = matches[-1].group(1).strip()
        # If this matched line is itself just a label like "**Ответ:**" pointing
        # to the next line, raw will be empty. In that case look at next non-empty line.
        if not raw:
            tail = text[matches[-1].end():].lstrip("\r\n")
            first = tail.split("\n", 1)[0].strip()
            raw = first
        # If the answer is on the next line (e.g. "**Ответ:**\n\\[\\boxed{...}\\]"),
        # check if there's a boxed expression on the immediately following lines.
        tail = text[matches[-1].end():]
        boxed_after = _find_all_boxed(tail[:600])
        if boxed_after:
            return _strip_md_and_latex_wrappers(boxed_after[-1])
        return _strip_md_and_latex_wrappers(raw)

    # (C) last display formula
    disp = re.findall(r"\\\[(.+?)\\\]", text, re.DOTALL)
    if disp:
        # Prefer one that contains '=' — answer often after last '='
        last = disp[-1].strip()
        if "=" in last:
            last = last.rsplit("=", 1)[1]
        return _strip_md_and_latex_wrappers(last)

    # (D) last non-empty line
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if lines:
        return _strip_md_and_latex_wrappers(lines[-1])[:200]

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# 2. NORMALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def _read_brace_arg(s: str, pos: int) -> tuple[str, int]:
    """Read a {...} balanced argument starting at s[pos] (must be '{').
    Returns (inner_text, index_after_closing_brace). If no '{' at pos,
    returns ('', pos)."""
    if pos >= len(s) or s[pos] != "{":
        return "", pos
    depth = 1
    j = pos + 1
    start = j
    while j < len(s) and depth > 0:
        ch = s[j]
        if ch == "\\" and j + 1 < len(s):
            j += 2  # skip escaped command (e.g. \{, \})
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    if depth != 0:
        return "", pos
    return s[start:j], j + 1


def _expand_command(s: str, cmd: str, n_args: int, formatter) -> str:
    """Find every occurrence of \\cmd and replace with formatter(*args)."""
    out: list[str] = []
    i = 0
    needle = "\\" + cmd
    while i < len(s):
        idx = s.find(needle, i)
        if idx == -1:
            out.append(s[i:])
            break
        # Make sure it isn't a longer command (e.g. \fracfoo). Next char must be
        # non-letter.
        end = idx + len(needle)
        if end < len(s) and s[end].isalpha():
            out.append(s[i:idx + 1])
            i = idx + 1
            continue
        out.append(s[i:idx])
        # Skip whitespace before first {
        j = end
        args: list[str] = []
        ok = True
        for _ in range(n_args):
            while j < len(s) and s[j] in " \t":
                j += 1
            if j >= len(s) or s[j] != "{":
                ok = False
                break
            arg, j = _read_brace_arg(s, j)
            args.append(arg)
        if not ok:
            out.append(s[idx:end])
            i = end
            continue
        out.append(formatter(*args))
        i = j
    return "".join(out)


def _expand_latex_macros(s: str) -> str:
    """Recursively expand \\frac, \\sqrt, \\dfrac, \\tfrac with brace balance."""
    for _ in range(8):
        before = s
        # \sqrt first (may be argument of frac)
        s = _expand_command(s, "sqrt", 1, lambda a: f"sqrt({_expand_latex_macros(a)})")
        s = _expand_command(s, "dfrac", 2, lambda a, b: f"(({_expand_latex_macros(a)})/({_expand_latex_macros(b)}))")
        s = _expand_command(s, "tfrac", 2, lambda a, b: f"(({_expand_latex_macros(a)})/({_expand_latex_macros(b)}))")
        s = _expand_command(s, "frac", 2, lambda a, b: f"(({_expand_latex_macros(a)})/({_expand_latex_macros(b)}))")
        if s == before:
            break
    # \sqrt without braces: \sqrt 5 → sqrt(5)
    s = re.sub(r"\\sqrt\s+([0-9]+(?:\.[0-9]+)?)", lambda m: f"sqrt({m.group(1)})", s)
    return s


def _latex_to_text(s: str) -> str:
    """Crude LaTeX → plain ASCII conversion for sympy parsing."""
    if not s:
        return s
    s = s.strip()
    # Drop math delimiters anywhere (already mostly stripped by extract, but be safe)
    s = s.replace(r"\(", "").replace(r"\)", "")
    s = s.replace(r"\[", "").replace(r"\]", "")
    s = s.replace("$$", "").replace("$", "")
    # Strip stray markdown emphasis markers — at this point we are inside an
    # extracted expression, so any *, _, ** inside are noise.
    s = re.sub(r"\*\*", "", s)
    # \\sqrt and \\frac — properly nested via brace counter
    s = _expand_latex_macros(s)
    # \cdot, \times, ·, ×  → *
    s = s.replace(r"\cdot", "*").replace(r"\times", "*")
    s = s.replace("·", "*").replace("×", "*").replace("⋅", "*")
    # \pi → pi, infinity
    s = s.replace(r"\pi", "pi").replace(r"\infty", "oo").replace("∞", "oo")
    # Remove leftover backslash commands like \,  \!  \;  \:  \quad  \qquad  \!
    s = re.sub(r"\\[,!;:](?![A-Za-z])", "", s)
    s = re.sub(r"\\(?:quad|qquad|displaystyle|left|right|big|Big|bigg|Bigg)\b", "", s)
    # Russian comma decimal separator → dot, but only between digits
    s = re.sub(r"(?<=\d),(?=\d)", ".", s)
    # Squeeze spaces (do this BEFORE implicit-mult so spaces don't fool us)
    s = re.sub(r"\s+", "", s)
    # Implicit multiplication. Sympy with implicit_multiplication_application
    # handles "2x" and "2(x+1)" itself, but does NOT handle ")(", so add a *
    # only between ')' and a following identifier/number/'('. Do NOT touch
    # function-call patterns like 'sqrt(' or 'pi(' (sympy will read pi as a
    # number * paren via implicit-mult itself).
    s = re.sub(r"\)(?=[A-Za-z0-9(])", r")*", s)
    return s


def _to_sympy(raw: str):
    """Try sympy.sympify on a (latex-stripped) string. Return None on failure."""
    if not _HAVE_SYMPY or not raw:
        return None
    try:
        # transformations enable implicit_mult etc., but sympify usually suffices
        from sympy.parsing.sympy_parser import (
            parse_expr, standard_transformations,
            implicit_multiplication_application, convert_xor,
        )
        tx = standard_transformations + (
            implicit_multiplication_application, convert_xor,
        )
        expr = parse_expr(raw, transformations=tx, evaluate=True)
        return sympy.simplify(expr)
    except Exception:
        return None


def normalize_answer(raw: str) -> str:
    """Canonicalize an answer string. Returns lowercase, whitespace-free form.

    If sympy can parse, returns canonical sympy str (rationalized, simplified).
    Otherwise returns a best-effort textual normalization.
    """
    if not raw:
        return ""
    s = _strip_md_and_latex_wrappers(raw)
    text = _latex_to_text(s)

    expr = _to_sympy(text)
    if expr is not None:
        try:
            # Rationalize denominator: radsimp moves sqrt out of denom
            expr = sympy.radsimp(expr)
            expr = sympy.nsimplify(expr, rational=False) if expr.free_symbols == set() else expr
            expr = sympy.simplify(expr)
        except Exception:
            pass
        out = str(expr)
        return re.sub(r"\s+", "", out).lower()

    # Fallback: textual canonicalization (already lower / no-space)
    return text.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 3. EQUALITY
# ─────────────────────────────────────────────────────────────────────────────

def _try_numeric_close(a_norm: str, b_norm: str, tol: float = 1e-9) -> Optional[bool]:
    if not _HAVE_SYMPY:
        try:
            return abs(float(a_norm) - float(b_norm)) < tol
        except Exception:
            return None
    try:
        ea = sympy.sympify(a_norm)
        eb = sympy.sympify(b_norm)
        diff = sympy.N(ea - eb, 30)
        return abs(complex(diff)) < tol
    except Exception:
        return None


def answers_equal(a: str, b: str) -> bool:
    """Return True if two answer strings are mathematically equivalent."""
    if a is None or b is None:
        return False

    sa = _strip_md_and_latex_wrappers(a)
    sb = _strip_md_and_latex_wrappers(b)
    if not sa or not sb:
        return False

    # Quick exact match after light cleaning
    if re.sub(r"\s+", "", sa).lower() == re.sub(r"\s+", "", sb).lower():
        return True

    ta = _latex_to_text(sa)
    tb = _latex_to_text(sb)
    if ta == tb:
        return True

    # Sympy structural equality
    if _HAVE_SYMPY:
        ea = _to_sympy(ta)
        eb = _to_sympy(tb)
        if ea is not None and eb is not None:
            try:
                diff = sympy.simplify(ea - eb)
                if diff == 0:
                    return True
                # Numeric fallback (handles tricky surds where simplify fails)
                num = sympy.N(diff, 30)
                if abs(complex(num)) < 1e-9:
                    return True
            except Exception:
                pass

    # Set comparison (comma-separated multi-answer)
    a_parts = sorted(p.strip() for p in re.split(r"[,;]", sa) if p.strip())
    b_parts = sorted(p.strip() for p in re.split(r"[,;]", sb) if p.strip())
    if len(a_parts) > 1 and len(a_parts) == len(b_parts):
        if all(answers_equal(x, y) for x, y in zip(a_parts, b_parts)):
            return True

    # Pure-numeric close
    res = _try_numeric_close(ta, tb)
    if res is True:
        return True

    return False
