"""Generates utils/math_text_fixer.py"""
import os

code = r'''"""Fixes plain-text math from OCR olympiad tasks."""
import re


# Unicode math symbols to LaTeX
UNICODE_TO_LATEX = {}
_pairs = [
    (0x2220, r'\angle '), (0x25B3, r'\triangle '),
    (0x00B0, r'^{\circ}'), (0x2260, r'\neq '),
    (0x2261, r'\equiv '), (0x2264, r'\leq '),
    (0x2265, r'\geq '), (0x221A, r'\sqrt'),
    (0x221E, r'\infty '), (0x00B1, r'\pm '),
    (0x00D7, r'\times '), (0x00F7, r'\div '),
    (0x2208, r'\in '), (0x2209, r'\notin '),
    (0x2A7D, r'\leq '), (0x2A7E, r'\geq '),
    (0x2026, r'\ldots '), (0x22C5, r'\cdot '),
    (0x03C0, r'\pi '), (0x03B1, r'\alpha '),
    (0x03B2, r'\beta '), (0x03B3, r'\gamma '),
    (0x03B4, r'\delta '), (0x03B8, r'\theta '),
    (0x03BB, r'\lambda '), (0x03C6, r'\varphi '),
    (0x03C9, r'\omega '),
]
for _code, _latex in _pairs:
    UNICODE_TO_LATEX[chr(_code)] = _latex

# Superscript/subscript digits
SUPERSCRIPT_MAP = {}
for c