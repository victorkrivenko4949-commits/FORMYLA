# -*- coding: utf-8 -*-
"""
LLM-audit zadach 7 klassa (995 zadach)
Zapuskat': python scripts/audit_grade7_llm.py

Chto delaet:
- Beryet vse zadachi class_level=7 iz adaptive_tasks
- Dlya kazhdoy vyzyvat DeepSeek s ocenkoy slozhnosti
- Zapisyvaet llm_suggested_grade, llm_suggested_difficulty,
  llm_quality_score, llm_rationale v BD
- Sokhranenie posle kazhdogo batcha (50 zadach)
- Prodolzhaet s mesta ostanovki (propuskaet uzhe audited)

NICHEGO NE MENYAET v original'nykh polyakh!
Tol'ko zapolnyaet llm_* kolonki.
"""
import sqlite3
import json
import time
import os
import sys
import io
import logging
import datetime
import re

# Fix Windows encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Logging
os.makedirs('scripts/logs', exist_ok=True)
log_file = 'scripts/logs/audit_{}.log'.format(
    datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

DB_PATH = 'instance/formyla.db'
BATCH_SIZE = 50
PAUSE_BETWEEN_CALLS = 1.0  # seconds
MAX_TASK_TEXT_LEN = 800    # truncate long tasks for prompt

# ============================================================
# PROMPT
# ============================================================
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

# ============================================================
# DeepSeek API call (pryamoy, bez importa ai/deepseek_client)
# ============================================================
import requests

def call_deepseek(prompt: str, system: str, api_key: str) -> str:
    """Pryamoy vyzov DeepSeek API."""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
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


def parse_llm_response(raw: str) -> dict:
    """Parset JSON iz otveta LLM."""
    # Udalyaem ```json ... ``` esli est'
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw)
    raw = raw.strip()
    # Udalyaem upravlyayushchie simvoly (krome \n \r \t) kotorye lomayut JSON parser
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw)
    data = json.loads(raw)
    
    # Validaciya i normalizaciya
    result = {
        'suggested_grade': int(data.get('suggested_grade', 7)),
        'suggested_difficulty': int(data.get('suggested_difficulty', 3)),
        'quality_score': float(data.get('quality_score', 0.5)),
        'rationale': str(data.get('rationale', ''))[:500],
        'topic_correct': bool(data.get('topic_correct', True)),
        'concerns': json.dumps(data.get('concerns', []), ensure_ascii=False)
    }
    
    # Klamping
    result['suggested_grade'] = max(5, min(11, result['suggested_grade']))
    result['suggested_difficulty'] = max(1, min(5, result['suggested_difficulty']))
    result['quality_score'] = max(0.0, min(1.0, result['quality_score']))
    
    return result


def main():
    # Proverka API key
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    if not api_key:
        # Pytaemsa zagruzit' iz .env
        env_path = '.env'
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('DEEPSEEK_API_KEY='):
                        api_key = line.split('=', 1)[1].strip().strip('"\'')
                        break
    
    if not api_key:
        logger.error("DEEPSEEK_API_KEY ne naydyen! Ustanovite peremennuyu okruzheniya.")
        sys.exit(1)
    
    logger.info(f"API key naydyen: {api_key[:8]}...")
    
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # Schitaem zadachi
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7")
    total = cur.fetchone()[0]
    
    cur.execute("""
        SELECT COUNT(*) FROM adaptive_tasks 
        WHERE class_level=7 AND llm_audited_at IS NOT NULL
    """)
    already_done = cur.fetchone()[0]
    
    logger.info(f"Vsego zadach 7 klassa: {total}")
    logger.info(f"Uzhe audited: {already_done}")
    logger.info(f"Ostalos': {total - already_done}")
    
    if already_done == total:
        logger.info("Vse zadachi uzhe audited! Zapuskayte audit_grade7_report.py dlya otcheta.")
        conn.close()
        return
    
    # Berym zadachi kotorye eshche ne audited
    cur.execute("""
        SELECT id, topic, difficulty_level, task_text, correct_answer, subtopic
        FROM adaptive_tasks
        WHERE class_level=7 AND llm_audited_at IS NULL
        ORDER BY id
    """)
    tasks = cur.fetchall()
    
    logger.info(f"Nachalo audita {len(tasks)} zadach (batchi po {BATCH_SIZE})...")
    logger.info("=" * 60)
    
    processed = 0
    errors = 0
    batch_num = 0
    
    for i, task in enumerate(tasks):
        task_id = task['id']
        topic = task['topic'] or 'Neizvestno'
        difficulty = task['difficulty_level']
        task_text = (task['task_text'] or '')[:MAX_TASK_TEXT_LEN]
        correct_answer = (task['correct_answer'] or 'ne ukazan')[:200]
        
        # Formiruyem prompt
        prompt = AUDIT_PROMPT.format(
            task_text=task_text,
            correct_answer=correct_answer,
            topic=topic,
            difficulty=difficulty
        )
        
        try:
            raw = call_deepseek(prompt, SYSTEM_PROMPT, api_key)
            result = parse_llm_response(raw)
            
            # Zapisyvaem v BD
            cur.execute("""
                UPDATE adaptive_tasks SET
                    llm_suggested_grade = ?,
                    llm_suggested_difficulty = ?,
                    llm_quality_score = ?,
                    llm_rationale = ?,
                    llm_topic_correct = ?,
                    llm_concerns = ?,
                    llm_audited_at = ?
                WHERE id = ?
            """, (
                result['suggested_grade'],
                result['suggested_difficulty'],
                result['quality_score'],
                result['rationale'],
                1 if result['topic_correct'] else 0,
                result['concerns'],
                datetime.datetime.utcnow().isoformat(),
                task_id
            ))
            
            processed += 1
            
            # Progress log
            if processed % 10 == 0 or processed == 1:
                logger.info(
                    f"[{processed}/{len(tasks)}] ID={task_id} | "
                    f"grade={result['suggested_grade']} | "
                    f"diff={result['suggested_difficulty']} | "
                    f"quality={result['quality_score']:.2f} | "
                    f"{result['rationale'][:60]}..."
                )
            
        except json.JSONDecodeError as e:
            logger.warning(f"[{i+1}] ID={task_id} JSON parse error: {e} | raw: {raw[:100]}")
            errors += 1
        except requests.exceptions.RequestException as e:
            logger.error(f"[{i+1}] ID={task_id} API error: {e}")
            errors += 1
            time.sleep(5)  # Dol'she zhdem pri oshibke API
        except Exception as e:
            logger.error(f"[{i+1}] ID={task_id} Unexpected error: {e}")
            errors += 1
        
        # Sokhranenie posle kazhdogo batcha
        if (i + 1) % BATCH_SIZE == 0:
            conn.commit()
            batch_num += 1
            logger.info(f"--- Batch {batch_num} sohkranen ({i+1}/{len(tasks)}) ---")
        
        # Pauza mezhdu vyzovami
        time.sleep(PAUSE_BETWEEN_CALLS)
    
    # Final'noe sokhranenie
    conn.commit()
    conn.close()
    
    logger.info("=" * 60)
    logger.info(f"AUDIT ZAVERSHEN!")
    logger.info(f"  Obrabotano: {processed}")
    logger.info(f"  Oshibok: {errors}")
    logger.info(f"  Log: {log_file}")
    logger.info("Teper' zapustite: python scripts/audit_grade7_report.py")


if __name__ == '__main__':
    main()
