#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Stage 4: Duplicate Re-check (rejected_tasks.json)
==================================================
Re-audits 411 rejected tasks to determine if any can be reinstated.

Rejection reasons:
  - stage1b_exact_among_candidates (66): exact normalized text match among candidates -> keep rejected
  - stage2_high_similarity_vs_existing (1): n-gram Jaccard >= 0.60 vs existing DB   -> DeepSeek check
  - stage2b_high_similarity_among_candidates (344): n-gram similarity among candidates -> DeepSeek check

Strategy:
  1. For stage1b: auto-keep rejected (exact text dupes, no salvage possible).
  2. For stage2/2b: pass each task through DeepSeek to determine if it's a genuinely
     different problem that could fill a gap cell. Classify (theme, subtopic, level)
     and check if target cell needs tasks.

Output: stage4_recheck_results.json, stage4_recheck_report.txt
"""

import os
import sys
import json
import csv
import hashlib
from collections import Counter, defaultdict

# ── cp1251-safe stdout ──────────────────────────────────────────────────
import codecs
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)

# ── Paths ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(BASE_DIR)

REJECTED_PATH = os.path.join(BASE_DIR, "l4_l5_fill_output", "rejected_tasks.json")
GAPS_CSV = os.path.join(BASE_DIR, "l4_l5_completion_work", "gaps_before_full.csv")
OUTPUT_JSON = os.path.join(BASE_DIR, "l4_l5_completion_work", "stage4_recheck_results.json")
OUTPUT_REPORT = os.path.join(BASE_DIR, "l4_l5_completion_work", "stage4_recheck_report.txt")
OUTPUT_REINSTATED = os.path.join(BASE_DIR, "l4_l5_completion_work", "stage4_reinstated_candidates.json")

# ── THEMES & GRADE_THEMES (from _fill_l4_l5_pipeline.py) ────────────────
THEMES = {
    "T001": {"name": "Числа и выражения", "subtopics": [
        "Натуральные и целые числа", "Рациональные числа и дроби", "Делимость и признаки делимости"]},
    "T002": {"name": "Текстовые задачи", "subtopics": [
        "Задачи на движение", "Задачи на работу и производительность", "Задачи на проценты и доли"]},
    "T003": {"name": "Уравнения и неравенства", "subtopics": [
        "Линейные уравнения и неравенства", "Квадратные уравнения и неравенства", "Системы уравнений и неравенств"]},
    "T004": {"name": "Функции и графики", "subtopics": [
        "Линейная функция и её график", "Квадратичная функция и её график", "Свойства функций: монотонность, чётность, периодичность"]},
    "T005": {"name": "Комбинаторика и вероятность", "subtopics": [
        "Комбинаторные принципы: сложение, умножение", "Перестановки, размещения, сочетания", "Вероятность случайного события"]},
    "T006": {"name": "Прогрессии и последовательности", "subtopics": [
        "Арифметическая прогрессия", "Геометрическая прогрессия", "Свойства последовательностей"]},
    "T007": {"name": "Планиметрия: треугольники", "subtopics": [
        "Свойства и признаки равенства треугольников", "Прямоугольный треугольник: теорема Пифагора", "Площадь треугольника"]},
    "T008": {"name": "Планиметрия: четырёхугольники", "subtopics": [
        "Параллелограммы: свойства и признаки", "Трапеция и её свойства", "Площади четырёхугольников"]},
    "T009": {"name": "Планиметрия: окружности", "subtopics": [
        "Касательные и хорды", "Вписанные и центральные углы", "Вписанные и описанные окружности"]},
    "T010": {"name": "Планиметрия: площадь и векторы", "subtopics": [
        "Площади сложных фигур", "Координаты и векторы на плоскости", "Метод координат в планиметрии"]},
    "T011": {"name": "Стереометрия", "subtopics": [
        "Многогранники: призма, пирамида", "Тела вращения: цилиндр, конус, шар", "Объёмы и площади поверхностей"]},
    "T012": {"name": "Тригонометрия", "subtopics": [
        "Основные тригонометрические тождества", "Тригонометрические уравнения", "Преобразование тригонометрических выражений"]},
    "T013": {"name": "Логарифмы и степени", "subtopics": [
        "Свойства степеней и корней", "Логарифмы: определение и свойства", "Показательные и логарифмические уравнения"]},
    "T014": {"name": "Производная и интеграл", "subtopics": [
        "Производная: правила вычисления", "Исследование функций с помощью производной", "Интеграл и его применение"]},
    "T015": {"name": "Теория чисел", "subtopics": [
        "Чётность, делимость, остатки", "Простые и составные числа", "Сравнения по модулю и диофантовы уравнения"]},
    "T016": {"name": "Графы и комбинаторные конструкции", "subtopics": [
        "Основные понятия теории графов", "Обходы графов: эйлеровы и гамильтоновы циклы", "Раскраски и комбинаторные конструкции"]},
    "T017": {"name": "Игры и стратегии", "subtopics": [
        "Симметричные стратегии и инварианты", "Анализ позиций: выигрышные и проигрышные", "Игры с конструированием и преследованием"]},
    "T018": {"name": "Инварианты и полуинварианты", "subtopics": [
        "Чётность и раскраски", "Суммы, произведения и остатки", "Алгоритмические инварианты"]},
    "T019": {"name": "Принцип крайнего и экстремальные задачи", "subtopics": [
        "Принцип крайнего", "Оценка и пример: неравенства и оптимизация", "Экстремальные задачи в геометрии"]},
    "T020": {"name": "Конструкции и примеры", "subtopics": [
        "Построение примеров с заданными свойствами", "Конструкции в комбинаторике", "Конструкции в геометрии"]},
    "T021": {"name": "Неравенства", "subtopics": [
        "Стандартные неравенства: Коши, Бернулли", "Методы доказательства неравенств", "Неравенства с параметрами"]},
    "T022": {"name": "Последовательности и суммы", "subtopics": [
        "Вычисление сумм и произведений", "Рекуррентные последовательности", "Пределы последовательностей"]},
    "T023": {"name": "Многочлены и алгебраические уравнения", "subtopics": [
        "Схема Горнера и теорема Безу", "Симметрические и возвратные многочлены", "Уравнения высших степеней"]},
    "T024": {"name": "Алгебра логики и булевы функции", "subtopics": [
        "Логические операции и таблицы истинности", "Булевы функции и их минимизация", "Комбинационные схемы и логические задачи"]},
    "T025": {"name": "Элементы математического анализа", "subtopics": [
        "Непрерывность и пределы", "Дифференцирование", "Интегрирование"]},
    "T026": {"name": "Вероятность и статистика", "subtopics": [
        "Случайные величины и распределения", "Статистические характеристики", "Условная вероятность и независимость"]},
    "T027": {"name": "Геометрические преобразования", "subtopics": [
        "Движения: параллельный перенос, поворот", "Симметрия и гомотетия", "Инверсия"]},
    "T028": {"name": "Методы доказательств и рассуждений", "subtopics": [
        "Метод от противного", "Индукция", "Принцип Дирихле"]},
    "T029": {"name": "Взвешивания, переливания, алгоритмы", "subtopics": [
        "Задачи на взвешивания", "Задачи на переливания", "Конструирование алгоритмов"]},
    "T030": {"name": "Позиционные системы счисления", "subtopics": [
        "Системы счисления с разными основаниями", "Арифметические операции в разных системах", "Применение систем счисления в задачах"]},
    "T031": {"name": "Графы: сети и потоки", "subtopics": [
        "Кратчайшие пути и остовные деревья", "Потоки в сетях: теорема Форда-Фалкерсона", "Двудольные графы и паросочетания"]},
    "T032": {"name": "Комплексные числа", "subtopics": [
        "Алгебраическая и тригонометрическая форма", "Корни из единицы и их свойства", "Комплексные числа в геометрии"]},
    "T033": {"name": "Элементы топологии и теории узлов", "subtopics": [
        "Топологические инварианты", "Лист Мёбиуса и бутылка Клейна", "Теория узлов: основные понятия"]},
    "T034": {"name": "Дискретная математика", "subtopics": [
        "Рекуррентные соотношения и производящие функции", "Теория Рамсея и экстремальная комбинаторика", "Кодирование и алгоритмы сжатия"]},
    "T035": {"name": "Математические головоломки", "subtopics": [
        "Классические головоломки (ханойская башня и др.)", "Задачи на разрезание и складывание", "Геометрические головоломки"]},
    "T036": {"name": "Календарь и время", "subtopics": [
        "Задачи на календарь и дни недели", "Часы и временные интервалы", "Периодические процессы"]},
    "T037": {"name": "Математика в быту и приложения", "subtopics": [
        "Финансовая математика", "Приближённые вычисления и погрешности", "Математические модели в жизни"]},
    "T038": {"name": "Логика и рассуждения", "subtopics": [
        "Логические задачи: рыцари и лжецы", "Задачи на анализ утверждений", "Логический вывод и умозаключения"]},
    "T039": {"name": "Алгоритмы и вычисления", "subtopics": [
        "Конструирование алгоритмов", "Оптимизация вычислений", "Дискретные алгоритмы"]},
    "T040": {"name": "Диофантовы уравнения", "subtopics": [
        "Линейные диофантовы уравнения", "Уравнения второй степени", "Уравнения высших степеней и методы перебора"]},
    "T041": {"name": "Планиметрия: задачи на доказательство", "subtopics": [
        "Доказательства с треугольниками", "Доказательства с четырёхугольниками", "Доказательства с окружностями"]},
    "T042": {"name": "Комбинаторные задачи", "subtopics": [
        "Классические комбинаторные схемы", "Комбинаторика с ограничениями", "Комбинаторные тождества и оценки"]},
    "T043": {"name": "Нестандартные задачи", "subtopics": [
        "Нестандартные постановки", "Междисциплинарные задачи", "Оценки и экстремумы"]},
}

GRADE_THEMES = {
    5: ["T001", "T002", "T003", "T028", "T029", "T038"],
    6: ["T001", "T002", "T003", "T017", "T028", "T038"],
    7: ["T001", "T002", "T003", "T017", "T028", "T038"],
    8: ["T001", "T002", "T003", "T008", "T017", "T038"],
    9: ["T007", "T008", "T009", "T015", "T017", "T038"],
    10: ["T007", "T008", "T009", "T015", "T017", "T038"],
    11: ["T007", "T008", "T009", "T011", "T015", "T017", "T038"],
}


def build_task_identifier(task):
    """Build SHA-256 hash of statement, first 12 hex chars."""
    stmt = task.get("statement", "")
    return hashlib.sha256(stmt.encode("utf-8")).hexdigest()[:12]


def load_gaps_csv(path):
    """Load gaps CSV and return dict: cell_key -> {grade, level, theme_id, subtopic_idx, needed, current_count}."""
    gaps = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cell_key = row["cell_key"]
            needed_raw = row["needed"].strip()
            current_raw = row["current_count"].strip()
            gaps[cell_key] = {
                "cell_key": cell_key,
                "grade": int(row["grade"]),
                "level": int(row["level"]),
                "theme_id": row["theme_id"],
                "subtopic_idx": int(row["subtopic_idx"]),
                "current_count": int(current_raw),
                "needed": int(needed_raw),
            }
    return gaps


def grade_themes_str(grade):
    """Return comma-separated theme list for DeepSeek prompt."""
    theme_ids = GRADE_THEMES.get(grade, [])
    parts = []
    for tid in theme_ids:
        info = THEMES.get(tid, {})
        name = info.get("name", tid)
        subs = "; ".join(info.get("subtopics", []))
        parts.append(f"{tid} - {name}: [{subs}]")
    return "\n".join(parts)


def build_verify_prompt(task, gap_cells_for_grade_level):
    """Build a prompt to verify if a rejected task is genuinely non-duplicate and could fill a gap."""
    stmt = task.get("statement", "")
    answer = task.get("answer", "")
    olympiad = task.get("olympiad", "")
    year = task.get("year", "")
    grade = task.get("grade", "")
    level = task.get("level", "")

    themes_str = grade_themes_str(grade)

    prompt = f"""Ты — эксперт по классификации олимпиадных задач по математике.

