# -*- coding: utf-8 -*-
"""
services/answer_checker.py — module for local student answer checking
WITHOUT calling an LLM (saving AI credits).

Checking levels:
  Level 1 — string normalization (whitespace, punctuation, prefixes, comma->dot).
  Level 2 — symbolic comparison via sympy (sp.simplify).

Public function:
    check_answer(student_input, correct_from_db) -> (bool, method)

Where method is a string for analytics logging:
    "exact_string"   — Level 1 matched after normalization.
    "symbolic"       — Level 2 sympy confirmed equality.
    "numeric"        — Level 2 numeric fallback (for irrationals).
    "mismatch"       — locally determined as WRONG.
    "parse_error"    — couldn't parse (needs AI fallback).
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Soft import sympy
try:
    import sympy as sp
    _HAS_SYMPY = True
except Exception:
    sp = None
    _HAS_SYMPY = False


def _normalize_string(s: str) -> str:
    """Level 1: normalize string for comparison.

    - strip
    - remove \, (LaTeX thin space)
    - remove \left, \right
    - replace ',' -> '.' (decimal comma)
    - remove prefix 'x=', 'x =', 'х=', 'х =' (Cyrillic х)
    - replace \pm -> '+-' (LaTeX plus-minus command)
    - replace ± -> '+-'
    - collapse whitespace
    - lowercase
    """
    if not s:
        return ""
    t = s.strip()
    # 1) LaTeX thin space
    t = t.replace("\\,", "")
    # 2) \left, \right
    t = t.replace("\\left", "").replace("\\right", "")
    # 3) Comma decimal -> dot  (only between digits: 2,5 -> 2.5)
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)
    # 4) Prefix 'x=' or 'х=' (Latin x or Cyrillic х)
    t = re.sub(r"^[x\u0445]\s*=\s*", "", t, flags=re.IGNORECASE)
    # 5) LaTeX \pm -> +-
    t = re.sub(r"\\pm", "+-", t)
    # 6) Unicode ± -> +-
    t = t.replace("\u00b1", "+-")
    # 7) Collapse whitespace
    t = re.sub(r"\s+", "", t)
    # 8) Lowercase for keyword comparison
    t = t.lower()
    return t


def _is_non_math_text(s: str) -> bool:
    """True if string contains Russian text -> non-numeric answer."""
    return bool(re.search(r"[\u0430-\u044f\u0410-\u042f\u0451\u0401]", s))


# LaTeX -> sympy conversion

def _clean_latex_for_sympy(text: str) -> str:
    """Clean LaTeX markup before sympy.sympify.

    Converts:
      \frac{a}{b}  -> (a)/(b)
      \sqrt{x}     -> sqrt(x)
      \cdot        -> removes
      ^             -> **
      comma-decimal -> dot
    """
    if not text:
        return ""
    t = text.strip()
    # 1) LaTeX math-mode markers
    t = re.sub(r"\\\(|\\\)|\\\[|\\\]", "", t)
    t = re.sub(r"\$\$|\$", "", t)
    # 2) Trailing period (LaTeX sentence punctuation)
    t = t.rstrip(".")
    # 3) \frac{a}{b} -> (a)/(b)
    t = re.sub(
        r"\\(?:dfrac|tfrac|frac)\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
        r"(\1)/(\2)",
        t,
    )
    # 4) \sqrt{x} -> sqrt(x)
    t = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"sqrt(\1)", t)
    # 5) ^ -> ** (sympy exponentiation)
    t = t.replace("^", "**")
    # 6) Comma decimal -> dot
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)
    # 7) Remove leftover LaTeX commands
    t = re.sub(
        r"\\(?:cdot|times|left|right|big|Big|bigg|Bigg|quad|qquad|displaystyle"
        r"|text|textbf|mathit|mathrm|underline)\s*",
        "",
        t,
    )
    # 8) Remove remaining backslash-commands (alpha -> alpha, pi -> pi for sympy)
    t = re.sub(r"\\([a-zA-Z]+)", r"\1", t)
    # 9) Squeeze whitespace
    t = re.sub(r"\s+", "", t)
    return t


# sympy comparison

def _sympy_compare(user: str, canon: str) -> Optional[bool]:
    """Compare two math expressions via sympy.

    Returns:
        True  — expressions are equivalent.
        False — expressions are NOT equivalent.
        None  — could not parse (parse error).
    """
    if not _HAS_SYMPY:
        return None

    cleaned_user = _clean_latex_for_sympy(user)
    cleaned_canon = _clean_latex_for_sympy(canon)

    if not cleaned_user or not cleaned_canon:
        return None

    # Non-math text -> skip sympy
    if _is_non_math_text(cleaned_user):
        return None

    try:
        expr_user = sp.sympify(cleaned_user, strict=False)
        expr_canon = sp.sympify(cleaned_canon, strict=False)
    except Exception:
        return None

    try:
        diff = sp.simplify(expr_user - expr_canon)
        if diff == 0:
            return True

        # Numeric fallback (handles surds where simplify fails)
        if getattr(expr_user, "is_number", False) and getattr(
            expr_canon, "is_number", False
        ):
            try:
                numeric_diff = abs(complex(sp.N(expr_user - expr_canon, 30)))
                if numeric_diff < 1e-9:
                    return True
            except Exception:
                pass

        return False
    except Exception:
        return None


# Set / interval parsing

def _parse_interval_set(text: str) -> Optional[List[str]]:
    """Parse interval set like x\u2208[1,5]\u222a[7,10] or x\u2208(-\u221e,3)."""
    if not text:
        return None
    t = text.strip().lower()
    t = re.sub(r"^[x\u0445]\s*[\u2208\u2209]\s*", "", t)
    if not t:
        return None
    parts = re.split(r"[\u222a]", t)
    intervals = []
    for p in parts:
        p = p.strip()
        m = re.match(r"^[\[\(]([^\]\)]*)[\]\)]$", p)
        if m:
            intervals.append(m.group(0))
        else:
            return None
    return intervals if intervals else None


def _compare_intervals(user: str, canon: str) -> Optional[bool]:
    """Compare two interval sets."""
    user_intervals = _parse_interval_set(user)
    canon_intervals = _parse_interval_set(canon)
    if user_intervals is None or canon_intervals is None:
        return None
    return sorted(user_intervals) == sorted(canon_intervals)


# Root list comparison

def _split_into_items(text: str) -> List[str]:
    """Split string into items by comma or ';'."""
    if not text:
        return []
    items = re.split(r"\s*[,;]\s*", text)
    return [it.strip() for it in items if it.strip()]


def _compare_as_list(user: str, canon: str) -> Optional[bool]:
    """Compare lists element-wise via sympy.

    If sympy can't parse any item -> return None (parse error, not mismatch).
    """
    user_items = _split_into_items(user)
    canon_items = _split_into_items(canon)

    if len(user_items) != len(canon_items):
        return False

    for u, c in zip(user_items, canon_items):
        if _HAS_SYMPY:
            result = _sympy_compare(u, c)
            if result is not None:
                if not result:
                    return False
                continue
        return None

    return True


# Public API

def check_answer(
    student_input: str,
    correct_from_db: str,
) -> Tuple[bool, str]:
    """Local answer checking WITHOUT calling an LLM.

    Args:
        student_input:   student's answer (string, possibly with LaTeX).
        correct_from_db: canonical answer from DB.

    Returns:
        (is_correct, method) tuple.
    """
    student = (student_input or "").strip()
    canon = (correct_from_db or "").strip()

    # Empty check
    if not student:
        logger.debug("check_answer: empty student input -> parse_error")
        return False, "parse_error"
    if not canon:
        logger.debug("check_answer: empty canonical answer -> parse_error")
        return False, "parse_error"

    # Check for proof / text answer -- skip local check
    ca_lower = canon.strip().lower()
    if ca_lower in ("\u0434\u043e\u043a\u0430\u0437\u0430\u0442\u0435\u043b\u044c\u0441\u0442\u0432\u043e",
                     "\u0434\u043e\u043a\u0430\u0437\u0430\u0442\u044c", "proof", ""):
        logger.debug("check_answer: proof task -> parse_error (fallback to AI)")
        return False, "parse_error"
    if "\u0434\u043e\u043a\u0430\u0436\u0438\u0442\u0435" in ca_lower or "\u0434\u043e\u043a\u0430\u0437\u0430\u0442\u044c" in ca_lower:
        logger.debug("check_answer: proof task -> parse_error (fallback to AI)")
        return False, "parse_error"

    # Non-math student text -> parse_error
    if _is_non_math_text(student):
        logger.debug("check_answer: non-math student text -> parse_error")
        return False, "parse_error"

    # Level 1: String normalization
    norm_student = _normalize_string(student)
    norm_canon = _normalize_string(canon)

    if not norm_student or not norm_canon:
        return False, "parse_error"

    if norm_student == norm_canon:
        logger.info(
            "check_answer: EXACT_STRING match | "
            "student='%s' canon='%s'",
            norm_student,
            norm_canon,
        )
        return True, "exact_string"

    # Level 2: Sympy comparison
    if _HAS_SYMPY:
        # 2a) Interval/set comparison
        interval_result = _compare_intervals(student, canon)
        if interval_result is not None:
            logger.info(
                "check_answer: INTERVAL match=%s | student='%s' canon='%s'",
                interval_result,
                student,
                canon,
            )
            return interval_result, "symbolic" if interval_result else "mismatch"

        # 2b) List-wise comparison
        list_result = _compare_as_list(student, canon)
        if list_result is not None:
            logger.info(
                "check_answer: LIST comparison result=%s | student='%s' canon='%s'",
                list_result,
                student,
                canon,
            )
            if list_result:
                return True, "symbolic"
            return False, "mismatch"

        # 2c) Direct sympy comparison
        sympy_result = _sympy_compare(student, canon)
        if sympy_result is True:
            logger.info(
                "check_answer: SYMBOLIC match | student='%s' canon='%s'",
                student,
                canon,
            )
            return True, "symbolic"
        elif sympy_result is False:
            logger.info(
                "check_answer: SYMBOLIC mismatch | student='%s' canon='%s'",
                student,
                canon,
            )
            return False, "mismatch"

    # Fallback: could not determine locally
    logger.debug(
        "check_answer: cannot determine locally -> parse_error | "
        "student='%s' canon='%s'",
        student,
        canon,
    )
    return False, "parse_error"
