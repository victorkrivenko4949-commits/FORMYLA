# -*- coding: utf-8 -*-
"""
URL builder for olimpiada.ru and other olympiad archives.
Maps olympiad slugs + metadata to specific archive pages.
"""

# olimpiada.ru activity IDs for math olympiads
OLIMPIADA_RU_ACTIVITY_IDS = {
    'vsosh': 74,       # ВсОШ математика
    # Add more if needed:
    # 'vsosh_physics': 72,
    # 'vsosh_informatics': 36,
}

# Round slug mapping for olimpiada.ru
ROUND_SLUGS_OLIMPIADA = {
    'school':     'school',
    'municipal':  'municipal',
    'regional':   'region',
    'final':      'final',
}


def build_specific_url(olympiad_slug, year, grade, round_slug, existing_url=None):
    """
    Build the most specific URL possible for an olympiad combo.

    For vsosh: builds https://olimpiada.ru/activity/74/stage/{round}/tasks?year={year}&grade={grade}
    For others: returns existing_url (already points to correct archive)

    Args:
        olympiad_slug: str ('vsosh', 'euler', 'lomonosov', ...)
        year: int (2014)
        grade: int (9)
        round_slug: str ('school', 'municipal', 'regional', 'final')
        existing_url: str (current source_url, used as fallback)

    Returns:
        str: most specific URL available
    """
    activity_id = OLIMPIADA_RU_ACTIVITY_IDS.get(olympiad_slug)

    if activity_id and round_slug in ROUND_SLUGS_OLIMPIADA:
        stage = ROUND_SLUGS_OLIMPIADA[round_slug]
        url = f"https://olimpiada.ru/activity/{activity_id}/stage/{stage}/tasks"
        params = []
        if year:
            params.append(f"year={year}")
        if grade:
            params.append(f"grade={grade}")
        if params:
            url += '?' + '&'.join(params)
        return url

    # For all other olympiads, return existing URL (already specific enough)
    return existing_url


def get_combo_source_url(combo):
    """
    Get the best source URL for a combo dict from OLYMPIADS_DB.

    Args:
        combo: dict with keys: olympiad, year, grade, round, source_url

    Returns:
        str: best URL for this combo
    """
    return build_specific_url(
        olympiad_slug=combo.get('olympiad', ''),
        year=combo.get('year'),
        grade=combo.get('grade'),
        round_slug=combo.get('round', ''),
        existing_url=combo.get('source_url', ''),
    )
