# -*- coding: utf-8 -*-
"""
services/theme_registry.py — Canonical theme→section lookup + human-readable titles.

Loads data/theme_to_section.json and FORMYLA_L1_L5_TOP5.jsonl once at import time.
Provides:
  section_of_theme(theme_id) → canonical slug (algebra|geometry|combinatorics|logic|number_theory)
  theme_title(theme_id) → human-readable title from JSONL (e.g. "Многочлены и алгебраические тождества")
  themes_of_grade(grade) → list of theme_id
  themes_of_section(grade, section) → list of theme_id
  all_themes() → list of (theme_id, section) tuples
"""
import json
import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# Load theme→section dictionary and theme→title once
# ══════════════════════════════════════════════════════════════════════

_THEME_TO_SECTION: Dict[str, str] = {}
_THEME_TO_TITLE: Dict[str, str] = {}   # theme_id -> human title from JSONL
_THEMES_BY_GRADE: Dict[int, List[str]] = {}
_THEMES_BY_GRADE_SECTION: Dict[str, List[str]] = {}  # key: "grade:section"
_ALL_THEMES: List[Tuple[str, str]] = []  # (theme_id, section)

_loaded = False


def _load():
    global _THEME_TO_SECTION, _THEME_TO_TITLE, _THEMES_BY_GRADE, _THEMES_BY_GRADE_SECTION, _ALL_THEMES, _loaded
    if _loaded:
        return

    # Load theme_to_section.json — canonical source for both section & grade
    path = os.path.join(os.path.dirname(__file__), '..', 'data', 'theme_to_section.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            _THEME_TO_SECTION = json.load(f)
        logger.info("theme_registry: loaded %d theme→section mappings", len(_THEME_TO_SECTION))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error("theme_registry: cannot load %s: %s", path, e)
        _THEME_TO_SECTION = {}

    # Load human-readable theme titles from JSONL
    _THEME_TO_TITLE.clear()
    jsonl_path = os.path.join(os.path.dirname(__file__), '..', 'FORMYLA_L1_L5_TOP5.jsonl')
    try:
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    d = json.loads(line)
                    tid = d.get('theme_id', '')
                    title = d.get('theme', '')
                    if tid and title and tid not in _THEME_TO_TITLE:
                        _THEME_TO_TITLE[tid] = title
                except json.JSONDecodeError:
                    continue
        logger.info("theme_registry: loaded %d theme→title mappings from JSONL", len(_THEME_TO_TITLE))
    except FileNotFoundError:
        logger.warning("theme_registry: JSONL file not found at %s, theme titles will fall back to theme_id", jsonl_path)

    # Derive grade→theme mapping from theme_id prefixes (e.g. G5_T002_S0 → grade 5)
    for tid in _THEME_TO_SECTION:
        parts = tid.split('_')
        if len(parts) >= 2 and parts[0].startswith('G'):
            try:
                grade_int = int(parts[0][1:])
            except ValueError:
                continue
            if grade_int not in _THEMES_BY_GRADE:
                _THEMES_BY_GRADE[grade_int] = []
            if tid not in _THEMES_BY_GRADE[grade_int]:
                _THEMES_BY_GRADE[grade_int].append(tid)

    # Build per grade+section index
    CANONICAL_SECTIONS = ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory')
    for grade_int, theme_list in _THEMES_BY_GRADE.items():
        for section_slug in CANONICAL_SECTIONS:
            key = f"{grade_int}:{section_slug}"
            _THEMES_BY_GRADE_SECTION[key] = [
                t for t in theme_list
                if _THEME_TO_SECTION.get(t) == section_slug
            ]

    logger.info("theme_registry: derived themes for grades %s from theme_to_section.json",
                sorted(_THEMES_BY_GRADE.keys()))

    # Build all themes list
    _ALL_THEMES = sorted(
        (tid, section) for tid, section in _THEME_TO_SECTION.items()
    )

    _loaded = True


# ══════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════

def section_of_theme(theme_id: Optional[str]) -> Optional[str]:
    """Return canonical section slug for a theme_id, or None if unknown."""
    if not theme_id:
        return None
    _load()
    return _THEME_TO_SECTION.get(theme_id)


def theme_title(theme_id: Optional[str]) -> str:
    """Return human-readable theme title for a theme_id, or fallback to theme_id itself.

    Loaded from JSONL's `theme` field (e.g. "Многочлены и алгебраические тождества").
    Falls back to theme_id if no title is loaded.
    """
    if not theme_id:
        return ""
    _load()
    return _THEME_TO_TITLE.get(theme_id, theme_id)


def themes_of_grade(grade: int) -> List[str]:
    """Return list of theme_id for a given grade."""
    _load()
    return list(_THEMES_BY_GRADE.get(grade, []))


def themes_of_section(grade: int, section: str) -> List[str]:
    """Return list of theme_id for a given grade+section."""
    _load()
    key = f"{grade}:{section}"
    return list(_THEMES_BY_GRADE_SECTION.get(key, []))


def all_themes() -> List[Tuple[str, str]]:
    """Return list of (theme_id, section) tuples."""
    _load()
    return list(_ALL_THEMES)


def theme_count() -> int:
    """Return number of loaded theme→section mappings."""
    _load()
    return len(_THEME_TO_SECTION)
