#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 3: Overflow Re-Audit (2-pass DeepSeek)
=============================================
Re-audit 1366 overflow tasks from fill pipeline using DeepSeek API.
Overflow tasks already have a target_cell (suggested classification),
but were not placed because their target cell was already full (5/5).

Strategy:
  Pass 1 — For each task, present its target_cell classification to DeepSeek
           and ask: "Is this correct?" with confidence score.
  Pass 2 — For tasks with Pass-1 confidence < 0.70, re-audit from scratch
           (full classification without target_cell bias) to find correct theme.

Output:
  l4_l5_completion_work/stage3_overflow_audit_results.json
  l4_l5_completion_work/stage3_audit_report.txt
"""

import json
import os
import sys
import time
import hashlib
from datetime import datetime, timezone

# ── Windows console encoding fix ────────────────────────────────────────────
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# ── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVERFLOW_PATH = os.path.join(BASE_DIR, 'l4_l5_fill_output', 'overflow_tasks.json')
CURATED_PATH   = os.path.join(BASE_DIR, 'l4_l5_fill_output', 'curated_bank_L4_L5_filled.json')
WORK_DIR       = os.path.join(BASE_DIR, 'l4_l5_completion_work')
RESULT_PATH    = os.path.join(WORK_DIR, 'stage3_overflow_audit_results.json')
REPORT_PATH    = os.path.join(WORK_DIR, 'stage3_audit_report.txt')
CHECKPOINT_PATH = os.path.join(WORK_DIR, 'stage3_checkpoint.json')

os.makedirs(WORK_DIR, exist_ok=True)

# ── Import DeepSeek client ──────────────────────────────────────────────────
sys.path.insert(0, BASE_DIR)
from ai.deepseek_client import DeepSeekClient

# ── THEMES data (copied from _fill_l4_l5_pipeline.py) ──────────────────────
THEMES = {
    "T001": {"name": "Алгебра: теория групп",
             "subtopics": ["Группы: определения и примеры",
                           "Группы: подгруппы, смежные классы",
                           "Гомоморфизмы и факторгруппы"]},
    "T002": {"name": "Арифметика и теория чисел",
             "subtopics": ["Делимость и остатки",
                           "НОД, НОК, алгоритм Евклида",
                           "Сравнения по модулю (a \u2261 b mod n)"]},
    "T003": {"name": "Вероятность и комбинаторика",
             "subtopics": ["Геометрическая вероятность",
                           "Классическая вероятность",
                           "Условная вероятность и формула Байеса"]},
    "T004": {"name": "Графы: основные понятия",
             "subtopics": ["Графы: определения, изоморфизм",
                           "Маршруты, цепи, циклы, Эйлеровы графы",
                           "Связность и компоненты связности"]},
    "T005": {"name": "Дополнительные задачи и смешанные темы",
             "subtopics": ["Задачи на оптимизацию",
                           "Комбинированные задачи (алгебра + геометрия)",
                           "Прикладные задачи"]},
    "T006": {"name": "Комбинаторика и вероятность",
             "subtopics": ["Перестановки и факториалы",
                           "Правила сложения и умножения в комбинаторике",
                           "Размещения и сочетания"]},
    "T007": {"name": "Комбинаторика и теория игр",
             "subtopics": ["Выигрышные и проигрышные позиции",
                           "Игры с симметричной стратегией",
                           "Стратегия и анализ игр"]},
    "T008": {"name": "Логика и множества",
             "subtopics": ["Булевы функции и их минимизация",
                           "Логические операции и таблицы истинности",
                           "Множества и операции над ними"]},
    "T009": {"name": "Метод координат: декартовы координаты",
             "subtopics": ["Координаты на прямой и плоскости",
                           "Расстояние между точками, середина отрезка",
                           "Уравнения прямых и окружностей"]},
    "T010": {"name": "Метод координат: векторы",
             "subtopics": ["Векторы: сложение, умножение на число",
                           "Координаты вектора, связь с точками",
                           "Скалярное произведение векторов"]},
    "T011": {"name": "Неравенства: алгебраические неравенства",
             "subtopics": ["Доказательство неравенств",
                           "Квадратные неравенства",
                           "Неравенства с модулем"]},
    "T012": {"name": "Неравенства: метод интервалов и рациональные",
             "subtopics": ["Дробно-рациональные неравенства",
                           "Иррациональные неравенства",
                           "Метод интервалов для рациональных неравенств"]},
    "T013": {"name": "Неравенства: показательные и логарифмические",
             "subtopics": ["Логарифмические неравенства",
                           "Показательные неравенства",
                           "Системы показательных и логарифмических неравенств"]},
    "T014": {"name": "Неравенства: тригонометрические",
             "subtopics": ["Неравенства с обр. тригонометрическими функциями",
                           "Простейшие тригонометрические неравенства с sin, cos",
                           "Простейшие тригонометрические неравенства с tg, ctg"]},
    "T015": {"name": "Неравенства: числовые наборы",
             "subtopics": ["Неравенства о среднем арифметическом и среднем геометрическом",
                           "Неравенства Чебышева и Маркова",
                           "Цепочки неравенств, взвешенные средние"]},
    "T016": {"name": "Планиметрия: многоугольники",
             "subtopics": ["Многоугольники: виды, свойства",
                           "Параллелограммы и трапеции",
                           "Треугольники: виды, свойства"]},
    "T017": {"name": "Планиметрия: окружность",
             "subtopics": ["Вписанные углы и их свойства",
                           "Длина окружности, площадь круга и сектора",
                           "Касательные и секущие к окружности"]},
    "T018": {"name": "Планиметрия: площадь",
             "subtopics": ["Площади подобных фигур",
                           "Площадь круга и его частей",
                           "Формулы площади треугольника и четырёхугольника"]},
    "T019": {"name": "Планиметрия: треугольники",
             "subtopics": ["Подобие треугольников",
                           "Признаки равенства треугольников",
                           "Теорема Пифагора"]},
    "T020": {"name": "Последовательности и прогрессии",
             "subtopics": ["Арифметическая прогрессия",
                           "Геометрическая прогрессия",
                           "Суммы последовательностей"]},
    "T021": {"name": "Производная и её применение",
             "subtopics": ["Геометрический смысл производной",
                           "Исследование функций с помощью производной",
                           "Правила и формулы дифференцирования"]},
    "T022": {"name": "Проценты, отношения и пропорции",
             "subtopics": ["Задачи на проценты",
                           "Пропорции и отношения",
                           "Прямая и обратная пропорциональность"]},
    "T023": {"name": "Рациональные уравнения и неравенства",
             "subtopics": ["Дробно-рациональные уравнения",
                           "Метод замены переменной в рациональных уравнениях",
                           "Рациональные уравнения"]},
    "T024": {"name": "Решение задач: анализ и интерпретация",
             "subtopics": ["Оценка и прикидка",
                           "Проверка решения и поиск ошибок",
                           "Составление плана решения"]},
    "T025": {"name": "Решение уравнений: методы замены",
             "subtopics": ["Замена переменной (подстановка)",
                           "Использование симметрии",
                           "Сведение к системе уравнений"]},
    "T026": {"name": "Решение уравнений: разложение на множители",
             "subtopics": ["Вынесение общего множителя и группировка",
                           "Использование формул сокращённого умножения",
                           "Разложение квадратного трёхчлена"]},
    "T027": {"name": "Системы уравнений",
             "subtopics": ["Графический метод решения систем",
                           "Метод подстановки",
                           "Системы линейных уравнений"]},
    "T028": {"name": "Стереометрия: аксиомы и прямые",
             "subtopics": ["Аксиомы стереометрии",
                           "Взаимное расположение прямых в пространстве",
                           "Скрещивающиеся прямые"]},
    "T029": {"name": "Стереометрия: многогранники",
             "subtopics": ["Параллелепипеды, призмы",
                           "Пирамиды",
                           "Правильные многогранники"]},
    "T030": {"name": "Стереометрия: тела вращения",
             "subtopics": ["Конус, цилиндр",
                           "Сфера, шар",
                           "Тела вращения: сечения, комбинации"]},
    "T031": {"name": "Стереометрия: угол и расстояние",
             "subtopics": ["Расстояние от точки до плоскости",
                           "Угол между плоскостями (двугранный угол)",
                           "Угол между прямой и плоскостью"]},
    "T032": {"name": "Текстовые задачи: движение",
             "subtopics": ["Движение в противоположных направлениях",
                           "Движение по воде",
                           "Движение по кругу"]},
    "T033": {"name": "Текстовые задачи: производительность и смеси",
             "subtopics": ["Задачи на концентрацию, сплавы, смеси",
                           "Задачи на совместную работу",
                           "Задачи на производительность труда"]},
    "T034": {"name": "Теория вероятностей: дискретные распределения",
             "subtopics": ["Биномиальное распределение",
                           "Дискретные случайные величины",
                           "Математическое ожидание и дисперсия"]},
    "T035": {"name": "Тригонометрические уравнения",
             "subtopics": ["Однородные тригонометрические уравнения",
                           "Отбор корней в тригонометрических уравнениях",
                           "Простейшие тригонометрические уравнения"]},
    "T036": {"name": "Тригонометрия: преобразования",
             "subtopics": ["Основное тригонометрическое тождество",
                           "Формулы приведения",
                           "Формулы сложения и двойного угла"]},
    "T037": {"name": "Уравнения с модулем",
             "subtopics": ["Графическое решение уравнений с модулем",
                           "Метод интервалов для уравнений с модулем",
                           "Уравнения с модулем"]},
    "T038": {"name": "Уравнения: иррациональные",
             "subtopics": ["Иррациональные уравнения с одним корнем",
                           "Иррациональные уравнения с несколькими корнями",
                           "Метод замены в иррациональных уравнениях"]},
    "T039": {"name": "Уравнения: показательные и логарифмические",
             "subtopics": ["Логарифмические уравнения",
                           "Показательные уравнения",
                           "Системы показательных и логарифмических уравнений"]},
    "T040": {"name": "Уравнения: тригонометрические системы",
             "subtopics": ["Системы тригонометрических уравнений",
                           "Тригонометрические уравнения с параметром",
                           "Тригонометрические уравнения с отбором корней"]},
    "T041": {"name": "Числа, индукция, алгоритмы",
             "subtopics": ["Алгоритмы и вычисления",
                           "Комплексные числа",
                           "Метод математической индукции"]},
    "T042": {"name": "Функции и графики",
             "subtopics": ["Графики функций: преобразования и сдвиги",
                           "Область определения и область значений",
                           "Построение графиков сложных функций"]},
    "T043": {"name": "Стереометрия: объёмы и сечения",
             "subtopics": ["Объём многогранников",
                           "Объём тел вращения",
                           "Сечения многогранников"]}
}

GRADE_THEMES = {
    5:  ["T002", "T022", "T008", "T004", "T024", "T005"],
    6:  ["T006", "T007", "T032", "T033", "T016", "T018"],
    7:  ["T026", "T025", "T023", "T027", "T019", "T003"],
    8:  ["T042", "T011", "T012", "T037", "T009", "T017"],
    9:  ["T038", "T020", "T010", "T015", "T036", "T035"],
    10: ["T039", "T013", "T014", "T028", "T029", "T030"],
    11: ["T021", "T040", "T034", "T043", "T031", "T041", "T001"]
}

# ── Helpers ─────────────────────────────────────────────────────────────────

def build_task_identifier(task):
    """Build a deterministic short hash for the task statement."""
    stmt = task.get('statement', '')
    raw = stmt.strip().encode('utf-8') if stmt else str(task.get('olympiad', '')).encode()
    return hashlib.sha256(raw).hexdigest()[:12]


def parse_target_cell(target_cell):
    """
    Parse a target_cell string like "G8|L5|T009|S1"
    Returns dict with grade, level, theme_id, subtopic_idx or None on failure.
    """
    if not target_cell:
        return None
    try:
        parts = target_cell.split('|')
        if len(parts) != 4:
            return None
        grade_str, level_str, theme_id, subtopic_str = parts
        grade = int(grade_str.replace('G', ''))
        level = int(level_str.replace('L', ''))
        subtopic_idx = int(subtopic_str.replace('S', ''))
        return {
            "grade": grade,
            "level": level,
            "theme_id": theme_id,
            "subtopic_idx": subtopic_idx
        }
    except (ValueError, IndexError):
        return None


def grade_themes_str(grade):
    """Return a formatted string of possible themes for this grade."""
    tids = GRADE_THEMES.get(int(grade), [])
    lines = []
    for tid in tids:
        if tid in THEMES:
            t = THEMES[tid]
            subs = "; ".join(t["subtopics"])
            lines.append(f'  {tid}: "{t["name"]}" \u2014 \u043f\u043e\u0434\u0442\u0435\u043c\u044b: [{subs}]')
    return "\n".join(lines)


def build_pass1_prompt(task, target_info):
    """
    Build pass1 prompt: present the task with its target_cell classification
    and ask DeepSeek to verify if it's correct.
    """
    grade = task.get('grade', 0)
    level = task.get('level', 4)
    statement = task.get('statement', '')
    answer = task.get('answer', '')
    olympiad = task.get('olympiad', '')

    suggested_tid = target_info["theme_id"]
    suggested_si = target_info["subtopic_idx"]
    suggested_theme = THEMES.get(suggested_tid, {})
    suggested_name = suggested_theme.get("name", "?")
    suggested_subtopics = suggested_theme.get("subtopics", [])
    suggested_subtopic_name = suggested_subtopics[suggested_si] if suggested_si < len(suggested_subtopics) else "?"

    prompt = f"""Ты — эксперт по классификации олимпиадных задач по математике.

