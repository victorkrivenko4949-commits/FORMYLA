# -*- coding: utf-8 -*-
"""
LLM-audit zadach 6 klassa (927 zadach)
Zapuskat': python scripts/audit_grade6_llm.py

VAZNO:
- Rabotaet TOL'KO s class_level = 6
- NE trogaet zadachi 7 klassa (original_grade=7)
- Zapolnyaet llm_* kolonki dlya 6 klassa
- Prodolzhaet s mesta ostanovki (propuskaet uzhe audited)
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
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

os.makedirs('scripts/logs', exist_ok=True)
log_file = 'scripts/logs/audit_grade6_{}.log'.format(
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
PAUSE_BETWEEN_CALLS = 1.0
MAX_TASK_TEXT_LEN = 800
TARGET_CLASS = 6  # TOCHNO 6 KLASS

SYSTEM_PROMPT = """Ty - ekspert-metodist po matematike dlya rossiyskikh shkol'nikov.
Tvoya zadacha - ocenit' zadachu dlya adaptivnogo testa.
Vsegda otvechay TOL'KO validnym JSON bez kommentariev."""

AUDIT_PROMPT = """Oceni zadachu dlya adaptivnogo testa po matematike.

USLOVIE ZADACHI:
{task_text}

OTVET: {correct_answer}
TEMA: {topic}
TEKUSHCHIY KLASS: 6
TEKUSHCHAYA SLOZHNOST': {difficulty}/7

=== PROGRAMMA 6 KLASSA RF ===

5 KLASS (uzhe znaet): drobi prostye, protsenty bazovye, prostye chisla
6 KLASS (TSEL'):
  - Obyknovennye drobi: vse operatsii, sravnenie, smeshannye chisla
  - Desyatichnye drobi: vse operatsii
  - Protsenty i proportsii: zadachi na protsenty, pryamaya/obratnaya proportsiya
  - Otricatel'nye chisla: ponyatie, sravnenie, deystviya
  - Modul' chisla: opredelenie, svoystva
  - Koordinatnaya ploskost': tochki, otrezki, figury
  - Prosteyshie lineynye uravneniya (ax+b=c)
  - Zadachi na dvizhenie, rabotu, smesi (prostye)
  - Bazovaya geometriya: ugly, treugol'niki, okruzhnost', perimetr, ploshchad'
  - Delimost', NOD/NOK, priznaki delimosti
  - Kombinatorika bazovaya (pravilo summy/proizvedeniya)
  - Logika: prostoy perebor, rytsari i lzhetsy (bazovye)
  - Invarianty (chetnost', raskraski) — olimpiadnyy uroven' dlya 6 klassa
  - Grafy, razrezaniya — olimpiadnyy uroven' dlya 6 klassa
  - Printsip Dirikhle — olimpiadnyy uroven' dlya 6 klassa

7 KLASS (eshche ne znaet):
  - FSU: (a+b)^2, (a-b)(a+b) i t.d.
  - Odnochlen, mnogochlen, razlozhenie na mnozhiteli
  - Sistemy dvukh lineynykh uravneniy
  - Funktsiya y=kx+b, grafik pryamoy
  - Teorema Pifagora, podobie treugol'nikov
  - Dokazatel'stva (krome samykh prostykh)

8+ KLASS (tochno ne dlya 6):
  - Kvadratnye uravneniya
  - Trigonometriya
  - Logarifmy, stepeni

=== SHKALA SLOZHNOSTI (1-5) dlya 6 klassa ===
1 = bazovaya: pryamoe primenenie formuly/opredeleniya
2 = standartnaya: 1-2 shaga, tipovaya zadacha
3 = chut' vyshe standarta: nestandartnyy khod, no v programme
4 = povyshennaya: olimpiadnyy uroven' dlya 6 klassa
5 = olimpiadnaya: zadacha olimpiady vysshego urovnya dlya 6 klassa

=== SHKALA KACHESTVA (0.0-1.0) ===
1.0 = otlichnaya: yasno, korrektno, interesno
0.7 = khoroshaya: minor problemy
0.5 = srednyaya: est' problemy no reshaema
0.3 = plokhaya: ser'yeznye problemy
0.0 = bitaya: nekorrektna

Vernis' STROGIY JSON (bez ```json):
{{
  "suggested_grade": <5-11>,
  "suggested_difficulty": <1-5>,
  "quality_score": <0.0-1.0>,
  "rationale": "<1-2 predlozheniya>",
  "topic_correct": <true/false>,
  "concerns": ["<problema 1>"]
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


def parse_llm_response(raw):
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw)
    raw = raw.strip()
    raw = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', raw)
    data = json.loads(raw)
    result = {
        'suggested_grade': int(data.get('suggested_grade', 6)),
        'suggested_difficulty': int(data.get('suggested_difficulty', 3)),
        'quality_score': float(data.get('quality_score', 0.5)),
        'rationale': str(data.get('rationale', ''))[:500],
        'topic_correct': bool(data.get('topic_correct', True)),
        'concerns': json.dumps(data.get('concerns', []), ensure_ascii=False)
    }
    result['suggested_grade'] = max(5, min(11, result['suggested_grade']))
    result['suggested_difficulty'] = max(1, min(5, result['suggested_difficulty']))
    result['quality_score'] = max(0.0, min(1.0, result['quality_score']))
    return result


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


def main():
    api_key = get_api_key()
    if not api_key:
        logger.error("DEEPSEEK_API_KEY ne naydyen!")
        sys.exit(1)
    logger.info(f"API key: {api_key[:8]}...")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # PROVERKA: tochno 6 klass
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=?", (TARGET_CLASS,))
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=? AND llm_audited_at IS NOT NULL", (TARGET_CLASS,))
    already_done = cur.fetchone()[0]

    logger.info(f"TARGET: class_level = {TARGET_CLASS}")
    logger.info(f"Vsego zadach {TARGET_CLASS} klassa: {total}")
    logger.info(f"Uzhe audited: {already_done}")
    logger.info(f"Ostalos': {total - already_done}")

    # ZASHCHITA: proverka chto ne trogaem 7 klass
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7 AND llm_audited_at IS NOT NULL")
    grade7_audited = cur.fetchone()[0]
    logger.info(f"Grade 7 audited (ne trogaem): {grade7_audited} -- dolzhno ostat'sya {grade7_audited}")

    if already_done == total:
        logger.info("Vse zadachi 6 klassa uzhe audited!")
        conn.close()
        return

    # Berym zadachi 6 klassa kotorye eshche ne audited
    cur.execute("""
        SELECT id, topic, difficulty_level, task_text, correct_answer
        FROM adaptive_tasks
        WHERE class_level = ? AND llm_audited_at IS NULL
        ORDER BY id
    """, (TARGET_CLASS,))
    tasks = cur.fetchall()

    logger.info(f"Nachalo audita {len(tasks)} zadach 6 klassa (batchi po {BATCH_SIZE})...")
    logger.info("=" * 60)

    processed = 0
    errors = 0

    for i, task in enumerate(tasks):
        task_id = task['id']
        topic = task['topic'] or 'Neizvestno'
        difficulty = task['difficulty_level']
        task_text = (task['task_text'] or '')[:MAX_TASK_TEXT_LEN]
        correct_answer = (task['correct_answer'] or 'ne ukazan')[:200]

        prompt = AUDIT_PROMPT.format(
            task_text=task_text,
            correct_answer=correct_answer,
            topic=topic,
            difficulty=difficulty
        )

        try:
            raw = call_deepseek(prompt, SYSTEM_PROMPT, api_key)
            result = parse_llm_response(raw)

            cur.execute("""
                UPDATE adaptive_tasks SET
                    llm_suggested_grade = ?,
                    llm_suggested_difficulty = ?,
                    llm_quality_score = ?,
                    llm_rationale = ?,
                    llm_topic_correct = ?,
                    llm_concerns = ?,
                    llm_audited_at = ?
                WHERE id = ? AND class_level = ?
            """, (
                result['suggested_grade'],
                result['suggested_difficulty'],
                result['quality_score'],
                result['rationale'],
                1 if result['topic_correct'] else 0,
                result['concerns'],
                datetime.datetime.utcnow().isoformat(),
                task_id,
                TARGET_CLASS  # DOPOLNITEL'NAYA ZASHCHITA
            ))

            processed += 1

            if processed % 10 == 0 or processed == 1:
                logger.info(
                    f"[{processed}/{len(tasks)}] ID={task_id} | "
                    f"grade={result['suggested_grade']} | "
                    f"diff={result['suggested_difficulty']} | "
                    f"quality={result['quality_score']:.2f} | "
                    f"{result['rationale'][:60]}..."
                )

        except json.JSONDecodeError as e:
            logger.warning(f"[{i+1}] ID={task_id} JSON error: {e}")
            errors += 1
        except requests.exceptions.RequestException as e:
            logger.error(f"[{i+1}] ID={task_id} API error: {e}")
            errors += 1
            time.sleep(5)
        except Exception as e:
            logger.error(f"[{i+1}] ID={task_id} Error: {e}")
            errors += 1

        if (i + 1) % BATCH_SIZE == 0:
            conn.commit()
            logger.info(f"--- Batch {(i+1)//BATCH_SIZE} sohkranen ({i+1}/{len(tasks)}) ---")

        time.sleep(PAUSE_BETWEEN_CALLS)

    conn.commit()

    # FINAL PROVERKA: grade 7 ne tronuto
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=7 AND llm_audited_at IS NOT NULL")
    grade7_after = cur.fetchone()[0]
    logger.info(f"Grade 7 audited posle: {grade7_after} (dolzhno = {grade7_audited})")
    if grade7_after != grade7_audited:
        logger.error("PROBLEMA: grade 7 byl izmenen!")
    else:
        logger.info("OK: grade 7 ne tronuto")

    conn.close()
    logger.info("=" * 60)
    logger.info(f"AUDIT 6 KLASSA ZAVERSHEN!")
    logger.info(f"  Obrabotano: {processed}")
    logger.info(f"  Oshibok: {errors}")
    logger.info(f"  Log: {log_file}")
    logger.info("Teper' zapustite: python scripts/audit_grade6_report.py")


if __name__ == '__main__':
    main()
