#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Gap Filler - avtomaticheskoe zapolnenie dyr v baze olimpiad
"""

import sys
import json
import requests
import time
import re
sys.path.insert(0, ".")
from olympiads import OLYMPIADS_DB

# Idealnaya matrica olimpiad (istoricheski korrektnaya)
IDEAL_MATRIX = {
    'vsosh': {
        'years': range(2010, 2025),
        'rounds': ['school', 'municipal'],
        'grades': [5, 6, 7, 8]
    },
    'lomonosov': {
        'years': range(2020, 2025),
        'rounds': ['otbor', 'final'],
        'grades': [5, 6, 7, 8]
    },
    'vysshaya_proba': {
        'years': range(2020, 2025),
        'rounds': ['otbor', 'final'],
        'grades': [7, 8]  # TOLKO 7-8 klassy!
    },
    'phystech': {
        'years': range(2021, 2025),
        'rounds': ['otbor'],
        'grades': [5, 6, 7, 8]
    },
    'formula_unity': {
        'years': range(2021, 2025),
        'rounds': ['final'],
        'grades': [5, 6, 7, 8]
    }
}

TASKS_PER_VARIANT = 5  # Idealno po 5 zadach

# DeepSeek API nastrojki
DEEPSEEK_API_KEY = "sk-54c1fd3679ad45dd857871d788ecf262"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-chat"

# Nazvaniya olimpiad
OLYMPIAD_TITLES = {
    'vsosh': 'Vserossijskaya olimpiada shkolnikov',
    'lomonosov': 'Olimpiada Lomonosova',
    'vysshaya_proba': 'Olimpiada Vysshaya proba',
    'phystech': 'Olimpiada Fizteh',
    'formula_unity': 'Olimpiada Formula Edinstva'
}

ROUND_TITLES = {
    'school': 'Shkolnyj etap',
    'municipal': 'Municipalnyj etap',
    'otbor': 'Otborochnyj etap',
    'final': 'Zaklyuchitelnyj etap'
}

# Temy dlya raznoobraznogo raspredeleniya
SUBJECTS = ['number_theory', 'algebra', 'geometry', 'combinatorics', 'logic']


def audit_gaps():
    """Audit dyr v baze"""
    print("="*70)
    print("STEP 1: AUDIT GAPS IN DATABASE")
    print("="*70)
    
    # Podschityvaem tekushchee sostoyanie
    current_state = {}
    for combo in OLYMPIADS_DB:
        olympiad = combo.get('olympiad')
        year = combo.get('year')
        grade = combo.get('grade')
        round_key = combo.get('round')
        
        key = (olympiad, year, round_key, grade)
        if key not in current_state:
            current_state[key] = 0
        current_state[key] += 1
    
    # Nahodim dyry
    total_gaps = 0
    gaps_list = []
    
    for olympiad, config in IDEAL_MATRIX.items():
        for year in config['years']:
            for round_key in config['rounds']:
                for grade in config['grades']:
                    key = (olympiad, year, round_key, grade)
                    current_count = current_state.get(key, 0)
                    needed = TASKS_PER_VARIANT - current_count
                    
                    if needed > 0:
                        gaps_list.append({
                            'olympiad': olympiad,
                            'year': year,
                            'round': round_key,
                            'grade': grade,
                            'needed': needed
                        })
                        total_gaps += needed
    
    # Vyvodim otchet
    print(f"\nTOTAL MISSING: {total_gaps} tasks")
    print(f"Number of gaps (combinations): {len(gaps_list)}")
    print("="*70)
    
    return gaps_list, total_gaps


def fix_json_string(content):
    """Popytka ispravit nevaliidnyj JSON"""
    # Ubiraem markdown
    if content.startswith('```'):
        lines = content.split('\n')
        content = '\n'.join(lines[1:-1]) if len(lines) > 2 else content
        content = content.replace('```json', '').replace('```', '').strip()
    
    # Probujuem najti JSON massiv
    match = re.search(r'\[.*\]', content, re.DOTALL)
    if match:
        content = match.group(0)
    
    return content


def generate_tasks_via_deepseek(olympiad, year, round_key, grade, count, start_id, max_retries=3):
    """
    Generaciya zadach cherez DeepSeek API s retry i luchshej obrabotkoj oshibok
    """
    olympiad_title = OLYMPIAD_TITLES.get(olympiad, olympiad)
    round_title = ROUND_TITLES.get(round_key, round_key)
    
    prompt = f"""You are an expert in mathematical olympiads. Generate {count} unique olympiad problems for:

