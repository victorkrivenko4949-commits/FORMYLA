# -*- coding: utf-8 -*-
"""
Test LLM audita na 3 zadachakh (po 1 iz diff=1, diff=4, diff=7)
Zapuskat': python scripts/test_audit_llm_3tasks.py
"""
import sqlite3
import json
import time
import os
import sys
import io
import re
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = 'instance/formyla.db'

SYSTEM_PROMPT = """Ty - ekspert-metodist po matematike dlya rossiyskikh shkol'nikov.
Tvoya zadacha - ocenit' zadachu dlya adaptivnogo testa.
Vsegda otvechay TOL'KO validnym JSON bez kommentariev."""

AUDIT_PROMPT = """Oceni zadachu dlya adaptivnogo testa po matematike.

USLOVIE ZADACHI:
{task_text}

OTVET: {correct_answer}
TEMA: {topic}
TEKUSHCHIY KLASS: 7
TEKUSHCHAYA SLOZHNOST': {difficulty}/7

=== PROGRAMMA ROSSIYSKOY SHKOLY ===

5 KLASS: drobi, protsenty, prostye chisla, osnovy geometrii
6 KLASS: otricatel'nye chisla, proportsii, koordinaty, NOD/NOK
7 KLASS (TSEL'): 
  - Algebra: lineynye uravneniya, FSU (a+b)^2 (a-b)(a+b), odnochlen, 
    mnogochlen, razlozhenie na mnozhiteli
  - Geometriya: ugly (vertikal'nye, smezhnye), ravnobedrennyy treugol'nik,
    priznaki ravenstva treugol'nikov, parallel'nye pryamye
  - Logika: prostoy perebor, printsip Dirikhle (bazovyy)
8 KLASS: kvadratnye uravneniya, teorema Pifagora, podobie treugol'nikov
9 KLASS: progressii, trigonometriya, vektor, sistemy s parametrom
10-11 KLASS: logarifmy, proizvodnaya, integral, kombinatorika C(n,k)

=== CHTO NE DOLZHNO BYT' V 7 KLASSE ===
- Kvadratnye uravneniya (8 klass)
- Teorema Pifagora (8 klass)
- Podobie treugol'nikov (8 klass)
- Neravenstvo Koshi-Bunyakovskogo (9-10 klass)
- Funktsional'nye uravneniya f(m+n)=... (10-11 klass)
- Kombinatorika s C(n,k) (10 klass)
- Indukciya (9-10 klass)
- Slozhnyye invarianty (9+ klass)

=== SHKALA SLOZHNOSTI (1-5) dlya ukazannogo klassa ===
1 = bazovaya: pryamoe primenenie formuly/opredeleniya
2 = standartnaya: 1-2 shaga, tipovaya zadacha
3 = chut' vyshe standarta: nestandartnyy khod, no v programme
4 = povyshennaya: olimpiadnyy uroven' dlya etogo klassa
5 = olimpiadnaya: zadacha olimpiady vysshego urovnya dlya etogo klassa

=== SHKALA KACHESTVA (0.0-1.0) ===
1.0 = otlichnaya: yasno, korrektno, interesno
0.7 = khoroshaya: minor problemy s formulirovkoy
0.5 = srednyaya: est' problemy no zadacha reshaema
0.3 = plokhaya: ser'yeznye problemy s formulirovkoy ili otvetom
0.0 = bitaya: zadacha nekorrektna, ne imeet smysla

Vernis' STROGIY JSON (bez ```json, bez kommentariev):
{{
  "suggested_grade": <5-11>,
  "suggested_difficulty": <1-5>,
  "quality_score": <0.0-1.0>,
  "rationale": "<1-2 predlozheniya ob'yasneniya>",
  "topic_correct": <true/false>,
  "concerns": ["<problema 1>", "<problema 2>"]
}}"""


def call_deepseek(prompt, system, api_key):
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 512,
        "response_format": {"type": "json_object"}
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()['choices'][0]['message']['content']


def get_api_key():
    key = os.environ.get('DEEPSEEK_API_KEY')
    if key:
        return key
    for env_file in ['.env', '.env.local']:
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('DEEPSEEK_API_KEY='):
                        return line.split('=', 1)[1].strip().strip('"\'')
    return None


api_key = get_api_key()
if not api_key:
    print("ERROR: DEEPSEEK_API_KEY ne naydyen!")
    sys.exit(1)
print(f"API key: {api_key[:8]}...")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Berym 3 zadachi: diff=1, diff=4, diff=7
test_tasks = []
for diff in [1, 4, 7]:
    cur = conn.cursor()
    cur.execute("""
        SELECT id, topic, difficulty_level, task_text, correct_answer
        FROM adaptive_tasks WHERE class_level=7 AND difficulty_level=?
        ORDER BY RANDOM() LIMIT 1
    """, (diff,))
    row = cur.fetchone()
    if row:
        test_tasks.append(dict(row))

print(f"\nTestiruem na {len(test_tasks)} zadachakh...\n")
print("=" * 70)

for task in test_tasks:
    print(f"\n--- ZADACHA ID={task['id']} | Topic: {task['topic']} | Orig diff: {task['difficulty_level']} ---")
    print(f"Task (first 200): {task['task_text'][:200]}")
    print(f"Answer: {task['correct_answer'][:100]}")
    
    prompt = AUDIT_PROMPT.format(
        task_text=task['task_text'][:800],
        correct_answer=(task['correct_answer'] or '')[:200],
        topic=task['topic'],
        difficulty=task['difficulty_level']
    )
    
    try:
        raw = call_deepseek(prompt, SYSTEM_PROMPT, api_key)
        print(f"\nLLM raw response:\n{raw}")
        
        # Parse
        raw_clean = re.sub(r'```json\s*', '', raw)
        raw_clean = re.sub(r'```\s*', '', raw_clean).strip()
        data = json.loads(raw_clean)
        
        print(f"\nParsed result:")
        print(f"  suggested_grade:      {data.get('suggested_grade')}")
        print(f"  suggested_difficulty: {data.get('suggested_difficulty')}")
        print(f"  quality_score:        {data.get('quality_score')}")
        print(f"  topic_correct:        {data.get('topic_correct')}")
        print(f"  rationale:            {data.get('rationale')}")
        print(f"  concerns:             {data.get('concerns')}")
        
        grade_ok = "OK" if data.get('suggested_grade') == 7 else f"MOVE to {data.get('suggested_grade')}"
        diff_delta = task['difficulty_level'] - (data.get('suggested_difficulty') or 0)
        print(f"\n  VERDICT: grade={grade_ok} | diff_delta={diff_delta:+d}")
        
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print("-" * 70)
    time.sleep(1)

conn.close()
print("\n\nTest zavershen. Esli vse OK - mozhno zapuskat' polnyy audit:")
print("  python scripts/audit_grade7_llm.py")
print("\nOzhidaemoe vremya polnogo audita 995 zadach:")
print("  ~995 sekund = ~17 minut (1 sek pauza mezhdu vyzovami)")
