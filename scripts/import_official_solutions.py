# -*- coding: utf-8 -*-
"""
scripts/import_official_solutions.py

Phase 3: Batch import of official source metadata for olympiad combos.

Strategy:
  1. For each combo, build a deterministic source_url from known archive patterns.
  2. Use DeepSeek API to find/verify the official solution for each problem.
  3. Write results back to olympiads.py with new fields:
       source_url, source_name, solution_verified, official_solution (per problem)
  4. Log everything to logs/solution_import.log

Run:
    python scripts/import_official_solutions.py [--dry-run] [--limit N] [--olympiad vsosh]
"""

import sys
import os
import json
import re
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ─────────────────────────────────────────────────────────────────────────────
# OFFICIAL ARCHIVE URL PATTERNS
# These are deterministic — no AI needed, just known archive structures.
# ─────────────────────────────────────────────────────────────────────────────

OLYMPIAD_ARCHIVE_URLS = {
    # ВсОШ — Всероссийская олимпиада школьников
    'vsosh': {
        'base': 'https://olimpiada.ru/activity/74/tasks',
        'name': 'Всероссийская олимпиада школьников (ВсОШ)',
        'round_urls': {
            'school':     'https://olimpiada.ru/activity/74/tasks',
            'municipal':  'https://olimpiada.ru/activity/74/tasks',
            'regional':   'https://olimpiada.ru/activity/74/tasks',
            'final':      'https://olimpiada.ru/activity/74/tasks',
        },
        'pdf_pattern': 'https://olimpiada.ru/activity/74/tasks/{year}',
        'problems_ru': 'https://problems.ru/search/?q={query}',
    },

    # Олимпиада Эйлера
    'euler': {
        'base': 'https://www.euler.ru/olympiad/',
        'name': 'Олимпиада Эйлера',
        'round_urls': {
            'qualifying': 'https://www.euler.ru/olympiad/archive/',
            'final':      'https://www.euler.ru/olympiad/archive/',
            'regional':   'https://www.euler.ru/olympiad/archive/',
        },
        'pdf_pattern': 'https://www.euler.ru/olympiad/archive/{year}/',
    },

    # Формула единства / Третье тысячелетие
    'formula_unity': {
        'base': 'https://www.formulo.org/ru/olymp/',
        'name': 'Олимпиада «Формула единства» / «Третье тысячелетие»',
        'round_urls': {
            'qualifying': 'https://www.formulo.org/ru/olymp/{year}-math/',
            'final':      'https://www.formulo.org/ru/olymp/{year}-math/',
        },
        'pdf_pattern': 'https://www.formulo.org/ru/olymp/{year}-math/',
    },

    # Турнир городов
    'turgor': {
        'base': 'https://turgor.ru/tg/problems/',
        'name': 'Турнир городов',
        'round_urls': {
            'autumn_base':  'https://turgor.ru/tg/problems/',
            'autumn_hard':  'https://turgor.ru/tg/problems/',
            'spring_base':  'https://turgor.ru/tg/problems/',
            'spring_hard':  'https://turgor.ru/tg/problems/',
            'qualifying':   'https://turgor.ru/tg/problems/',
            'final':        'https://turgor.ru/tg/problems/',
        },
        'pdf_pattern': 'https://turgor.ru/tg/problems/{year}/',
    },

    # Олимпиада Ломоносова (МГУ)
    'lomonosov': {
        'base': 'https://olymp.msu.ru/rus/page/main/29/page/arhiv-zadanij-i-otvetov-olimpiady-shkolnikov-lomonosov',
        'name': 'Олимпиада школьников «Ломоносов» (МГУ)',
        'round_urls': {
            'qualifying': 'https://olymp.msu.ru/rus/page/main/29/page/arhiv-zadanij-i-otvetov-olimpiady-shkolnikov-lomonosov',
            'final':      'https://olymp.msu.ru/rus/page/main/29/page/arhiv-zadanij-i-otvetov-olimpiady-shkolnikov-lomonosov',
        },
        'pdf_pattern': 'https://olymp.msu.ru/rus/page/main/29/page/arhiv-zadanij-i-otvetov-olimpiady-shkolnikov-lomonosov',
    },

    # Покори Воробьёвы горы (ПВГ)
    'pvg': {
        'base': 'https://pvg.mk.ru/archive/',
        'name': 'Олимпиада «Покори Воробьёвы горы!»',
        'round_urls': {
            'qualifying': 'https://pvg.mk.ru/archive/',
            'final':      'https://pvg.mk.ru/archive/',
        },
        'pdf_pattern': 'https://pvg.mk.ru/archive/{year}/',
    },

    # Высшая проба (НИУ ВШЭ)
    'vysshaya_proba': {
        'base': 'https://olymp.hse.ru/mmo/tasks-math',
        'name': 'Олимпиада «Высшая проба» (НИУ ВШЭ)',
        'round_urls': {
            'qualifying': 'https://olymp.hse.ru/mmo/tasks-math',
            'final':      'https://olymp.hse.ru/mmo/tasks-math',
        },
        'pdf_pattern': 'https://olymp.hse.ru/mmo/tasks-math',
    },

    # Физтех (МФТИ)
    'phystech': {
        'base': 'https://olymp.mipt.ru/math/archive/',
        'name': 'Олимпиада «Физтех» (МФТИ)',
        'round_urls': {
            'qualifying': 'https://olymp.mipt.ru/math/archive/',
            'final':      'https://olymp.mipt.ru/math/archive/',
        },
        'pdf_pattern': 'https://olymp.mipt.ru/math/archive/{year}/',
    },

    # Олимпиада Курчатова
    'kurchatov': {
        'base': 'https://old.olimpiadakurchatova.ru/archive',
        'name': 'Олимпиада Курчатова',
        'round_urls': {
            'qualifying': 'https://old.olimpiadakurchatova.ru/archive',
            'final':      'https://old.olimpiadakurchatova.ru/archive',
        },
        'pdf_pattern': 'https://old.olimpiadakurchatova.ru/archive',
    },

    # СПбГУ
    'spbgu': {
        'base': 'https://olymp.spbu.ru/math/archive/',
        'name': 'Олимпиада СПбГУ по математике',
        'round_urls': {
            'qualifying': 'https://olymp.spbu.ru/math/archive/',
            'final':      'https://olymp.spbu.ru/math/archive/',
        },
        'pdf_pattern': 'https://olymp.spbu.ru/math/archive/{year}/',
    },
}

