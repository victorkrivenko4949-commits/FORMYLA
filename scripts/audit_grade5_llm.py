# -*- coding: utf-8 -*-
"""
LLM-audit zadach 5 klassa (949 zadach)
Zapuskat': python scripts/audit_grade5_llm.py

VAZNO:
- Rabotaet TOL'KO s class_level = 5
- NE trogaet zadachi 6 i 7 klassa
- Zapolnyaet llm_* kolonki dlya 5 klassa
- Prodolzhaet s mesta ostanovki
"""
import sqlite3, json, time, os, sys, io, logging, datetime, re, requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

os.makedirs('scripts/logs', exist_ok=True)
log_file = 'scripts/logs/audit_grade5_{}.log'.format(
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
TARGET_CLASS = 5

SYSTEM_PROMPT = """Ty - ekspert-metodist po matematike dlya rossiyskikh shkol'nikov.
Tvoya zadacha - ocenit' zadachu dlya adaptivnogo testa.
Vsegda otvechay TOL'KO validnym JSON bez kommentariev."""

AUDIT_PROMPT = """Oceni zadachu dlya adaptivnogo testa po matematike.

USLOVIE ZADACHI:
{task_text}

OTVET: {correct_answer}
TEMA: {topic}
TEKUSHCHIY KLASS: 5
TEKUSHCHAYA SLOZHNOST': {difficulty}/7

=== PROGRAMMA 5 KLASSA RF ===

4 KLASS (uzhe znaet): prostye operatsii s chislami, drobi bazovye
5 KLASS (TSEL'):
  - Drobi: obyknovennye i desyatichnye, vse operatsii
  - Protsenty bazovye
  - Prostye chisla, razlozhenie na mnozhiteli
  - Delimost' (na 2,3,5,9,10)
  - Koordinatnaya pryamaya
  - Prosteyshie uravneniya (x+a=b, ax=b)
  - Geometriya: ploshchad', perimetr, ob'em
  - Logika: prostoy perebor, rytsari i lzhetsy (bazovye)
  - Invarianty (chetnost') — olimpiadnyy uroven' dlya 5 klassa
  - Kombinatorika (pravilo summy/proizvedeniya) — olimpiadnyy
  - Vzveshipaniya, perelivaniya — olimpiadnyy
  - Grafy bazovye — olimpiadnyy
  - Printsip Dirikhle — olimpiadnyy
  - Tekstovye zadachi (rabota, dvizhenie) — olimpiadnyy

6 KLASS (eshche ne znaet):
  - Otricatel'nye chisla
  - Koordinatnaya ploskost' (2D)
  - NOD/NOK (prodvinutyy)
  - Proportsii i proportsional'nost'

7+ KLASS (tochno ne dlya 5):
  - Algebra (FSU, mnogochleny)
  - Geometriya (dokazatel'stva, teoremy)
  - Sistemy uravneniy

=== SHKALA SLOZHNOSTI (1-5) dlya 5 klassa ===
1 = bazovaya: pryamoe primenenie formuly
2 = standartnaya: 1-2 shaga
3 = chut' vyshe standarta: nestandartnyy khod
4 = povyshennaya: olimpiadnyy uroven' dlya 5 klassa
5 = olimpiadnaya: zadacha olimpiady vysshego urovnya

=== SHKALA KACHESTVA (0.0-1.0) ===
1.0 = otlichnaya
0.7 = khoroshaya
0.5 = srednyaya
0.3 = plokhaya
0.0 = bitaya

Vernis' STROGIY JSON (bez ```json):
{{
  "suggested_grade": <4-8>,
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
        'suggested_grade': int(data.get('suggested_grade', 5)),
        'suggested_difficulty': int(data.get('suggested_difficulty', 3)),
        'quality_score': float(data.get('quality_score', 0.5)),
        'rationale': str(data.get('rationale', ''))[:500],
        'topic_correct': bool(data.get('topic_correct', True)),
        'concerns': json.dumps(data.get('concerns', []), ensure_ascii=False)
    }
    result['suggested_grade'] = max(4, min(8, result['suggested_grade']))
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

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=?", (TARGET_CLASS,))
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level=? AND llm_audited_at IS NOT NULL", (TARGET_CLASS,))
    already_done = cur.fetchone()[0]

    # Proverka chto drugie klassy ne tronuto
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level IN (6,7) AND llm_audited_at IS NOT NULL")
    other_audited = cur.fetchone()[0]

    logger.info(f"TARGET: class_level = {TARGET_CLASS}")
    logger.info(f"Vsego zadach {TARGET_CLASS} klassa: {total}")
    logger.info(f"Uzhe audited: {already_done}")
    logger.info(f"Ostalos': {total - already_done}")
    logger.info(f"Grade 6+7 audited (ne trogaem): {other_audited}")

    if already_done == total:
        logger.info("Vse zadachi 5 klassa uzhe audited!")
        conn.close()
        return

    cur.execute("""
        SELECT id, topic, difficulty_level, task_text, correct_answer
        FROM adaptive_tasks
        WHERE class_level = ? AND llm_audited_at IS NULL
        ORDER BY id
    """, (TARGET_CLASS,))
    tasks = cur.fetchall()

    logger.info(f"Nachalo audita {len(tasks)} zadach 5 klassa (batchi po {BATCH_SIZE})...")
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
                TARGET_CLASS
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

    # Final check
    cur.execute("SELECT COUNT(*) FROM adaptive_tasks WHERE class_level IN (6,7) AND llm_audited_at IS NOT NULL")
    other_after = cur.fetchone()[0]
    logger.info(f"Grade 6+7 audited posle: {other_after} (dolzhno = {other_audited})")
    if other_after != other_audited:
        logger.error("PROBLEMA: grade 6/7 byl izmenen!")
    else:
        logger.info("OK: grade 6/7 ne tronuto")

    conn.close()
    logger.info("=" * 60)
    logger.info(f"AUDIT 5 KLASSA ZAVERSHEN! Obrabotano: {processed}, Oshibok: {errors}")
    logger.info("Teper' zapustite: python scripts/audit_grade5_report.py")


if __name__ == '__main__':
    main()
