#!/usr/bin/env python3
"""Replace catalog() in routes/olympiad.py with version that builds proper grade objects."""

import re

path = 'routes/olympiad.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_block = """@olympiad_bp.route('/courses')
def catalog():
    \"\"\"Список доступных курсов ВсОШ (9, 10, 11 класс).\"\"\"
    grades = [9, 10, 11]
    conf_counts = {}
    total_included = 0
    for g in grades:
        q = (db.session.query(VserossCourseEntry.confidence_level)
             .filter(VserossCourseEntry.grade == g))
        entries = q.all()
        conf_counts[g] = {}
        for e in entries:
            c = e.confidence_level if e.confidence_level is not None else 1
            conf_counts[g][c] = conf_counts[g].get(c, 0) + 1
        total_included += len(entries)
    return render_template('olympiad/catalog.html',
                           grades=grades,
                           conf_counts=conf_counts,
                           total_included=total_included,
                           stages=_STAGES,
                           stage_icons=_STAGE_ICONS)"""

new_block = """@olympiad_bp.route('/courses')
def catalog():
    \"\"\"Список доступных курсов ВсОШ (9, 10, 11 класс).\"\"\"
    grade_ids = [9, 10, 11]
    grades_data = []
    total_conf = {1: 0, 2: 0, 3: 0}
    total_included = 0

    for g in grade_ids:
        entries = VserossCourseEntry.query.filter_by(grade=g).all()
        # confidence counts per grade
        conf = {1: 0, 2: 0, 3: 0}
        # stage -> count
        stage_counts = {}
        for e in entries:
            c = e.confidence_level if e.confidence_level is not None else 1
            conf[c] = conf.get(c, 0) + 1
            s = e.stage or 'Неизвестно'
            stage_counts[s] = stage_counts.get(s, 0) + 1

        # Build stages list in _STAGES order
        stages_list = []
        for s in _STAGES:
            if s in stage_counts:
                stages_list.append({'name': s, 'count': stage_counts[s]})
                del stage_counts[s]
        # Add any extra stages not in _STAGES
        for s, cnt in stage_counts.items():
            stages_list.append({'name': s, 'count': cnt})

        # Aggregate global confidence counts
        for k in (1, 2, 3):
            total_conf[k] = total_conf.get(k, 0) + conf.get(k, 0)

        grades_data.append({
            'grade': g,
            'total': len(entries),
            'green': conf.get(3, 0),
            'yellow': conf.get(2, 0),
            'white': conf.get(1, 0),
            'stages': stages_list,
        })
        total_included += len(entries)

    return render_template('olympiad/catalog.html',
                           grades=grades_data,
                           conf_counts=total_conf,
                           total_included=total_included,
                           stages=_STAGES,
                           stage_icons=_STAGE_ICONS)"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"REPLACE OK — catalog() rewritten")
else:
    print(f"ERROR: old_block NOT FOUND in {path}")
    # Show what's actually there
    start = content.find('def catalog()')
    if start >= 0:
        print(f"Found 'def catalog()' at byte {start}")
        snippet = content[start:start+600]
        print(f"--- SNIPPET ---\n{snippet}\n--- END SNIPPET ---")
