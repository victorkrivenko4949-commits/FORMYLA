#!/usr/bin/env python3
"""
regenerate.py — Перегенерация 311 завышенных задач через DeepSeek API.

Скрипт читает level_overrated.jsonl (список 311 задач с завышенным уровнем),
для каждой генерирует НОВУЮ задачу (та же тема, класс, заявленный уровень,
но реально соответствующую этому уровню), и заменяет task_text/solution/correct_answer
in-place в final_db_1_5.json по id.

Использование:
    python regenerate.py

Требует переменную окружения DEEPSEEK_API_KEY.
"""

import os, json, time, requests, shutil, re
from collections import Counter

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")
if not DEEPSEEK_KEY:
    raise SystemExit("ERROR: DEEPSEEK_API_KEY не задан!")

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"

# --- Пути ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OVERRATED = os.path.join(BASE_DIR, "level_overrated.jsonl")
DB_PATH = r"C:\Users\Victor\Downloads\final_db_1_5.json"
BACKUP_PATH = r"C:\Users\Victor\Downloads\final_db_1_5_backup.json"
OUT_LOG = os.path.join(BASE_DIR, "regenerate_log.jsonl")

LEVEL_DESC = {
    1: "лёгкая школьная: одно действие, устный счёт",
    2: "школьная: 1-2 стандартных шага, знакомый шаблон",
    3: "школьный этап олимпиады: нужна идея, 2-3 шага, немного разбора случаев",
    4: "муниципальный этап: нетривиальная идея, комбинация методов, оценка+пример",
    5: "сложный муниципальный: несколько идей, доказательство, инвариант/крайнее, трудная конструкция",
}

SYSTEM_PROMPT = r"""Ты — методист-составитель олимпиадных задач по математике для российской школы (5-11 класс).
Ты придумываешь ОРИГИНАЛЬНЫЕ задачи строго заданного уровня сложности.

ШКАЛА УРОВНЕЙ:
1 — лёгкая школьная (одно действие, устный счёт).
2 — школьная (1-2 стандартных шага, знакомый шаблон).
3 — школьный этап олимпиады (нужна идея, 2-3 шага, немного разбора случаев).
4 — муниципальный этап (нетривиальная идея, комбинация методов, оценка+пример).
5 — сложный муниципальный (несколько идей, доказательство, инвариант/принцип крайнего, трудная конструкция).

ГЛАВНОЕ ПРАВИЛО: уровень задаётся ГЛУБИНОЙ РАССУЖДЕНИЯ, а НЕ размером чисел, страшностью формул или экзотичностью темы.
Задача, решаемая в одно-два действия «в лоб» (даже с большими числами) — это уровень 1-2, и НИКОГДА не 4-5.

ЗАПРЕЩЁННЫЕ ШАБЛОНЫ для уровней 4-5 (это НЕ сложные задачи, не генерируй их как уровень 4-5):
- «Устный Виет» — подбор корней квадратного трёхчлена по сумме/произведению.
- Задачи про «сумму цифр» (свойства делимости на 9 или на 3 — это уровень 1-2).
- «Сколько делителей у числа?» — тупая формула — это уровень 1-2.
- «Принцип Дирихле» в формулировке «12 клеток, 13 кроликов» — это уровень 1-2.
- «Найдите НОД/НОК» — алгоритм нахождения — это уровень 1-2.
- Тривиальные применения формулы площади/объёма (подставить числа в S = a·b или V = a·b·c — уровень 1-2).
- Любая задача, где достаточно одного пассивного действия (подставить, вычислить) — это уровень 1-2.

ФОРМАТ ВЫХОДА (строго JSON, без markdown-разметки, без кодовых блоков):
{
  "task_text": "<условие, формулы в LaTeX-инлайн $...$>",
  "solution": "<подробное решение, LaTeX-инлайн $...$, формулы на отдельных строках $$...$$>",
  "correct_answer": "<числовой ответ или краткое выражение, при необходимости с единицами измерения>"
}

ВАЖНО:
- Все LaTeX-формулы в строках JSON должны быть обрамлены $...$ (inline) или $$...$$ (display).
- НЕ используй \(...\) или \[...\] — это сломает JSON.
- Не используй обратную косую черту вне LaTeX-контекста.
- Ответ должен быть точным и однозначным (число, выражение, неравенство).
- Убедись, что JSON валиден: экранируй кавычки внутри строк как \". """


