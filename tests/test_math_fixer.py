#!/usr/bin/env python3
"""Unit tests for utils/math_text_fixer.py"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.math_text_fixer import fix_plain_math, fix_latex_commands


class TestFixLatexCommands:
    """Tests for fix_latex_commands (DeepSeek error fixer)."""

    def test_sqrt_bare_letter(self):
        assert fix_latex_commands(r'\sqrta') == r'\sqrt{a}'

    def test_sqrt_bare_letters(self):
        assert fix_latex_commands(r'\sqrtab') == r'\sqrt{ab}'

    def test_sqrt_space_number(self):
        assert fix_latex_commands(r'\sqrt 45') == r'\sqrt{45}'

    def test_frac_bare_args(self):
        assert fix_latex_commands(r'\frac a b') == r'\frac{a}{b}'

    def test_frac_half_braced(self):
        result = fix_latex_commands(r'\frac{1}2')
        assert result == r'\frac{1}{2}'

    def test_sqrt_parens_to_braces(self):
        result = fix_latex_commands(r'\sqrt(x+1)')
        assert result == r'\sqrt{x+1}'

    def test_already_correct(self):
        text = r'\sqrt{a} + \frac{1}{2}'
        assert fix_latex_commands(text) == text

    def test_none_input(self):
        assert fix_latex_commands(None) is None

    def test_empty_input(self):
        assert fix_latex_commands('') == ''


class TestFixPlainMath:
    """Tests for the full fix_plain_math pipeline."""

    def test_bare_powers(self):
        result = fix_plain_math('x2 + y3 = z')
        assert '^{2}' in result
        assert '^{3}' in result

    def test_unicode_angle(self):
        result = fix_plain_math('\u2220ABC = 90\u00b0')
        assert r'\angle' in result
        assert 'circ' in result

    def test_unicode_leq_geq(self):
        result = fix_plain_math('a \u2264 b \u2265 c')
        assert r'\leq' in result
        assert r'\geq' in result

    def test_already_formatted(self):
        text = '$a^2$ + $b^2$ = $c^2$ and $x$ is $y$ plus $z$'
        result = fix_plain_math(text)
        assert result == text  # should not modify

    def test_sqrt_fix_in_pipeline(self):
        result = fix_plain_math(r'\sqrta + \sqrtb')
        assert r'\sqrt{a}' in result
        assert r'\sqrt{b}' in result
        assert '$' in result  # should be wrapped

    def test_full_pipeline(self):
        result = fix_plain_math(r'\sqrta + \sqrtb = c2')
        assert r'\sqrt{a}' in result
        assert r'\sqrt{b}' in result
        assert '^{2}' in result
        assert '$' in result

    def test_none_input(self):
        assert fix_plain_math(None) is None

    def test_empty_input(self):
        assert fix_plain_math('') == ''

    def test_plain_text_no_math(self):
        text = 'This is a normal sentence without math.'
        result = fix_plain_math(text)
        assert '$' not in result


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
