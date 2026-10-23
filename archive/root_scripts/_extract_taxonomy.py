#!/usr/bin/env python3
"""Извлекает 128-theme таксономию из target_grid.json и сохраняет как taxonomy_by_grade.json для конвейера."""
import json, os, hashlib
from collections import defaultdict
from datetime import datetime, timezone

def extract_taxonomy():
    """Извлекаем плоскую таксономию из target_grid.json."""
    tg_path = 'l1_l3_generation/target_grid.json'
    with open(tg_path, 'r', encoding='utf-8') as f:
        tg = json.load(f)
    
    grades = tg.get('grades', {})
    themes_by_grade = defaultdict(list)
    theme_definitions = {}
    
    for gk in sorted(grades.keys()):
        g = int(gk)
        gdata = grades[gk]
        topics = gdata.get('topics', {})
        for tid, tinfo in topics.items():
            topic_name = tinfo.get('topic_name', '?')
            subs = tinfo.get('subtopics', {})
            for sid, sinfo in subs.items():
                if not sinfo.get('allowed', True):
                    continue
                subtopic_name = sinfo.get('subtopic_name', '?')
                # Определяем section на основе темы
                section = tinfo.get('section_name', topic_name)
                if not section:
                    section = topic_name
                
                theme_id = f"G{g}_{tid}_{sid}"
                theme_name = f"{topic_name}: {subtopic_name}"
                
                themes_by_grade[g].append({
                    'theme_id': theme_id,
                    'theme': theme_name,
                    'section': section,
                    'core_topic': tid,
                    'subtopic': sid
                })
                
                theme_definitions[theme_id] = {
                    'name': theme_name,
                    'section': section,
                    'grade': g,
                    'core_topic': tid,
                    'subtopic': sid,
                    'topic_name': topic_name,
                    'subtopic_name': subtopic_name
                }
    
    # Проверка
    print("=== ИЗВЛЕЧЁННАЯ ТАКСОНОМИЯ ===")
    total = 0
    for g in sorted(themes_by_grade.keys()):
        count = len(themes_by_grade[g])
        print(f"  Grade {g}: {count} themes")
        total += count
    print(f"  Total: {total}")
    
    # Сохраняем
    result = {
        'meta': {
            'total_themes': total,
            'total_cells': total * 3,
            'total_tasks_target': total * 15,
            'source': 'target_grid.json',
            'extracted_at': datetime.now(timezone.utc).isoformat()
        },
        'grades': {str(k): v for k, v in themes_by_grade.items()},
        'theme_definitions': theme_definitions
    }
    
    out_path = 'l1_l3_generation/taxonomy_by_grade.json'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    sha = hashlib.sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    print(f"\nСохранено: {out_path}")
    print(f"SHA-256: {sha}")
    print(f"Ячеек (×3 уровня): {total * 3}")
    print(f"Целевых задач (×5): {total * 15}")
    
    return result, themes_by_grade

if __name__ == '__main__':
    extract_taxonomy()