def user_prompt(overrated_task: dict) -> str:
    """Формирует user-промпт для генерации новой задачи."""
    return f"""Сгенерируй НОВУЮ ОРИГИНАЛЬНУЮ задачу по математике.

Класс: {overrated_task['class_level']}
Предмет: {overrated_task['subject']}
Требуемый уровень сложности: {overrated_task['current_difficulty_level']}
Описание уровня: {LEVEL_DESC.get(overrated_task['current_difficulty_level'], '')}
Причина завышения: {overrated_task.get('reason_template', 'не указана')}

Критерии:
1. Задача должна быть НОВОЙ (не совпадать с приведённой ниже).
2. Реально соответствовать заявленному уровню сложности {overrated_task['current_difficulty_level']}.
3. Быть уместной для указанного класса ({overrated_task['class_level']}) и предмета ({overrated_task['subject']}).
4. Иметь однозначный ответ.
5. Содержать подробное решение.

Старая задача (завышенная), её нужно ЗАМЕНИТЬ, а не дополнить:
ID: {overrated_task['id']}
Условие: {overrated_task.get('task_text', '')}
Ответ: {overrated_task.get('correct_answer', '')}"""


def _sanitize_json(raw: str) -> str:
    r"""Очищает JSON от невалидных LaTeX-escape-последовательностей.

    Проблема: DeepSeek API возвращает JSON, в котором внутри строк
    могут быть LaTeX-команды вроде \text, \frac, \sqrt, \cdot,
    а также \( \) или \[ \] — всё это НЕ является валидным JSON-escape.

    Валидные JSON-escape: \\, \", \/, \b, \f, \n, \r, \t, \uXXXX.
    Всё остальное (например \(, \), \t, \f, \s, \q, \rт) — ошибка.
    """
    # 1. Сначала конвертируем \( \) в $...$ (LaTeX inline)
    #    и \[ \] в $$...$$ (LaTeX display)
    raw = re.sub(r'\\\(', '$', raw)
    raw = re.sub(r'\\\)', '$', raw)
    raw = re.sub(r'\\\[', '$$', raw)
    raw = re.sub(r'\\\]', '$$', raw)

    # 2. Теперь ищем любые оставшиеся \X, где X — невалидный escape.
    #    Валидные: " \ / b f n r t u
    #    Если после \ идёт что-то другое — экранируем как \\X
    def _fix_escapes(m: re.Match) -> str:
        ch = m.group(1)
        if ch in ('"', '\\', '/', 'b', 'f', 'n', 'r', 't', 'u'):
            return m.group(0)  # уже валидно
        return '\\\\' + ch  # дублируем backslash

    raw = re.sub(r'\\(.)', _fix_escapes, raw)
    return raw


