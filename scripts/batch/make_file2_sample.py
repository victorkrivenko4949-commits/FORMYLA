# -*- coding: utf-8 -*-
"""Создать sample из файла geometry_needs_figure (2).jsonl (2187 задач).

Формат: {idx, grade, level, topic, task_text, correct_answer, solution}.
Нормализуем в схему batch: task_id=idx, condition=task_text, solution, answer.
Все с решением -> group A (condition_solution).
"""
import io, sys, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SRC = r'C:\Users\Redmi\Downloads\geometry_needs_figure (2).jsonl'
_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'out')

rows = []
with open(SRC, encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        rows.append({
            'task_id': f"f2_{r.get('idx')}",
            'grade': r.get('grade'),
            'condition': r.get('task_text') or '',
            'solution': r.get('solution') or '',
            'answer': r.get('correct_answer') or '',
            'level': r.get('level'),
            'needs_figure': True,
            'group': 'A',
            '_orig_idx': r.get('idx'),
        })

out_path = os.path.join(_OUT, 'sample_file2.jsonl')
with open(out_path, 'w', encoding='utf-8') as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f"file2 sample: {len(rows)} tasks -> {out_path}")
