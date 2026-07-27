#!/usr/bin/env python3
"""Debug actual cell-level prompt response from DeepSeek."""
import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get('DEEPSEEK_API_KEY', '')

# Load one cell worth of data
with open(r'C:\Users\Victor\Downloads\final_clean_dataset_5levels.json', 'r', encoding='utf-8') as f:
    main = json.load(f)
with open(r'C:\Users\Victor\Downloads\final_clean_dataset_5levels_reserve.json', 'r', encoding='utf-8') as f:
    reserve = json.load(f)

# Pick first L1 cell
cell_candidates = []
for t in main:
    if t.get('difficulty') == 1 and t.get('grade') == 5 and t.get('method_code') == 'A1':
        cell_candidates.append(t)
for t in reserve:
    if t.get('difficulty') == 1 and t.get('grade') == 5 and t.get('method_code') == 'A1':
        cell_candidates.append(t)

print(f"Candidates: {len(cell_candidates)}")
for t in cell_candidates:
    print(f"  ID={t['id']}, source={t.get('compression_status')}, text={t.get('task_text','')[:80]}")

# Build prompt like the main script
SYSTEM_PROMPT = """Ты методист российской математической образовательной платформы. Твоя задача — выбрать 5 лучших задач из предложенного пула для ячейки (класс, метод, уровень сложности).

Уровни:
- L1 (уровень 1): базовая школьная задача, один чёткий метод, минимум олимпиадных эвристик, проверяет конкретный навык.
- L2 (уровень 2): школьный олимпиадный уровень или сильная школьная задача, 2-3 осмысленных шага, допускается простое наблюдение, не рутинная L1, но не муниципальный/региональный уровень.

Критерии отбора (по приоритету):
1. Корректность: задача должна быть математически верной, с однозначным ответом.
2. Уровень (level_fit): задача должна строго соответствовать заявленному уровню (L1 или L2).
3. Качество формулировки: чёткое условие, без ambiguity, без опечаток.
4. Разнообразие (diversity_role): выбранные 5 задач должны покрывать разные идеи, подтипы, формы в рамках одного method_code.
5. Полнота: предпочтение задачам с решением и правильным ответом.

Верни ТОЛЬКО валидный JSON без markdown-разметки и пояснений."""

def normalize_text(text):
    import re
    if not text:
        return ""
    s = text.lower()
    s = re.sub(r'\s+', ' ', s).strip()
    for a, b in [('\u201c', "'"), ('\u201d', "'"), ('\u2018', "'"), ('\u2019', "'"),
                 ('\u00ab', "'"), ('\u00bb', "'")]:
        s = s.replace(a, b)
    s = s.replace('$$', '$').replace('\\[', '$').replace('\\]', '$')
    s = s.replace('\\(', '$').replace('\\)', '$')
    s = re.sub(r'\\(displaystyle|textstyle|scriptstyle|limits|nolimits|big|bigg|Big|Bigg)\b', '', s)
    s = re.sub(r'\\(quad|qquad|enspace|thinspace)\b', ' ', s)
    s = re.sub(r'\\(label|tag)\s*\{[^}]*\}', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

# Check duplicates
from collections import defaultdict
norm_map = defaultdict(list)
for t in cell_candidates:
    key = normalize_text(t.get('task_text', ''))
    norm_map[key].append(t['id'])
for k, v in norm_map.items():
    if len(v) > 1:
        print(f"  DUPLICATE: {v} -> '{k[:60]}'")

# Build user prompt
grade, method_code, difficulty = 5, 'A1', 1
lines = [f"Класс: {grade}", f"Метод: {method_code}", f"Уровень: L1 (уровень {difficulty})"]
lines.append("")
lines.append("Кандидаты:")
for t in cell_candidates:
    tid = t['id']
    text = (t.get('task_text', '') or '')[:300]
    has_solution = 'yes' if t.get('solution') else 'no'
    has_answer = 'yes' if t.get('correct_answer') else 'no'
    source = t.get('compression_status', 'main')
    lines.append(f"  [{tid}] | Источник: {source} | Решение: {has_solution} | Ответ: {has_answer}")
    lines.append(f"      Условие: {text}")
lines.append("")
lines.append("Выбери ровно 5 лучших задач. Верни JSON:")
lines.append('{')
lines.append('  "selected_ids": [id1, id2, id3, id4, id5],')
lines.append('  "ranking": {')
lines.append('    "<id>": { "level_fit": <1-10>, "quality": <1-10>, "diversity_role": "<str>", "reason": "<str>" }')
lines.append('  },')
lines.append('  "rejected_ids": [<id>, ...],')
lines.append('  "rejected_reasons": { "<id>": "<reason>" },')
lines.append('  "cell_summary": "<str>"')
lines.append('}')
user_prompt = '\n'.join(lines)

print(f"\nUser prompt length: {len(user_prompt)} chars")

payload = {
    'model': 'deepseek-chat',
    'messages': [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': user_prompt},
    ],
    'temperature': 0.1,
    'max_tokens': 4000,
}

headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json',
}

print("\nCalling DeepSeek API...")
resp = requests.post('https://api.deepseek.com/v1/chat/completions', json=payload, headers=headers, timeout=60)
print(f"HTTP {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    content = data['choices'][0]['message']['content']
    print(f"\nRaw response content:")
    print("=" * 50)
    print(content)
    print("=" * 50)
    
    # Try to parse as JSON
    content_clean = content.strip()
    if content_clean.startswith('```'):
        content_clean = content_clean.split('\n', 1)[-1] if '\n' in content_clean else content_clean[3:]
    if content_clean.endswith('```'):
        content_clean = content_clean.rsplit('```', 1)[0]
    content_clean = content_clean.strip()
    
    try:
        parsed = json.loads(content_clean)
        print(f"\nJSON parsed successfully!")
        print(f"Keys: {list(parsed.keys())}")
        print(f"selected_ids: {parsed.get('selected_ids')}")
        print(f"rejected_ids: {parsed.get('rejected_ids')}")
    except json.JSONDecodeError as e:
        print(f"\nJSON parse error: {e}")
        # Try regex extraction
        import re
        match = re.search(r'\{.*\}', content_clean, re.DOTALL)
        if match:
            try:
                parsed2 = json.loads(match.group(0))
                print(f"Regex extraction succeeded!")
                print(f"Keys: {list(parsed2.keys())}")
                print(f"selected_ids: {parsed2.get('selected_ids')}")
            except json.JSONDecodeError:
                print(f"Regex JSON also failed")
else:
    print(f"Error response: {resp.text[:500]}")