Olympiad: {olympiad_title}
Year: {year}
Round: {round_title}
Grade: {grade}

REQUIREMENTS:
1. Problems must match grade {grade} level
2. Variety of topics: number theory, algebra, geometry, combinatorics, logic
3. Each problem must have a complete solution and answer
4. Difficulty must match the olympiad round

CRITICAL: Return ONLY a valid JSON array. Each object MUST have ALL these fields:
- id (integer, starting from {start_id})
- olympiad (string: "{olympiad}")
- olympiad_title (string: "{olympiad_title}")
- year (integer: {year})
- round (string: "{round_key}")
- grade (integer: {grade})
- subject (string: one of number_theory, algebra, geometry, combinatorics, logic)
- difficulty (integer: {3 if grade <= 6 else 4})
- title (string: short title 2-5 words)
- text (string: complete problem statement, escape quotes properly)
- answer (string: brief answer)
- solution (string: detailed solution, escape quotes properly)

IMPORTANT: Escape all quotes in text and solution fields! Use simple language without special characters.

Example format:
[
  {{
    "id": {start_id},
    "olympiad": "{olympiad}",
    "olympiad_title": "{olympiad_title}",
    "year": {year},
    "round": "{round_key}",
    "grade": {grade},
    "subject": "number_theory",
    "difficulty": {3 if grade <= 6 else 4},
    "title": "Problem Title",
    "text": "Problem statement here",
    "answer": "Answer here",
    "solution": "Solution here"
  }}
]

