# -*- coding: utf-8 -*-
"""X8 acceptance test: base drawing renders without stroke-dasharray."""

import pytest


def test_base_svg_no_stroke_dasharray(test_svg_files):
    """Read base SVG and assert no stroke-dasharray substring."""
    base_path, _ = test_svg_files
    content = base_path.read_text(encoding='utf-8')
    assert 'stroke-dasharray' not in content, (
        "Base SVG must not contain stroke-dasharray"
    )