ROUND_DISPLAY_NAMES = {
    'school':       'Школьный этап',
    'municipal':    'Муниципальный этап',
    'regional':     'Региональный этап',
    'final':        'Заключительный этап',
    'qualifying':   'Отборочный тур',
    'autumn_base':  'Осенний тур (базовый)',
    'autumn_hard':  'Осенний тур (сложный)',
    'spring_base':  'Весенний тур (базовый)',
    'spring_hard':  'Весенний тур (сложный)',
    'distance':     'Дистанционный тур',
    'spring_basic': 'Весенний тур (базовый)',
    'fall_hard':    'Осенний тур (сложный)',
    'fall_basic':   'Осенний тур (базовый)',
    '1':            'Тур 1',
    '2':            'Тур 2',
}


def get_source_url(combo: dict) -> str:
    """Build deterministic source URL for a combo."""
    olympiad = combo.get('olympiad', '')
    year = combo.get('year', '')
    round_key = combo.get('round', '')

    info = OLYMPIAD_ARCHIVE_URLS.get(olympiad)
    if not info:
        return ''

    # Try round-specific URL first
    round_urls = info.get('round_urls', {})
    url = round_urls.get(round_key, info.get('base', ''))

    # Substitute year if pattern supports it
    url = url.replace('{year}', str(year))

    return url