Задача имеет ПРЕДПОЛОЖИТЕЛЬНУЮ классификацию. Проверь, верна ли она.

Данные задачи:
- Олимпиада: {olympiad}
- Класс: {grade}
- Уровень: L{level}
- Условие: {statement}
- Ответ: {answer}

Предположительная классификация:
- Тема: {suggested_tid} («{suggested_name}»)
- Подтема: S{suggested_si} («{suggested_subtopic_name}»)

Доступные темы для {grade}-го класса:
{grade_themes_str(grade)}

Верни JSON-объект с полями:
- "is_correct": true/false — верна ли предположительная классификация
- "theme_id": если is_correct=true, то {suggested_tid}; если false — укажи правильную тему
- "subtopic_idx": если is_correct=true, то {suggested_si}; если false — укажи правильную подтему (0, 1 или 2)
- "confidence": число от 0.0 до 1.0, насколько ты уверен в своём ответе
- "reasoning": краткое обоснование (2-3 предложения на русском)"""
    return prompt


def build_pass2_prompt(task, pass1_result):
    """
    Build pass2 prompt for tasks with low confidence.
    Do a full classification from scratch without target_cell bias.
    """
    grade = task.get('grade', 0)
    level = task.get('level', 4)
    statement = task.get('statement', '')
    answer = task.get('answer', '')
    olympiad = task.get('olympiad', '')

    possible_themes = grade_themes_str(grade)

    prompt = f"""Ты — эксперт по классификации олимпиадных задач. Прошлая попытка проверки дала низкую уверенность.