Return ONLY the JSON array, no markdown, no extra text!"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 6000
    }
    
    for attempt in range(max_retries):
        try:
            print(f"  -> Request to DeepSeek (attempt {attempt+1}/{max_retries})...")
            response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content'].strip()
            
            # Ispravlyaem JSON
            content = fix_json_string(content)
            
            # Parsim JSON
            tasks = json.loads(content)
            
            if not isinstance(tasks, list):
                raise ValueError("Response is not an array")
            
            # Proveryaem i dopolnyaem polya
            required_fields = ['id', 'olympiad', 'olympiad_title', 'year', 'round', 'grade', 
                              'subject', 'difficulty', 'title', 'text', 'answer', 'solution']
            
            for idx, task in enumerate(tasks):
                missing = [f for f in required_fields if f not in task]
                if missing:
                    print(f"  WARNING: Missing fields in task {idx}: {missing}, filling...")
                    if 'id' not in task:
                        task['id'] = start_id + idx
                    if 'olympiad' not in task:
                        task['olympiad'] = olympiad
                    if 'olympiad_title' not in task:
                        task['olympiad_title'] = olympiad_title
                    if 'year' not in task:
                        task['year'] = year
                    if 'round' not in task:
                        task['round'] = round_key
                    if 'grade' not in task:
                        task['grade'] = grade
                    if 'subject' not in task:
                        task['subject'] = SUBJECTS[idx % len(SUBJECTS)]
                    if 'difficulty' not in task:
                        task['difficulty'] = 3 if grade <= 6 else 4
                    if 'title' not in task:
                        task['title'] = f"Problem {idx + 1}"
                    if 'text' not in task:
                        task['text'] = "Problem statement"
                    if 'answer' not in task:
                        task['answer'] = "Answer"
                    if 'solution' not in task:
                        task['solution'] = "Solution"
            
            print(f"  OK Received {len(tasks)} tasks")
            return tasks
            
        except requests.exceptions.RequestException as e:
            print(f"  ERROR Network error: {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"  Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                print(f"  FAILED after {max_retries} attempts")
                return []
                
        except json.JSONDecodeError as e:
            print(f"  ERROR JSON parse error: {e}")
            if attempt < max_retries - 1:
                print(f"  Retrying with different temperature...")
                payload['temperature'] = 0.5  # Snizhaem temperaturu
                time.sleep(3)
            else:
                print(f"  FAILED after {max_retries} attempts")
                return []
                
        except Exception as e:
            print(f"  ERROR Unexpected error: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                return []
    
    return []


def save_incremental(generated_tasks, filename='olympiads_full_patch.py'):
    """
    Inkrementalnoe sohranenie (posle kazhdoj uspeshnoj generacii)
    """
    content = "# -*- coding: utf-8 -*-\n"
    content += "# Full patch - generated tasks to fill gaps\n\n"
    content += "OLYMPIADS_FULL_PATCH = "
    content += json.dumps(generated_tasks, ensure_ascii=False, indent=4)
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)


def fill_all_gaps():
    """
    FULL GENERATION: filling ALL gaps with incremental saves
    """
    print("\n" + "="*70)
    print("STEP 2: FULL TASK GENERATION")
    print("="*70)
    
    gaps_list, total_gaps = audit_gaps()
    
    if not gaps_list:
        print("\nNo gaps found!")
        return []
    
    print(f"\nFilling ALL {len(gaps_list)} gaps ({total_gaps} tasks)")
    print("-"*70)
    
    generated_tasks = []
    next_id = 90001
    successful_count = 0
    failed_count = 0
    
    for i, gap in enumerate(gaps_list, 1):
        olympiad = gap['olympiad']
        year = gap['year']
        round_key = gap['round']
        grade = gap['grade']
        needed = gap['needed']
        
        print(f"\n[{i}/{len(gaps_list)}] {olympiad.upper()} {year}, {round_key}, grade {grade}")
        print(f"    Tasks needed: {needed}")
        
        # Generiruem zadachi
        tasks = generate_tasks_via_deepseek(olympiad, year, round_key, grade, needed, next_id)
        
        if not tasks:
            print("    SKIPPED - generation failed")
            failed_count += 1
            continue
        
        # Dobavlyaem v obshchij spisok
        generated_tasks.extend(tasks)
        next_id += len(tasks)
        successful_count += 1
        
        print(f"    OK Added {len(tasks)} tasks (ID: {tasks[0]['id']}-{tasks[-1]['id']})")
        
        # Sohranenie posle kazhdyh 10 uspeshnyh generacij
        if successful_count % 10 == 0:
            save_incremental(generated_tasks)
            print(f"\n*** CHECKPOINT: Saved {len(generated_tasks)} tasks to file ***\n")
        
        # Progress report
        if len(generated_tasks) % 50 == 0:
            print(f"\n*** PROGRESS: {len(generated_tasks)} tasks generated, {successful_count} successful, {failed_count} failed ***\n")
        
        # Pauza mezhdu zaprosami
        time.sleep(2)
    
    print("\n" + "="*70)
    print(f"GENERATION COMPLETE:")
    print(f"  Total generated: {len(generated_tasks)} tasks")
    print(f"  Successful: {successful_count} combinations")
    print(f"  Failed: {failed_count} combinations")
    print("="*70)
    
    return generated_tasks


def save_full_patch(generated_tasks):
    """
    Final save
    """
    print("\n" + "="*70)
    print("STEP 3: FINAL SAVE")
    print("="*70)
    
    save_incremental(generated_tasks)
    
    print(f"OK Results saved to olympiads_full_patch.py")
    print(f"  Total tasks: {len(generated_tasks)}")
    
    # Statistika
    stats = {}
    for task in generated_tasks:
        olymp = task.get('olympiad', 'unknown')
        stats[olymp] = stats.get(olymp, 0) + 1
    
    print("\nStatistics by olympiad:")
    for olymp, count in sorted(stats.items()):
        print(f"  {olymp}: {count} tasks")
    
    return True


def main():
    """Glavnaya funkciya"""
    print("\n>>> SMART GAP FILLER - FULL GENERATION WITH RETRY")
    print("="*70)
    
    # Generiruem zadachi
    generated_tasks = fill_all_gaps()
    
    if not generated_tasks:
        print("\nWARNING No tasks generated")
        return
    
    # Final save
    save_full_patch(generated_tasks)
    
    # Primer pervoj zadachi
    print("\n" + "="*70)
    print("EXAMPLE OF FIRST TASK (format check):")
    print("="*70)
    
    if generated_tasks:
        first_task = generated_tasks[0]
        for key, value in first_task.items():
            if isinstance(value, str) and len(value) > 100:
                print(f"  {key}: {value[:100]}...")
            else:
                print(f"  {key}: {value}")
    
    print("\n" + "="*70)
    print("OK FULL GENERATION COMPLETE!")
    print("="*70)


if __name__ == "__main__":
    main()
