#!/usr/bin/env python
"""
Targeted one-off script to fill the last remaining L2 hole: g6|Теория чисел, делимость.
Makes up to 20 attempts with increasing temperature and explicit anti-duplicate instructions.
"""
import json, sys, os, re, logging, time
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = "adaptive_data/adaptive_full_9120_fixed.json"

def load_db():
    return json.load(open(DB_PATH, encoding='utf-8'))

sys.path.insert(0, os.path.dirname(__file__))
from ai.deepseek_client import DeepSeekClient

# ── Existing tasks (already known) ──
EXISTING_TASKS = [
    "Найдите наименьшее натуральное число, которое при делении на \\(6\\) даёт остаток \\(3\\), при делении на \\(8\\) даёт остаток \\(5\\), а при делении на \\(7\\) не даёт остатка. Найдите наименьшее такое число, меньшее \\(100\\).",
    "Найдите наименьшее натуральное число, которое имеет ровно 8 натуральных делителей (включая 1 и само число).",
    "Сколько чисел от 1 до 100 не делятся ни на 2, ни на 3, ни на 5?",
    "Найдите количество двузначных чисел, которые делятся на 9, но не делятся на 6?",
]

# Fingerprints of existing tasks
EXISTING_FPS = set()
for s in EXISTING_TASKS:
    EXISTING_FPS.add(s[:100].lower().replace(" ", ""))

SYSTEM_PROMPT = "You are a mathematics olympiad problem generator. Output ONLY a valid JSON object. No markdown, no code fences, no explanations."

def build_prompt(temperature):
    """Build a very specific prompt that tells the model what NOT to generate."""
    prompt = f"""Generate ONE olympiad-level mathematics problem for grade 6, topic: "Теория чисел, делимость" (Number Theory, Divisibility).

IMPORTANT: This is a DIFFERENT problem than any of the EXISTING problems listed below. Do NOT generate anything similar.

EXISTING problems already in this cell (DO NOT REPEAT or vary these):
1. Chinese remainder: number giving remainders 3 when divided by 6, 5 when divided by 8, 0 when divided by 7
2. Smallest natural number with exactly 8 divisors
3. Count numbers from 1 to 100 not divisible by 2, 3, or 5
4. Count two-digit numbers divisible by 9 but not divisible by 6

Generate something COMPLETELY DIFFERENT from the above. Possible topics (pick one):
- GCD/LCM problems
- Divisibility rules and proofs
- Prime/composite number properties
- Modular arithmetic puzzles
- Last digit / digit sum problems
- Problems about perfect squares or cubes
- Divisibility by specific numbers (7, 11, 13, etc.)
- Number theory word problems

The problem should be challenging but appropriate for grade 6 students studying number theory.
Include: "statement" (problem text in Russian), "answer" (short final answer), "solution" (step-by-step).

Output ONLY this JSON object:
{{"statement": "...", "answer": "...", "solution": "..."}}
"""
    return prompt


def main():
    client = DeepSeekClient()
    
    for attempt in range(1, 21):
        temp = min(0.5 + attempt * 0.05, 1.2)  # Gradually increase temperature
        logger.info(f"┌─ Attempt {attempt}/20 (temp={temp:.2f}) ──────────────────────")
        
        try:
            prompt = build_prompt(temp)
            raw = client.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=4000,
                temperature=temp,
            )
            
            # Try to extract JSON
            text = raw.strip()
            
            # Find first { and last }
            first_brace = text.find('{')
            last_brace = text.rfind('}')
            if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                json_str = text[first_brace:last_brace+1]
            else:
                logger.warning(f"  No JSON braces found, skipping")
                continue
            
            # Fix escapes
            import re as re_mod
            prev = None
            while prev != json_str:
                prev = json_str
                for old, new in [('\\(', '('), ('\\)', ')'), ('\\[', '['), ('\\]', ']'),
                                 ('\\{', '{'), ('\\}', '}')]:
                    json_str = json_str.replace(old, new)
                json_str = re_mod.sub(r'\\([^"\\/bfnrtu])', r'\1', json_str)
            
            # Parse
            try:
                task = json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(f"  JSON parse failed: {e}")
                continue
            
            stmt = task.get('statement', '').strip()
            ans = task.get('answer', '').strip()
            
            if not stmt or not ans:
                logger.warning(f"  Missing required fields")
                continue
            
            # Check duplicate
            fp = stmt[:100].lower().replace(" ", "")
            if fp in EXISTING_FPS:
                logger.warning(f"  DUPLICATE fingerprint matches existing task! Skipping.")
                logger.warning(f"  Generated: {stmt[:100]}...")
                continue
            
            # Check duplicate against full DB
            db = load_db()
            all_fps = set()
            for t in db:
                s = t.get('statement', '').strip()
                if s:
                    all_fps.add(s[:100].lower().replace(" ", ""))
            
            if fp in all_fps:
                logger.warning(f"  DUPLICATE fingerprint matches DB! Skipping.")
                continue
            
            # SUCCESS! Add to DB
            max_id = max((int(x.get('id', 0)) for x in db if str(x.get('id', '')).isdigit()), default=0)
            task['id'] = max_id + 1
            task['level'] = 2
            task['grade'] = 6
            task['topic'] = "Теория чисел, делимость"
            task['section'] = ""
            task['subject'] = "math"
            
            db.append(task)
            with open(DB_PATH, 'w', encoding='utf-8') as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[OK] SUCCESS! Generated unique task (attempt {attempt})")
            logger.info(f"  Statement: {stmt[:150]}...")
            logger.info(f"  Answer: {ans[:100]}...")
            logger.info(f"  New DB total: {len(db)} tasks")
            
            # Final verification
            l2_after = [t for t in db if t.get('level') == 2]
            cells = defaultdict(list)
            for t in l2_after:
                cells[(t['grade'], t['topic'])].append(t)
            remaining = {k: v for k, v in cells.items() if len(v) < 5}
            if not remaining:
                logger.info("\n" + "="*60)
                logger.info(" ALL L2 CELLS ARE FULL! ")
                logger.info(f"  Total L2 tasks: {len(l2_after)}")
            else:
                logger.info(f"\n[!]️  {len(remaining)} cells still with holes:")
                for (g, tp), ts in sorted(remaining.items()):
                    logger.info(f"  L2|g{g}|{tp} — {len(ts)}/5")
            
            return  # Exit after success
        
        except Exception as e:
            logger.error(f"  Error: {e}")
        
        time.sleep(1)
    
    logger.error(" Failed to generate a unique task after 20 attempts")


if __name__ == '__main__':
    main()