Теперь выполни ПОЛНУЮ классификацию задачи с нуля, без учёта предыдущих предположений.

Задача для {grade}-го класса (уровень L{level}):
- Олимпиада: {olympiad}
- Условие: {statement}
- Ответ: {answer}

Прошлый результат: тема {pass1_result.get("theme_id", "?")}, подтема {pass1_result.get("subtopic_idx", "?")}, уверенность {pass1_result.get("confidence", 0)}.

Пожалуйста, проанализируй внимательнее. Доступные темы:
{possible_themes}

Обрати внимание на ключевые математические концепции в условии. Определи, к какой теме и подтеме относится задача.

Верни JSON-объект с полями:
- "theme_id": идентификатор темы (например, "T009")
- "subtopic_idx": индекс подтемы (0, 1 или 2)
- "confidence": число от 0.0 до 1.0, насколько ты уверен
- "reasoning": подробное обоснование на русском (3-5 предложений)
- "keywords": список ключевых слов из условия, которые указывают на эту тему"""
    return prompt


def parse_json_response(response_text):
    """Try to parse JSON from DeepSeek response. Handles markdown fences."""
    text = response_text.strip()
    # Remove markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        start = 0
        end = len(lines)
        for i, line in enumerate(lines):
            if line.strip().startswith("```"):
                start = i + 1
                break
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip().startswith("```"):
                end = i
                break
        text = "\n".join(lines[start:end]).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ── Core audit logic ────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("STAGE 3: OVERFLOW RE-AUDIT (2-pass DeepSeek)")
    print("=" * 70)

    # ── Load overflow tasks ─────────────────────────────────────────────────
    print(f"\n[LOAD] Loading overflow tasks from: {OVERFLOW_PATH}")
    with open(OVERFLOW_PATH, 'r', encoding='utf-8') as f:
        overflow_tasks = json.load(f)
    total = len(overflow_tasks)
    print(f"[LOAD] Loaded {total} overflow tasks")

    # ── Load curated bank (for existing task statements, to avoid re-adds) ──
    print(f"\n[LOAD] Loading curated bank from: {CURATED_PATH}")
    with open(CURATED_PATH, 'r', encoding='utf-8') as f:
        curated_bank = json.load(f)
    print(f"[LOAD] Loaded {len(curated_bank)} existing tasks")

    # Build set of existing normalized statements for exact dedup later
    existing_statements = set()
    for t in curated_bank:
        stmt = t.get('statement', '').strip()
        if stmt:
            norm = ' '.join(stmt.lower().split())
            existing_statements.add(norm)

    # ── Initialize DeepSeek client ──────────────────────────────────────────
    print("\n[DS] Initializing DeepSeek client...")
    client = DeepSeekClient()
    print("[DS] Client ready")

    # ── Load or create checkpoint ───────────────────────────────────────────
    results = []
    if os.path.exists(CHECKPOINT_PATH):
        print(f"\n[CP] Loading checkpoint from: {CHECKPOINT_PATH}")
        with open(CHECKPOINT_PATH, 'r', encoding='utf-8') as f:
            checkpoint = json.load(f)
            results = checkpoint.get('results', [])
        print(f"[CP] Checkpoint loaded: {len(results)} tasks already processed")
    else:
        print("\n[CP] No checkpoint found, starting fresh")

    # Build set of already processed task IDs
    processed_ids = set(r.get('task_id') for r in results)

    # Filter tasks that have unparseable target_cell
    tasks_with_parsed = []
    skipped_no_target = 0
    for task in overflow_tasks:
        tc = task.get('target_cell', '')
        parsed = parse_target_cell(tc)
        if parsed is None:
            skipped_no_target += 1
            continue
        tasks_with_parsed.append((task, parsed))

    if skipped_no_target > 0:
        print(f"\n[WARN] Skipped {skipped_no_target} tasks without parseable target_cell")

    # ── PASS 1: Verification of target_cell classifications ─────────────────
    print(f"\n{'=' * 70}")
    print(f"PASS 1: Verification of {len(tasks_with_parsed)} overflow tasks")
    print(f"{'=' * 70}")
    print(f"  Already processed: {len(processed_ids)} tasks")
    print(f"  Remaining: {len(tasks_with_parsed) - len(processed_ids)} tasks\n")

    pass1_errors = 0
    for idx, (task, target_info) in enumerate(tasks_with_parsed):
        task_id = build_task_identifier(task)

        if task_id in processed_ids:
            continue

        grade = task.get('grade', 0)
        level = task.get('level', 4)
        statement_preview = task.get('statement', '')[:80].replace('\n', ' ')

        print(f"  [{idx+1}/{len(tasks_with_parsed)}] Task {task_id} | G{grade} L{level} | {statement_preview}...")

        prompt = build_pass1_prompt(task, target_info)
        system_prompt = (
            "Ты — классификатор олимпиадных задач по математике. "
            "Отвечай ТОЛЬКО в формате JSON с полями is_correct, theme_id, subtopic_idx, confidence, reasoning."
        )

        try:
            response = client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.2,
                response_format={"type": "json_object"}
            )

            parsed = parse_json_response(response)
            if parsed is None:
                print(f"    [WARN] Failed to parse JSON response. Raw: {response[:200]}")
                parsed = {
                    "is_correct": False,
                    "theme_id": None,
                    "subtopic_idx": None,
                    "confidence": 0.0,
                    "reasoning": "JSON parse error"
                }
                pass1_errors += 1

            result = {
                "task_id": task_id,
                "task": task,
                "target_cell": task.get('target_cell', ''),
                "target_info": target_info,
                "pass1": {
                    "is_correct": parsed.get("is_correct", False),
                    "theme_id": parsed.get("theme_id"),
                    "subtopic_idx": parsed.get("subtopic_idx"),
                    "confidence": parsed.get("confidence", 0.0),
                    "reasoning": parsed.get("reasoning", ""),
                    "keywords": parsed.get("keywords", [])
                },
                "pass2": None
            }
            results.append(result)

            conf = result["pass1"]["confidence"]
            is_correct = result["pass1"]["is_correct"]
            if conf >= 0.7:
                status = "VERIFIED" if is_correct else "REJECTED"
                print(f"    -> {parsed.get('theme_id')}/S{parsed.get('subtopic_idx')} (conf={conf:.2f}) [{status}]")
            else:
                print(f"    -> {parsed.get('theme_id')}/S{parsed.get('subtopic_idx')} (conf={conf:.2f}) [LOW - needs pass 2]")

            # Save checkpoint every 20 tasks
            if (idx + 1) % 20 == 0:
                print(f"  [CP] Saving checkpoint ({len(results)} results)...")
                with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
                    json.dump({"results": results}, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"    [ERROR] DeepSeek call failed: {e}")
            result = {
                "task_id": task_id,
                "task": task,
                "target_cell": task.get('target_cell', ''),
                "target_info": target_info,
                "pass1": {
                    "is_correct": False,
                    "theme_id": None,
                    "subtopic_idx": None,
                    "confidence": 0.0,
                    "reasoning": f"API error: {str(e)}"
                },
                "pass2": None
            }
            results.append(result)
            pass1_errors += 1

        # Rate limit friendly delay
        time.sleep(0.5)

    # Save checkpoint after Pass 1
    print(f"\n[CP] Saving checkpoint after Pass 1 ({len(results)} results)...")
    with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
        json.dump({"results": results}, f, ensure_ascii=False, indent=2)

    # ── PASS 2: Re-audit low-confidence tasks ───────────────────────────────
    low_conf_tasks = [r for r in results
                      if r["pass1"]["confidence"] is not None
                      and r["pass1"]["confidence"] < 0.70]

    print(f"\n{'=' * 70}")
    print(f"PASS 2: Re-auditing {len(low_conf_tasks)} low-confidence tasks")
    print(f"{'=' * 70}")

    pass2_errors = 0
    for idx, result in enumerate(low_conf_tasks):
        task = result["task"]
        task_id = result["task_id"]
        grade = task.get('grade', 0)
        level = task.get('level', 4)
        statement_preview = task.get('statement', '')[:80].replace('\n', ' ')

        print(f"  [{idx+1}/{len(low_conf_tasks)}] Task {task_id} | G{grade} L{level} | {statement_preview}...")

        prompt = build_pass2_prompt(task, result["pass1"])
        system_prompt = (
            "Ты — эксперт-классификатор олимпиадных задач. "
            "Проанализируй задачу внимательно. "
            "Отвечай ТОЛЬКО в формате JSON с полями theme_id, subtopic_idx, confidence, reasoning, keywords."
        )

        try:
            response = client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            parsed = parse_json_response(response)
            if parsed is None:
                print(f"    [WARN] Failed to parse JSON response in Pass 2")
                parsed = {
                    "theme_id": result["pass1"]["theme_id"],
                    "subtopic_idx": result["pass1"]["subtopic_idx"],
                    "confidence": result["pass1"]["confidence"],
                    "reasoning": "Pass 2 JSON parse error, kept Pass 1 result",
                    "keywords": []
                }
                pass2_errors += 1

            result["pass2"] = {
                "theme_id": parsed.get("theme_id"),
                "subtopic_idx": parsed.get("subtopic_idx"),
                "confidence": parsed.get("confidence", 0.0),
                "reasoning": parsed.get("reasoning", ""),
                "keywords": parsed.get("keywords", [])
            }

            conf = result["pass2"]["confidence"]
            print(f"    -> {parsed.get('theme_id')}/S{parsed.get('subtopic_idx')} (conf={conf:.2f})")

        except Exception as e:
            print(f"    [ERROR] Pass 2 DeepSeek call failed: {e}")
            result["pass2"] = {
                "theme_id": result["pass1"]["theme_id"],
                "subtopic_idx": result["pass1"]["subtopic_idx"],
                "confidence": result["pass1"]["confidence"],
                "reasoning": f"Pass 2 API error: {str(e)}",
                "keywords": []
            }
            pass2_errors += 1

        # Save checkpoint every 10 tasks in Pass 2
        if (idx + 1) % 10 == 0:
            print(f"  [CP] Saving checkpoint ({len(results)} total results)...")
            with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
                json.dump({"results": results}, f, ensure_ascii=False, indent=2)

        time.sleep(0.5)

    # ── Final save ──────────────────────────────────────────────────────────
    print(f"\n[SAVE] Saving final results ({len(results)} tasks)...")
    with open(RESULT_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"[SAVE] Results saved to: {RESULT_PATH}")

    # Clear checkpoint since we're done
    if os.path.exists(CHECKPOINT_PATH):
        os.remove(CHECKPOINT_PATH)
        print(f"[CP] Checkpoint cleared")

    # ── Compute summary statistics ──────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("SUMMARY REPORT")
    print(f"{'=' * 70}")

    # Determine final classification quality for each task
    def get_final_confidence(r):
        if r["pass2"] and r["pass2"]["confidence"] is not None:
            return r["pass2"]["confidence"]
        return r["pass1"]["confidence"] or 0.0

    def get_final_theme(r):
        if r["pass2"] and r["pass2"]["theme_id"]:
            return r["pass2"]["theme_id"]
        return r["pass1"]["theme_id"]

    def get_final_subtopic(r):
        if r["pass2"] and r["pass2"]["subtopic_idx"] is not None:
            return r["pass2"]["subtopic_idx"]
        return r["pass1"]["subtopic_idx"]

    def get_final_is_correct(r):
        # For pass2 results, check if theme matches target_cell
        if r["pass2"] and r["pass2"]["theme_id"]:
            final_tid = r["pass2"]["theme_id"]
            final_si = r["pass2"]["subtopic_idx"]
            # Compare with target_info
            info = r.get("target_info")
            if info:
                return final_tid == info["theme_id"] and final_si == info["subtopic_idx"]
            return False
        # For pass1, use is_correct field
        return r["pass1"].get("is_correct", False)

    # Classification stats
    pass1_high = sum(1 for r in results
                     if r["pass1"]["confidence"] is not None
                     and r["pass1"]["confidence"] >= 0.70)
    pass1_low = len(results) - pass1_high

    pass2_final_high = sum(1 for r in results
                           if r["pass2"] is not None
                           and r["pass2"]["confidence"] is not None
                           and r["pass2"]["confidence"] >= 0.70)

    pass2_final_low = sum(1 for r in results
                          if r["pass2"] is not None
                          and r["pass2"]["confidence"] is not None
                          and r["pass2"]["confidence"] < 0.70)

    verified = []
    reclassified = []
    unconfident = []
    for r in results:
        conf = get_final_confidence(r)
        tid = get_final_theme(r)
        if conf < 0.7 or not tid:
            unconfident.append(r)
        elif get_final_is_correct(r):
            verified.append(r)
        else:
            reclassified.append(r)

    # Grade-level breakdown
    grades = {}
    for r in results:
        g = r["task"].get("grade", 0)
        if g not in grades:
            grades[g] = {"total": 0, "confident": 0}
        grades[g]["total"] += 1
        if get_final_confidence(r) >= 0.7:
            grades[g]["confident"] += 1

    # Theme distribution
    theme_counts = {}
    for r in results:
        tid = get_final_theme(r)
        if tid:
            theme_counts[tid] = theme_counts.get(tid, 0) + 1

    # Level distribution
    l4_count = sum(1 for r in results if r["task"].get("level") == 4)
    l5_count = sum(1 for r in results if r["task"].get("level") == 5)

    # Target cell distribution (which cells are these overflow tasks for?)
    cell_counts = {}
    for r in results:
        tc = r.get("target_cell", "")
        if tc:
            cell_counts[tc] = cell_counts.get(tc, 0) + 1

    print(f"\nTotal overflow tasks processed: {len(results)}")
    print(f"Errors (Pass 1): {pass1_errors}")
    print(f"Errors (Pass 2): {pass2_errors}")
    print()
    print(f"Pass 1 results:")
    print(f"  High confidence (>=0.70): {pass1_high}")
    print(f"  Low confidence (<0.70):  {pass1_low}")
    print(f"Pass 2 re-audited:          {len(low_conf_tasks)}")
    print(f"  After pass 2 high conf:   {pass2_final_high}")
    print(f"  After pass 2 still low:   {pass2_final_low}")
    print()
    print(f"Final classification quality:")
    print(f"  Verified (original target correct): {len(verified)}")
    print(f"  Reclassified (original was wrong):  {len(reclassified)}")
    print(f"  Unconfident (<0.70):                {len(unconfident)}")
    print()
    print(f"Level breakdown:")
    print(f"  L4: {l4_count}")
    print(f"  L5: {l5_count}")
    print()
    print(f"Grade breakdown:")
    for g in sorted(grades.keys()):
        info = grades[g]
        print(f"  Grade {g}: {info['total']} total, {info['confident']} confident")
    print()
    print(f"Top themes assigned:")
    for tid, count in sorted(theme_counts.items(), key=lambda x: -x[1])[:15]:
        tname = THEMES.get(tid, {}).get("name", "?")
        print(f"  {tid} ({tname}): {count} tasks")
    print()
    print(f"Top 10 target cells (most overflow tasks):")
    for tc, count in sorted(cell_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {tc}: {count} tasks")

    # ── Write report ────────────────────────────────────────────────────────
    lines = [
        "=" * 70,
        "STAGE 3: OVERFLOW RE-AUDIT REPORT",
        "=" * 70,
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Total overflow tasks processed: {len(results)}",
        f"Pass 1 high confidence (>=0.70): {pass1_high}",
        f"Pass 1 low confidence (<0.70):  {pass1_low}",
        f"Pass 2 re-audited:              {len(low_conf_tasks)}",
        f"Pass 2 errors:                  {pass2_errors}",
        "",
        f"Final verified (target correct):    {len(verified)}",
        f"Final reclassified (target wrong):  {len(reclassified)}",
        f"Final unconfident (<0.70):          {len(unconfident)}",
        "",
        f"L4 tasks: {l4_count}",
        f"L5 tasks: {l5_count}",
        "",
        "Grade breakdown:",
    ]
    for g in sorted(grades.keys()):
        info = grades[g]
        lines.append(f"  Grade {g}: {info['total']} total, {info['confident']} confident")

    lines.extend(["", "Top 15 themes assigned:"])
    for tid, count in sorted(theme_counts.items(), key=lambda x: -x[1])[:15]:
        tname = THEMES.get(tid, {}).get("name", "?")
        lines.append(f"  {tid} ({tname}): {count} tasks")

    lines.extend(["", "Top 10 target cells (most overflow tasks):"])
    for tc, count in sorted(cell_counts.items(), key=lambda x: -x[1])[:10]:
        lines.append(f"  {tc}: {count} tasks")

    lines.extend(["", "Tasks still unconfident (final conf < 0.70):"])
    for r in unconfident:
        task = r["task"]
        tid = get_final_theme(r)
        si = get_final_subtopic(r)
        conf = get_final_confidence(r)
        tc = r.get("target_cell", "?")
        stmt = task.get("statement", "")[:100].replace("\n", " ")
        lines.append(f"  [{r['task_id']}] G{task.get('grade')} L{task.get('level')} "
                     f"target={tc} -> {tid}/S{si} (conf={conf:.2f}) | {stmt}...")
        if r["pass2"]:
            lines.append(f"      Pass 2 reasoning: {r['pass2'].get('reasoning', 'N/A')[:200]}")

    lines.extend(["", "Reclassified tasks (original target was wrong):"])
    for r in reclassified[:30]:
        task = r["task"]
        tid = get_final_theme(r)
        si = get_final_subtopic(r)
        conf = get_final_confidence(r)
        tc = r.get("target_cell", "?")
        stmt = task.get("statement", "")[:80].replace("\n", " ")
        lines.append(f"  [{r['task_id']}] G{task.get('grade')} L{task.get('level')} "
                     f"target={tc} -> {tid}/S{si} (conf={conf:.2f}) | {stmt}...")

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"\n[REPORT] Written to: {REPORT_PATH}")

    print(f"\n{'=' * 70}")
    print(f"STAGE 3 COMPLETE. Proceed to Stage 4 (duplicate re-check).")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