def get_source_name(combo: dict) -> str:
    """Build human-readable source name for a combo."""
    olympiad = combo.get('olympiad', '')
    year = combo.get('year', '')
    grade = combo.get('grade', '')
    round_key = combo.get('round', '')
    round_title = combo.get('round_title', ROUND_DISPLAY_NAMES.get(round_key, round_key))

    info = OLYMPIAD_ARCHIVE_URLS.get(olympiad)
    olympiad_name = info['name'] if info else combo.get('olympiad_title', olympiad)

    return f"{olympiad_name}, {year} год, {grade} класс, {round_title}"


# ─────────────────────────────────────────────────────────────────────────────
# DEEPSEEK SOLUTION SEARCH
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Ты — архивист математических олимпиад России. Твоя задача — найти РЕАЛЬНОЕ авторское решение олимпиадной задачи из официальных источников.

Источники (в порядке приоритета):
1. problems.ru — крупнейший архив олимпиадных задач
2. olimpiada.ru/vos — архив ВсОШ
3. turgor.ru — Турнир городов
4. mmo.mccme.ru — Московская олимпиада
5. olymp.msu.ru — Олимпиада Ломоносова
6. formulo.org — Формула единства
7. pvg.mk.ru — Покори Воробьёвы горы
8. olymp.hse.ru — Высшая проба

ПРАВИЛА:
- Если знаешь авторское решение из этих источников — дай его точно.
- Если не уверен — дай лучшее математически корректное решение с пометкой.
- НЕ придумывай источники. Если источник неизвестен — оставь source_url пустым.
- LaTeX: используй \\( ... \\) для инлайн, \\[ ... \\] для блоков.
- Дроби: \\frac{a}{b}, корни: \\sqrt{x}, умножение: \\cdot

Верни ТОЛЬКО валидный JSON (без markdown-блоков):
{
  "found": true,
  "source_url": "точная ссылка или пустая строка",
  "confidence": 0.0,
  "official_solution": "решение с LaTeX"
}"""


def fix_latex_json(text: str) -> str:
    """
    Fix common JSON parse errors caused by LaTeX backslashes.
    DeepSeek often returns single backslashes in JSON strings (invalid JSON).
    Doubles all single backslashes that are not already doubled.
    """
    return re.sub(r'(?<!\\)\\(?!\\|")', r'\\\\', text)


def extract_json_fields(text: str) -> dict:
    """
    Robustly extract JSON fields from DeepSeek response even with LaTeX backslash issues.
    Uses regex to extract each field individually.
    """
    result = {}

    # Extract 'found' boolean
    m = re.search(r'"found"\s*:\s*(true|false)', text, re.IGNORECASE)
    if m:
        result['found'] = m.group(1).lower() == 'true'

    # Extract 'confidence' float
    m = re.search(r'"confidence"\s*:\s*([0-9.]+)', text)
    if m:
        try:
            result['confidence'] = float(m.group(1))
        except ValueError:
            result['confidence'] = 0.0

    # Extract 'source_url' string (between quotes, no backslashes expected)
    m = re.search(r'"source_url"\s*:\s*"([^"]*)"', text)
    if m:
        result['source_url'] = m.group(1)

    # Extract 'official_solution' - tricky due to embedded LaTeX
    # Try to find the value between "official_solution": " and the closing "
    m = re.search(r'"official_solution"\s*:\s*"(.*?)(?<!\\)"\s*[,}\n]', text, re.DOTALL)
    if m:
        sol = m.group(1)
        sol = sol.replace('\\"', '"').replace('\\n', '\n').replace('\\t', '\t')
        result['official_solution'] = sol
    else:
        # Fallback: grab everything after the key to end of block
        m = re.search(r'"official_solution"\s*:\s*"(.*)', text, re.DOTALL)
        if m:
            raw = m.group(1)
            end_match = re.search(r'(?<!\\)"\s*[,}]', raw)
            if end_match:
                sol = raw[:end_match.start()]
                sol = sol.replace('\\"', '"').replace('\\n', '\n')
                result['official_solution'] = sol

    return result


def search_official_solution(client, combo: dict, problem: dict) -> dict:
    """
    Use DeepSeek to find/verify official solution for a problem.
    Returns dict with found, source_url, confidence, official_solution.
    Uses 3-strategy JSON parsing to handle LaTeX backslash issues.
    """
    olympiad_name = get_source_name(combo)
    problem_text = problem.get('text', '')
    problem_num = problem.get('num', '?')
    current_solution = problem.get('solution', '')

    user_prompt = f"""Олимпиада: {olympiad_name}
