#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate 5 calibrated L6 samples for grade 5."""
import os, json, sys, time
sys.path.insert(0, '.')
from ai.deepseek_client import DeepSeekClient

client = DeepSeekClient()

SYSTEM = """You are a methodologist creating HARD olympiad math problems for Russian grade 5 students.

DIFFICULTY LEVEL 6 means:
- NOT a standard textbook problem
- NOT a simple Pigeonhole (N balls K colors = L3)
- NOT 3 knights/liars basic (= L3)
- NOT combinatorics with C(n,k) formula (grade 5 does NOT know C(n,k)!)

L6 MUST HAVE at least one:
(a) NON-OBVIOUS INVARIANT (student discovers what is preserved: parity of sum, coloring, remainder)
(b) TWO-STEP: construct example + prove optimality bound
(c) DOUBLE COUNTING
(d) EXTREMAL PRINCIPLE
(e) NON-TRIVIAL COLORING (checkerboard, diagonal, modular)

FORBIDDEN for grade 5: C(n,k), n!, equations with x, powers>2, negative numbers, modular notation.
ALLOWED: natural numbers, fractions, simple geometry, verbal Pigeonhole, colorings, parity, graphs as dots+lines.

GOOD L6 EXAMPLE:
"Numbers 1..20 on board. Erase any two a,b, write |a-b|. Can 0 remain?"
Solution: Sum parity invariant. 1+...+20=210 even. |a-b| preserves sum parity. 0 is even, possible.
Why L6: invariant discovery + construction.

BAD (NOT L6, is L3):
"50 balls 5 colors. How many to draw for 5 same?" - trivial Pigeonhole.

Return STRICTLY JSON:
{
  "condition": "<problem statement in Russian>",
  "solution": "<step-by-step solution in Russian>",
  "answer": "<short answer>",
  "tags": ["<tag>"],
  "estimated_time_min": <number>,
  "l6_pattern": "<a/b/c/d/e>",
  "banality_score": <1-10, 1=original, 10=textbook>,
  "difficulty_justification": "<why this is L6>"
}
No text outside JSON. No markdown blocks."""

USER = """Generate a HARD L6 problem for grade 5.
Topic: {topic}
Difficulty: 6 (must be genuinely hard, not textbook-standard)
Remember: NO C(n,k), NO equations with x. Only grade 5 math apparatus.
Return strictly JSON."""

topics = [
    'Principle Dirichlet (non-trivial application)',
    'Invariants and parity',
    'Logic (knights and liars, complex scenario)',
    'Geometric cutting and tiling',
    'Graphs (friendships, routes)',
]

results = []
for i, topic in enumerate(topics):
    print(f'Generating L6 v2 #{i+1}: {topic}...')
    try:
        resp = client.generate(
            prompt=USER.format(topic=topic),
            system_prompt=SYSTEM,
            temperature=0.7,
            max_tokens=2000
        )
        resp_clean = resp.strip()
        if resp_clean.startswith('```'):
            lines = resp_clean.split('\n')
            resp_clean = '\n'.join(lines[1:])
            if '```' in resp_clean:
                resp_clean = resp_clean[:resp_clean.rfind('```')]
        task = json.loads(resp_clean)
        results.append({'topic': topic, 'task': task})
        cond = task.get('condition', '')[:80]
        bs = task.get('banality_score', '?')
        pat = task.get('l6_pattern', '?')
        print(f'  OK [banality={bs}, pattern={pat}]: {cond}...')
    except Exception as e:
        results.append({'topic': topic, 'error': str(e), 'raw': resp[:300] if 'resp' in dir() else 'no resp'})
        print(f'  ERROR: {e}')
    time.sleep(1)

with open('data/audit/grade5_l6_v2_samples.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print('\n' + '='*80)
for i, r in enumerate(results):
    print(f'\n--- L6 v2 #{i+1}: {r["topic"]} ---')
    if 'task' in r:
        t = r['task']
        print(f'Condition: {t.get("condition", "N/A")}')
        print(f'Answer: {t.get("answer", "N/A")}')
        print(f'Banality: {t.get("banality_score", "?")}')
        print(f'Pattern: {t.get("l6_pattern", "?")}')
        print(f'Justification: {t.get("difficulty_justification", "?")}')
        sol = t.get('solution', 'N/A')
        print(f'Solution: {sol[:400]}...')
    else:
        print(f'ERROR: {r.get("error", "")}')
print('\nSaved to data/audit/grade5_l6_v2_samples.json')