def call_deepseek(prompt: str, system_prompt: str = None, max_tokens: int = 2048, temperature: float = 0.7) -> dict:
    """Вызов DeepSeek API с обработкой JSON и повторными попытками."""
    if system_prompt is None:
        system_prompt = SYSTEM_PROMPT

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"}
    }

    for attempt in range(5):
        try:
            resp = requests.post(API_URL, headers=headers, json=payload, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()

            # Санируем JSON перед парсингом
            clean = _sanitize_json(content)
            try:
                return json.loads(clean)
            except json.JSONDecodeError as e:
                # Если не помогло — пробуем найти JSON в тексте
                start = clean.find('{')
                end = clean.rfind('}')
                if start != -1 and end != -1:
                    candidate = clean[start:end+1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
                raise

        except requests.exceptions.Timeout:
            print(f"  [!] Таймаут (попытка {attempt+1}/5)")
            if attempt == 4:
                raise
            time.sleep(5)
        except requests.exceptions.RequestException as e:
            print(f"  [!] Ошибка запроса: {e} (попытка {attempt+1}/5)")
            if attempt == 4:
                raise
            time.sleep(5)
        except json.JSONDecodeError as e:
            print(f"  [!] Ошибка парсинга JSON: {e}")
            print(f"  [!] Сырой ответ: {content[:200]}...")
            if attempt == 4:
                raise
            time.sleep(5)


def backup_db():
    """Создаёт бекап, если его ещё нет."""
    if not os.path.exists(BACKUP_PATH):
        shutil.copy2(DB_PATH, BACKUP_PATH)
        print(f"[*] Бекап создан: {BACKUP_PATH}")
    else:
        print("[*] Бекап уже существует.")


def load_db() -> list:
    """Загружает БД из JSON."""
    with open(DB_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_db(db: list):
    """Сохраняет БД в JSON."""
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def load_overrated() -> list:
    """Загружает список задач с завышенным уровнем из JSONL."""
    tasks = []
    with open(OVERRATED, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                tasks.append(json.loads(line))
    return tasks


def log_result(entry: dict):
    """Дописывает результат в лог."""
    with open(OUT_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def main():
    backup_db()
    db = load_db()
    overrated = load_overrated()

    # Индекс задач по id
    db_index = {task['id']: task for task in db}

    print(f"[*] Загружено задач в БД: {len(db)}")
    print(f"[*] Задач для перегенерации: {len(overrated)}")

    stats = Counter()  # ok, fail, skip
    autosave_counter = 0
    total = len(overrated)

    for idx, o_task in enumerate(overrated, 1):
        task_id = o_task['id']
        print(f"\n[{idx}/{total}] Обработка задачи ID={task_id}...")

        if task_id not in db_index:
            print(f"  [!] ID {task_id} не найден в БД, пропуск.")
            stats['skip'] += 1
            log_result({"id": task_id, "status": "skip", "reason": "not_found"})
            continue

        try:
            prompt = user_prompt(o_task)
            result = call_deepseek(prompt)
        except Exception as e:
            print(f"  [!!] Ошибка: {e}")
            stats['fail'] += 1
            log_result({"id": task_id, "status": "fail", "error": str(e)})
            continue

        # Проверка полей
        if not all(k in result for k in ('task_text', 'solution', 'correct_answer')):
            print(f"  [!] Неполный ответ API: {list(result.keys())}")
            stats['fail'] += 1
            log_result({"id": task_id, "status": "fail", "error": "missing_fields", "keys": list(result.keys())})
            continue

        # Замена задачи в БД
        task = db_index[task_id]
        old_text = task.get('task_text', '')[:80]
        task['task_text'] = result['task_text']
        task['solution'] = result['solution']
        task['correct_answer'] = result['correct_answer']

        stats['ok'] += 1
        autosave_counter += 1
        log_result({
            "id": task_id,
            "status": "ok",
            "class_level": o_task.get('class_level'),
            "subject": o_task.get('subject'),
            "level": o_task.get('current_difficulty_level'),
        })
        print(f"  [OK] Старое условие: {old_text}...")
        print(f"  [OK] Новое условие: {result['task_text'][:80]}...")

        # Автосохранение каждые 20 задач
        if autosave_counter >= 20:
            print(f"\n[*] Автосохранение ({idx}/{total})...")
            save_db(db)
            autosave_counter = 0

    # Финальное сохранение
    print(f"\n[*] Финальное сохранение...")
    save_db(db)

    # Итог
    print(f"\n{'='*50}")
    print(f"РЕЗУЛЬТАТЫ:")
    print(f"  Успешно:  {stats['ok']}")
    print(f"  Ошибок:   {stats['fail']}")
    print(f"  Пропущено: {stats['skip']}")
    print(f"  Всего:    {stats['ok'] + stats['fail'] + stats['skip']}")
    print(f"  Лог:      {OUT_LOG}")
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
