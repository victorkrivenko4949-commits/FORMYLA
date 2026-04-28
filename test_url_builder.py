# -*- coding: utf-8 -*-
from services.olimpiada_url import get_combo_source_url

tests = [
    {
        'name': 'vsosh regional 2014 grade 9',
        'combo': {'olympiad': 'vsosh', 'year': 2014, 'grade': 9, 'round': 'regional',
                  'source_url': 'https://olimpiada.ru/activity/74/tasks'}
    },
    {
        'name': 'vsosh school 2020 grade 11',
        'combo': {'olympiad': 'vsosh', 'year': 2020, 'grade': 11, 'round': 'school',
                  'source_url': 'https://olimpiada.ru/activity/74/tasks'}
    },
    {
        'name': 'vsosh final 2019 grade 10',
        'combo': {'olympiad': 'vsosh', 'year': 2019, 'grade': 10, 'round': 'final',
                  'source_url': 'https://olimpiada.ru/activity/74/tasks'}
    },
    {
        'name': 'euler final 2015 grade 8 (should keep original)',
        'combo': {'olympiad': 'euler', 'year': 2015, 'grade': 8, 'round': 'final',
                  'source_url': 'https://www.euler.ru/olympiad/archive/'}
    },
    {
        'name': 'lomonosov qualifying 2020 grade 9 (should keep original)',
        'combo': {'olympiad': 'lomonosov', 'year': 2020, 'grade': 9, 'round': 'qualifying',
                  'source_url': 'https://olymp.msu.ru/rus/page/main/29/page/arhiv-zadanij-i-otvetov-olimpiady-shkolnikov-lomonosov'}
    },
]

for t in tests:
    url = get_combo_source_url(t['combo'])
    print(f"{t['name']}:")
    print(f"  -> {url}")
    print()