ЗАДАЧА:
{stmt[:1500]}

ОТВЕТ (для контекста):
{answer[:500]}

ИСТОЧНИК: {olympiad}, {year}
КЛАСС: {grade}
УРОВЕНЬ СЛОЖНОСТИ (уже задан): L{level} (где L4 — средняя сложность, L5 — высокая)

ЭТОТ ЗАДАЧА БЫЛА ОТМЕЧЕНА КАК ДУБЛИКАТ (высокая n-граммная схожесть с другой задачей в банке или среди кандидатов).
Твоя задача — проверить, является ли эта задача genuinely уникальной (не дубликатом) и определить её тематику.

Доступные темы для класса {grade}:
{themes_str}

Ответь в формате JSON:
{{
  "is_unique": true/false,
  "confidence": 0.0-1.0,
  "theme_id": "TXXX",
  "subtopic_idx": 0/1/2,
  "reasoning": "краткое объяснение, почему это уникальная задача или дубликат"
}}

Правила:
- "is_unique": true — если это genuinely НОВАЯ задача, не являющаяся переформулировкой/вариацией существующей
- "is_unique": false — если это действительно дубликат (та же математическая идея, переформулировка с числами)
- Для stage1b (exact match): is_unique=false наверняка
- Для stage2b (high similarity): может быть false positive, если n-граммы совпали случайно
- Выбери наиболее подходящую тему и подтему из списка для данного класса
- subtopic_idx: 0, 1, или 2 (индекс подтемы в списке subtopics)
"""
    return prompt


def parse_json_response(response_text):
    """Try to parse JSON from DeepSeek response. Handles markdown fences."""
    text = response_text.strip()
    # Try direct json.loads first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to find JSON inside markdown code fences
    import re
    # Match ```json ... ``` or ``` ... ```
    pattern = r"```(?:json)?\s*\n?(.*?)```"
    matches = re.findall(pattern, text, re.DOTALL)
    for match in matches:
        match = match.strip()
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    # Try to find anything that looks like a JSON object
    pattern = r"(\{.*\})"
    matches = re.findall(pattern, text, re.DOTALL)
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    return None


def analyze_rejection_reasons(data):
    """Analyze and print rejection reason distribution."""
    reasons = Counter(r["reason"] for r in data)
    print("[STAGE4] Rejection reason distribution:")
    for reason, count in reasons.most_common():
        print(f"    {reason}: {count}")
    print(f"    TOTAL: {len(data)}")

    # Grade/level distribution
    grades = Counter(r["grade"] for r in data)
    levels = Counter(r["level"] for r in data)
    print(f"[STAGE4] Grade distribution: {dict(sorted(grades.items()))}")
    print(f"[STAGE4] Level distribution: L4={levels.get(4,0)}, L5={levels.get(5,0)}")
    return reasons


def load_existing_results(results_path):
    """Load existing results for checkpoint resume."""
    if os.path.exists(results_path):
        with open(results_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def main():
    print("=" * 70)
    print("  STAGE 4: DUPLICATE RE-CHECK (rejected_tasks.json)")
    print("=" * 70)

    # ── Load data ────────────────────────────────────────────────────────
    print(f"\n[STAGE4] Loading rejected tasks from: {REJECTED_PATH}")
    with open(REJECTED_PATH, "r", encoding="utf-8") as f:
        rejected = json.load(f)
    print(f"[STAGE4] Loaded {len(rejected)} rejected tasks.")

    # Load gaps
    print(f"[STAGE4] Loading gaps from: {GAPS_CSV}")
    gaps = load_gaps_csv(GAPS_CSV)
    print(f"[STAGE4] Loaded {len(gaps)} gap cells.")

    # ── Phase 1: Analysis only (no API calls) ────────────────────────────
    print("\n" + "-" * 70)
    print("  PHASE 1: ANALYSIS OF REJECTION REASONS")
    print("-" * 70)

    reasons = analyze_rejection_reasons(rejected)

    # Separate by reason
    stage1b = [r for r in rejected if r["reason"] == "stage1b_exact_among_candidates"]
    stage2 = [r for r in rejected if r["reason"] == "stage2_high_similarity_vs_existing"]
    stage2b = [r for r in rejected if r["reason"] == "stage2b_high_similarity_among_candidates"]
    other = [r for r in rejected if r["reason"] not in ("stage1b_exact_among_candidates", "stage2_high_similarity_vs_existing", "stage2b_high_similarity_among_candidates")]

    print(f"\n[STAGE4] stage1b_exact_among_candidates: {len(stage1b)} tasks -> auto-reject (exact dupes)")
    print(f"[STAGE4] stage2_high_similarity_vs_existing: {len(stage2)} tasks -> needs DeepSeek check")
    print(f"[STAGE4] stage2b_high_similarity_among_candidates: {len(stage2b)} tasks -> needs DeepSeek check")
    if other:
        print(f"[STAGE4] OTHER reasons: {len(other)} tasks")

    # ── Phase 2: For stage1b, auto-classify as keep rejected ─────────────
    results = []
    for r in stage1b:
        results.append({
            "task_index": rejected.index(r),
            "task_id": build_task_identifier(r),
            "grade": r.get("grade"),
            "level": r.get("level"),
            "reason": r["reason"],
            "verdict": "REJECTED",
            "verdict_reasoning": "Exact normalized text match among candidates. Definitively a duplicate.",
        })

    # For "other" reasons, auto-reject
    for r in other:
        results.append({
            "task_index": rejected.index(r),
            "task_id": build_task_identifier(r),
            "grade": r.get("grade"),
            "level": r.get("level"),
            "reason": r["reason"],
            "verdict": "REJECTED",
            "verdict_reasoning": f"Unknown rejection reason: {r['reason']}",
        })

    print(f"\n[STAGE4] Phase 1 complete: {len(results)} tasks auto-classified as REJECTED.")

    # ── Phase 3: DeepSeek verification for stage2 and stage2b ────────────
    print("\n" + "-" * 70)
    print("  PHASE 2: DEEPSEEK VERIFICATION")
    print("-" * 70)
    print(f"[STAGE4] Tasks to verify: {len(stage2) + len(stage2b)}")

    # These need DeepSeek API. We'll use the ai/deepseek_client.py module.
    need_deepseek = stage2 + stage2b

    # Load existing results for checkpoint
    existing_results = load_existing_results(OUTPUT_JSON)
    processed_ids = set()
    for r in existing_results:
        tid = r.get("task_id", "")
        if tid:
            processed_ids.add(tid)
    print(f"[STAGE4] Already processed: {len(processed_ids)} tasks (from existing results).")

    # Import DeepSeek client
    sys.path.insert(0, BASE_DIR)
    try:
        from ai.deepseek_client import DeepSeekClient
        client = DeepSeekClient()
        print("[STAGE4] DeepSeek client loaded successfully.")
    except ImportError as e:
        print(f"[STAGE4] ERROR: Could not load DeepSeekClient: {e}")
        print("[STAGE4] Falling back to mock classification (no API calls).")
        client = None

    # Process each task
    total_to_process = len(need_deepseek)
    pending = [t for t in need_deepseek if build_task_identifier(t) not in processed_ids]
    print(f"[STAGE4] Tasks to process this run: {len(pending)} / {total_to_process}")

    if pending and client is not None:
        batch_size = 10
        for batch_start in range(0, len(pending), batch_size):
            batch = pending[batch_start:batch_start + batch_size]
            for task in batch:
                task_idx = rejected.index(task)
                task_id = build_task_identifier(task)
                grade = task.get("grade")
                level = task.get("level")
                rejection_reason = task.get("reason", "")

                # Build prompt
                prompt = build_verify_prompt(task, gaps)

                system_prompt = "Ты — математик-эксперт по классификации олимпиадных задач. Отвечай строго в формате JSON."

                try:
                    response = client.generate(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=0.2,
                        max_tokens=512,
                        response_format={"type": "json_object"},
                    )

                    parsed = parse_json_response(response)
                    if parsed is None:
                        # Fallback: try raw response as JSON
                        try:
                            parsed = json.loads(response)
                        except (json.JSONDecodeError, TypeError):
                            parsed = {"is_unique": False, "confidence": 0.0,
                                      "theme_id": None, "subtopic_idx": None,
                                      "reasoning": "Failed to parse DeepSeek response"}

                    is_unique = parsed.get("is_unique", False)
                    confidence = parsed.get("confidence", 0.0)
                    theme_id = parsed.get("theme_id", None)
                    subtopic_idx = parsed.get("subtopic_idx", None)
                    reasoning = parsed.get("reasoning", "")

                    # Determine verdict
                    if is_unique and confidence >= 0.70:
                        verdict = "REINSTATE_CANDIDATE"
                        verdict_reasoning = f"Genuinely unique task (confidence={confidence:.2f}). Theme={theme_id}, Subtopic={subtopic_idx}. {reasoning}"
                    elif is_unique and confidence < 0.70:
                        verdict = "UNCERTAIN"
                        verdict_reasoning = f"Possibly unique but low confidence ({confidence:.2f}). Theme={theme_id}, Subtopic={subtopic_idx}. {reasoning}"
                    else:
                        verdict = "REJECTED"
                        verdict_reasoning = f"Confirmed duplicate (confidence={confidence:.2f}). {reasoning}"

                    results.append({
                        "task_index": task_idx,
                        "task_id": task_id,
                        "grade": grade,
                        "level": level,
                        "reason": rejection_reason,
                        "verdict": verdict,
                        "confidence": confidence,
                        "theme_id": theme_id,
                        "subtopic_idx": subtopic_idx,
                        "reasoning": reasoning,
                    })
                    print(f"  [OK] Task {task_id} (G{grade}|L{level}|{rejection_reason}): {verdict} (conf={confidence:.2f})")

                except Exception as e:
                    print(f"  [ERR] Task {task_id} failed: {e}")
                    results.append({
                        "task_index": task_idx,
                        "task_id": task_id,
                        "grade": grade,
                        "level": level,
                        "reason": rejection_reason,
                        "verdict": "ERROR",
                        "confidence": 0.0,
                        "theme_id": None,
                        "subtopic_idx": None,
                        "reasoning": f"API error: {e}",
                    })

            # Save checkpoint after each batch
            with open(OUTPUT_JSON + ".tmp", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"[STAGE4] Checkpoint saved: {len(results)} results ({len(pending)} remaining)")

    elif pending and client is None:
        # No API - mock classification for stage2/2b tasks
        print("[STAGE4] No DeepSeek client - using heuristic classification.")
        for task in pending:
            task_id = build_task_identifier(task)
            grade = task.get("grade")
            level = task.get("level")
            rejection_reason = task.get("reason", "")

            # stage2_high_similarity_vs_existing: likely true duplicate
            if rejection_reason == "stage2_high_similarity_vs_existing":
                verdict = "REJECTED"
                confidence = 0.85
                reasoning = "High n-gram similarity to existing DB task >= 0.60. Likely true duplicate."
            else:
                # stage2b: could be false positive, but without API we conservatively reject
                verdict = "REJECTED"
                confidence = 0.50
                reasoning = "Similarity among candidates. Without DeepSeek verification, conservatively rejected."

            results.append({
                "task_index": rejected.index(task),
                "task_id": task_id,
                "grade": grade,
                "level": level,
                "reason": rejection_reason,
                "verdict": verdict,
                "confidence": confidence,
                "theme_id": None,
                "subtopic_idx": None,
                "reasoning": reasoning,
            })

    # Merge with existing results
    all_results = existing_results + [r for r in results if r["task_id"] not in processed_ids]

    # ── Phase 3: Generate report and reinstatement recommendations ───────
    print("\n" + "-" * 70)
    print("  PHASE 3: REPORT GENERATION")
    print("-" * 70)

    verdicts = Counter(r["verdict"] for r in all_results)
    print(f"[STAGE4] Final verdicts: {dict(verdicts)}")

    reinstatement_candidates = [r for r in all_results if r["verdict"] == "REINSTATE_CANDIDATE"]
    uncertain = [r for r in all_results if r["verdict"] == "UNCERTAIN"]
    rejected_final = [r for r in all_results if r["verdict"] == "REJECTED"]
    errors = [r for r in all_results if r["verdict"] == "ERROR"]

    print(f"\n[STAGE4] Reinstatement candidates: {len(reinstatement_candidates)}")
    print(f"[STAGE4] Uncertain: {len(uncertain)}")
    print(f"[STAGE4] Rejected: {len(rejected_final)}")
    print(f"[STAGE4] Errors: {len(errors)}")

    # For reinstatement candidates, check if they can fill gap cells
    reinstated_with_gaps = []
    for r in reinstatement_candidates:
        grade = r.get("grade")
        level = r.get("level")
        theme_id = r.get("theme_id")
        subtopic_idx = r.get("subtopic_idx")

        if theme_id and subtopic_idx is not None:
            cell_key = f"G{grade}|L{level}|{theme_id}|S{subtopic_idx}"
            if cell_key in gaps:
                gap = gaps[cell_key]
                r["target_cell"] = cell_key
                r["cell_needed"] = gap["needed"]
                reinstated_with_gaps.append(r)

    print(f"\n[STAGE4] Reinstatement candidates matching gap cells: {len(reinstated_with_gaps)}")

    # Build the reinstated candidates output
    reinstated_output = []
    for r in reinstated_with_gaps:
        task_idx = r["task_index"]
        task = rejected[task_idx]
        reinstated_output.append({
            "task": task,
            "verdict_info": {
                "confidence": r.get("confidence"),
                "theme_id": r.get("theme_id"),
                "subtopic_idx": r.get("subtopic_idx"),
                "target_cell": r.get("target_cell"),
                "cell_needed": r.get("cell_needed"),
                "reasoning": r.get("reasoning"),
            }
        })

    # ── Write outputs ────────────────────────────────────────────────────
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n[STAGE4] Results saved to: {OUTPUT_JSON}")

    with open(OUTPUT_REINSTATED, "w", encoding="utf-8") as f:
        json.dump(reinstated_output, f, ensure_ascii=False, indent=2)
    print(f"[STAGE4] Reinstated candidates saved to: {OUTPUT_REINSTATED}")

    # Clean up temp file
    tmp_path = OUTPUT_JSON + ".tmp"
    if os.path.exists(tmp_path):
        os.remove(tmp_path)

    # ── Write report ─────────────────────────────────────────────────────
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  STAGE 4: DUPLICATE RE-CHECK REPORT\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Total rejected tasks: {len(rejected)}\n")
        f.write(f"  stage1b_exact_among_candidates: {len(stage1b)}\n")
        f.write(f"  stage2_high_similarity_vs_existing: {len(stage2)}\n")
        f.write(f"  stage2b_high_similarity_among_candidates: {len(stage2b)}\n\n")

        f.write(f"FINAL VERDICTS:\n")
        f.write(f"  REINSTATE_CANDIDATE: {len(reinstatement_candidates)}\n")
        f.write(f"  UNCERTAIN: {len(uncertain)}\n")
        f.write(f"  REJECTED: {len(rejected_final)}\n")
        f.write(f"  ERROR: {len(errors)}\n\n")

        f.write(f"Reinstatement candidates matching gap cells: {len(reinstated_with_gaps)}\n\n")

        if reinstated_with_gaps:
            f.write("REINSTATEMENT CANDIDATES (matching gaps):\n")
            f.write("-" * 70 + "\n")
            for r in reinstated_with_gaps:
                task_idx = r["task_index"]
                task = rejected[task_idx]
                f.write(f"  [{r['target_cell']}] need={r['cell_needed']} | "
                        f"conf={r.get('confidence', 0):.2f} | "
                        f"G{r.get('grade')}|L{r.get('level')} | "
                        f"reason={r.get('reason')}\n")
                f.write(f"  Statement: {task.get('statement', '')[:120]}...\n")
                f.write(f"  Reasoning: {r.get('reasoning', '')[:200]}\n\n")

        if uncertain:
            f.write("\nUNCERTAIN TASKS:\n")
            f.write("-" * 70 + "\n")
            for r in uncertain:
                task_idx = r["task_index"]
                task = rejected[task_idx]
                f.write(f"  G{r.get('grade')}|L{r.get('level')} | "
                        f"conf={r.get('confidence', 0):.2f} | "
                        f"reason={r.get('reason')}\n")
                f.write(f"  Statement: {task.get('statement', '')[:100]}...\n\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("  END OF REPORT\n")
        f.write("=" * 70 + "\n")

    print(f"[STAGE4] Report saved to: {OUTPUT_REPORT}")
    print(f"\n[STAGE4] Done. {len(all_results)} results total.")
    print(f"[STAGE4]   REINSTATE_CANDIDATE: {len(reinstatement_candidates)}")
    print(f"[STAGE4]   UNCERTAIN: {len(uncertain)}")
    print(f"[STAGE4]   REJECTED: {len(rejected_final)}")
    print(f"[STAGE4]   ERROR: {len(errors)}")
    if reinstated_with_gaps:
        print(f"[STAGE4]   Matching gap cells: {len(reinstated_with_gaps)}")


if __name__ == "__main__":
    main()