Задача №{problem_num}:

{problem_text}

Текущее решение (возможно AI-сгенерированное, проверь его корректность):
{current_solution[:500] if current_solution else 'Нет решения'}

Найди авторское решение из официальных источников. Если текущее решение математически верно — можешь его улучшить/уточнить. Если содержит ошибки — исправь."""

    try:
        response = client.generate(
            prompt=user_prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=2000
        )

        # Clean response
        text = response.strip()
        # Remove markdown code blocks if present
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
        text = text.strip()

        # Extract JSON block
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            text = match.group(0)

        # Strategy 1: Standard json.loads
        try:
            result = json.loads(text)
            return {
                'found': result.get('found', False),
                'source_url': result.get('source_url', ''),
                'confidence': float(result.get('confidence', 0.0)),
                'official_solution': result.get('official_solution', ''),
            }
        except json.JSONDecodeError:
            pass

        # Strategy 2: Fix LaTeX backslashes and retry
        try:
            fixed = fix_latex_json(text)
            result = json.loads(fixed)
            return {
                'found': result.get('found', False),
                'source_url': result.get('source_url', ''),
                'confidence': float(result.get('confidence', 0.0)),
                'official_solution': result.get('official_solution', ''),
            }
        except json.JSONDecodeError:
            pass

        # Strategy 3: Field-by-field regex extraction (most robust)
        result = extract_json_fields(text)
        if result.get('official_solution') or result.get('found'):
            logging.info(f"  Problem {problem_num}: Parsed via regex fallback")
            return {
                'found': result.get('found', False),
                'source_url': result.get('source_url', ''),
                'confidence': float(result.get('confidence', 0.0)),
                'official_solution': result.get('official_solution', ''),
            }

        # All strategies failed
        logging.warning(f"All parse strategies failed for combo {combo.get('id')} prob {problem_num}")
        return {
            'found': False,
            'source_url': '',
            'confidence': 0.0,
            'official_solution': '',
        }

    except Exception as e:
        logging.warning(f"DeepSeek error for combo {combo.get('id')} prob {problem_num}: {e}")
        return {
            'found': False,
            'source_url': '',
            'confidence': 0.0,
            'official_solution': '',
        }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN BATCH PROCESSOR
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging():
    """Setup logging to both file and console."""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / 'solution_import.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ]
    )
    return log_file


def add_source_metadata_to_combos(olympiads_db: list) -> list:
    """
    Phase 1.3: Add source_url, source_name fields to all combos
    (deterministic, no AI needed).
    """
    updated = 0
    for combo in olympiads_db:
        if not combo.get('source_url'):
            combo['source_url'] = get_source_url(combo)
            updated += 1
        if not combo.get('source_name'):
            combo['source_name'] = get_source_name(combo)

    logging.info(f"Added source metadata to {updated} combos")
    return olympiads_db


def process_batch(olympiads_db: list, client, args) -> dict:
    """
    Main batch processing loop.
    Returns statistics dict.
    """
    stats = {
        'total_combos': 0,
        'total_problems': 0,
        'solutions_found': 0,
        'solutions_high_confidence': 0,
        'needs_manual_review': 0,
        'errors': 0,
        'skipped': 0,
    }

    # Filter combos
    combos_to_process = olympiads_db
    if args.olympiad:
        combos_to_process = [c for c in olympiads_db if c.get('olympiad') == args.olympiad]
        logging.info(f"Filtering to olympiad '{args.olympiad}': {len(combos_to_process)} combos")

    if args.limit:
        combos_to_process = combos_to_process[:args.limit]
        logging.info(f"Limiting to first {args.limit} combos")

    stats['total_combos'] = len(combos_to_process)
    stats['total_problems'] = sum(len(c.get('problems', [])) for c in combos_to_process)

    logging.info(f"Processing {stats['total_combos']} combos, {stats['total_problems']} problems")
    logging.info("=" * 70)

    for combo_idx, combo in enumerate(combos_to_process, 1):
        combo_id = combo.get('id')
        olympiad = combo.get('olympiad')
        year = combo.get('year')
        grade = combo.get('grade')
        round_key = combo.get('round')
        source_name = combo.get('source_name', get_source_name(combo))
        source_url = combo.get('source_url', get_source_url(combo))

        logging.info(f"\n[{combo_idx}/{stats['total_combos']}] Combo {combo_id}: {source_name}")
        logging.info(f"  Source URL: {source_url}")

        problems = combo.get('problems', [])
        combo_solutions_found = 0

        for prob in problems:
            prob_num = prob.get('num')
            stats['total_problems'] += 0  # already counted

            # Skip if already verified
            if prob.get('solution_verified') and not args.force:
                stats['skipped'] += 1
                logging.info(f"  Problem {prob_num}: SKIP (already verified)")
                continue

            if args.dry_run:
                logging.info(f"  Problem {prob_num}: DRY RUN - would search for solution")
                stats['solutions_found'] += 1
                continue

            # Search for official solution
            logging.info(f"  Problem {prob_num}: Searching...")
            result = search_official_solution(client, combo, prob)

            if result['found'] and result['official_solution']:
                prob['official_solution'] = result['official_solution']
                prob['solution_verified'] = result['confidence'] >= 0.85
                prob['solution_confidence'] = result['confidence']
                prob['needs_manual_review'] = result['confidence'] < 0.85

                if result['source_url']:
                    prob['source_url'] = result['source_url']

                stats['solutions_found'] += 1
                combo_solutions_found += 1

                if result['confidence'] >= 0.85:
                    stats['solutions_high_confidence'] += 1
                    logging.info(f"  Problem {prob_num}: FOUND (confidence={result['confidence']:.2f}) ✓")
                else:
                    stats['needs_manual_review'] += 1
                    logging.info(f"  Problem {prob_num}: LOW CONFIDENCE ({result['confidence']:.2f}) - needs review")
            else:
                prob['solution_verified'] = False
                prob['needs_manual_review'] = True
                prob['solution_confidence'] = 0.0
                stats['needs_manual_review'] += 1
                logging.info(f"  Problem {prob_num}: NOT FOUND - marked for manual review")

            # Rate limiting
            time.sleep(0.5)

        # Mark combo as processed
        combo['source_url'] = source_url
        combo['source_name'] = source_name
        combo['solutions_imported'] = combo_solutions_found > 0

        logging.info(f"  Combo {combo_id}: {combo_solutions_found}/{len(problems)} solutions found")

    return stats


def save_olympiads(olympiads_db: list, output_file: str = 'olympiads.py', dry_run: bool = False):
    """Save updated olympiads database back to Python file."""
    if dry_run:
        logging.info(f"[DRY RUN] Would save {len(olympiads_db)} combos to {output_file}")
        return

    # Backup original
    backup_file = f'olympiads_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.py'
    if os.path.exists(output_file):
        import shutil
        shutil.copy2(output_file, backup_file)
        logging.info(f"Backup saved to {backup_file}")

    # Write updated file
    # Use repr() to write valid Python (True/False/None instead of JSON true/false/null)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# Baza olimpiad s vosstanovlennymi uslovijami\n')
        f.write('# Updated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + '\n')
        f.write('# Fields added: source_url, source_name, official_solution, solution_verified\n\n')
        f.write('OLYMPIADS_DB = ')
        # json.dumps produces JSON (true/false/null) — convert to Python literals
        json_str = json.dumps(olympiads_db, ensure_ascii=False, indent=4)
        # Replace JSON booleans/null with Python equivalents
        import re as _re
        py_str = _re.sub(r'\btrue\b', 'True', json_str)
        py_str = _re.sub(r'\bfalse\b', 'False', py_str)
        py_str = _re.sub(r'\bnull\b', 'None', py_str)
        f.write(py_str)
        f.write('\n')

    logging.info(f"Saved {len(olympiads_db)} combos to {output_file}")


def print_statistics(stats: dict):
    """Print final statistics."""
    print("\n" + "=" * 70)
    print("IMPORT STATISTICS")
    print("=" * 70)
    print(f"Total combos processed:      {stats['total_combos']}")
    print(f"Total problems:              {stats['total_problems']}")
    print(f"Solutions found:             {stats['solutions_found']}")
    if stats['total_problems'] > 0:
        pct = 100 * stats['solutions_found'] // max(stats['total_problems'], 1)
        print(f"  High confidence (≥0.85):  {stats['solutions_high_confidence']} ({pct}%)")
    print(f"Needs manual review:         {stats['needs_manual_review']}")
    print(f"Skipped (already verified):  {stats['skipped']}")
    print(f"Errors:                      {stats['errors']}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='Import official solutions for olympiad problems'
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Run without making changes')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of combos to process')
    parser.add_argument('--olympiad', type=str, default=None,
                        help='Filter by olympiad slug (e.g. vsosh, euler)')
    parser.add_argument('--force', action='store_true',
                        help='Re-process already verified solutions')
    parser.add_argument('--metadata-only', action='store_true',
                        help='Only add source_url/source_name, skip AI solution search')
    parser.add_argument('--output', type=str, default='olympiads.py',
                        help='Output file (default: olympiads.py)')
    args = parser.parse_args()

    log_file = setup_logging()
    logging.info("=" * 70)
    logging.info("IMPORT OFFICIAL SOLUTIONS - START")
    logging.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info(f"Dry run: {args.dry_run}")
    logging.info(f"Metadata only: {args.metadata_only}")
    logging.info(f"Log file: {log_file}")
    logging.info("=" * 70)

    # Load olympiads database
    from olympiads import OLYMPIADS_DB
    olympiads_db = list(OLYMPIADS_DB)  # make a mutable copy
    logging.info(f"Loaded {len(olympiads_db)} combos, "
                 f"{sum(len(c.get('problems',[])) for c in olympiads_db)} problems")

    # Phase 1.3: Add deterministic source metadata to all combos
    logging.info("\nPhase 1.3: Adding source metadata to all combos...")
    olympiads_db = add_source_metadata_to_combos(olympiads_db)

    if args.metadata_only:
        logging.info("--metadata-only flag set. Skipping AI solution search.")
        save_olympiads(olympiads_db, args.output, args.dry_run)
        logging.info("Done.")
        return

    # Initialize DeepSeek client
    from ai.deepseek_client import DeepSeekClient
    client = DeepSeekClient()
    logging.info("DeepSeek client initialized")

    # Phase 3: Batch process
    logging.info("\nPhase 3: Batch processing solutions...")
    stats = process_batch(olympiads_db, client, args)

    # Save results
    save_olympiads(olympiads_db, args.output, args.dry_run)

    # Print statistics
    print_statistics(stats)

    logging.info("IMPORT OFFICIAL SOLUTIONS - COMPLETE")


if __name__ == '__main__':
    main()
