# -*- coding: utf-8 -*-
"""X8 acceptance test: aux drawing renders with stroke-dasharray."""

import pytest


def test_aux_svg_has_stroke_dasharray(test_svg_files):
    """Read aux SVG and assert stroke-dasharray appears at least once."""
    _, aux_path = test_svg_files
    content = aux_path.read_text(encoding='utf-8')
    assert 'stroke-dasharray' in content, (
        "Aux SVG must contain stroke-dasharray at least once"
    )
