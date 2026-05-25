# -*- coding: utf-8 -*-
"""Strict problem lookup for AI tutor endpoints (regression fix)."""


def find_problem_for_tutor(problems_db, problem_id):
    """Look up by id strictly in PROBLEMS_DB. Return None if id missing
    or text is empty (so the caller can return 404).
    """
    if problem_id is None:
        return None
    try:
        pid_int = int(problem_id)
    except (ValueError, TypeError):
        return None
    for p in problems_db or []:
        try:
            if int(p.get('id')) != pid_int:
                continue
        except (ValueError, TypeError):
            continue
        text_val = (p.get('text') or '').strip()
        if not text_val:
            return None
        return p
    return None