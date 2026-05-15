"""Generate missing adaptive-test tasks via DeepSeek API.

What it does
============
1. Reads `adaptive_tasks` rows from instance/formyla.db.
2. For each (class_level, ui_topic) combination it counts how many
   non-flagged tasks match the SAME keyword filter that
   `app.adaptive_test_start_simple()` uses. If the count is below
   --min-count (default 12), the combination is "недозалитая".
3. For each недозалитой комбинации:
     * берёт 3-5 случайных уже существующих задач этой темы как образец
       стиля, калибровки сложности и формата критериев;
     * формирует промпт «сгенерируй N новых задач в JSON-массиве,
       каждое поле — как в БД adaptive_tasks: class_level, difficulty_level,
       topic, subtopic, task_text, solution, criteria_1_point,
       criteria_2_points, correct_answer»;
     * вызывает DeepSeekClient.generate(...);
     * чистит markdown-обёртку, парсит JSON;
     * валидирует и нормализует поля;
     * стримом пишет каждую задачу в adaptive_data/_generated/<cls>_<topic>_<ts>.jsonl;
     * сразу инсертит в SQLite (с de-dup по task_text).

Не трогает существующие генераторы и пайплайны.

CLI
===
    python scripts/generate_missing_adaptive_tasks.py            # все недозалитые комбо
    python scripts/generate_missing_adaptive_tasks.py --only knights_liars
    python scripts/generate_missing_adaptive_tasks.py --grades 9 10 11 --target 12
    python scripts/generate_missing_adaptive_tasks.py --dry-run
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import random
import re
import sqlite3
import sys
import time
from typing import Iterable

# Make project root importable
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# Load .env (DEEPSEEK_API_KEY)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError  # noqa: E402
from services.adaptive_topic_mapping import (
    TOPIC_KEYWORDS_BY_GRADE,
    get_keywords_for_grade_topic,
)  # noqa: E402

DB_PATH = os.path.join("instance", "formyla.db")
OUT_DIR = os.path.join("adaptive_data", "_generated")
os.makedirs(OUT_DIR, exist_ok=True)

UI_TOPICS = ["algebra", "geometry", "combinatorics",
             "number_theory", "movement", "knights_liars"]
GRADES = [5, 6, 7, 8, 9, 10, 11]

UI_TOPIC_NAMES_RU = {
    "algebra": "Алгебра",
    "geometry": "Геометрия",
    "combinatorics": "Комбинаторика",
    "number_theory": "Теория чисел",
    "movement": "Задачи на движение",
    "knights_liars": "Логика. Рыцари и лжецы",
}

FALLBACK_KEYWORDS = {
    "algebra": ["алгебра", "выражения", "одночлен", "многочлен", "формул"],
    "geometry": ["геометрия", "треугольник", "четырехугольник", "окружность",
                 "вектор", "площад", "стереометр", "многогранник",
                 "тела вращения", "объем"],
    "combinatorics": ["комбинатор", "вероятност", "перестановк", "размещен", "сочетан"],
    "number_theory": ["натуральн", "делимост", "положительн", "отрицательн",
                      "рациональн", "числ", "НОД", "НОК"],
    "movement": ["движен", "текстовые задачи", "совместная работа"],
    "knights_liars": ["рыцар", "лжец"],
}


def keywords_for(grade: int, topic: str) -> list[str]:
    kw = get_keywords_for_grade_topic(grade, topic)
    return kw if kw else FALLBACK_KEYWORDS.get(topic, [])


def fetch_count(cur: sqlite3.Cursor, grade: int, topic_ui: str) -> int:
    kws = [k.lower() for k in keywords_for(grade, topic_ui)]
    rows = cur.execute(
        "SELECT topic FROM adaptive_tasks WHERE class_level=? AND is_flagged=0",
        (grade,),
    ).fetchall()
    if not kws:
        return len(rows)
    return sum(1 for (t,) in rows if t and any(k in t.lower() for k in kws))


def fetch_examples(cur: sqlite3.Cursor, grade: int, topic_ui: str,
                   limit: int = 4) -> list[dict]:
    """Return up to `limit` random non-flagged tasks matching the topic."""
    kws = [k.lower() for k in keywords_for(grade, topic_ui)]
    rows = cur.execute(
        """SELECT class_level, difficulty_level, topic, subtopic, task_text,
                  solution, criteria_1_point, criteria_2_points, correct_answer
           FROM adaptive_tasks WHERE class_level=? AND is_flagged=0""",
        (grade,),
    ).fetchall()
    cols = ["class_level", "difficulty_level", "topic", "subtopic",
            "task_text", "solution", "criteria_1_point",
            "criteria_2_points", "correct_answer"]
    matches = []
    for r in rows:
        d = dict(zip(cols, r))
        if not d.get("topic"):
            continue
        if not kws or any(k in d["topic"].lower() for k in kws):
            matches.append(d)
    random.shuffle(matches)
    return matches[:limit]


def existing_topics(cur: sqlite3.Cursor, grade: int, topic_ui: str) -> list[str]:
    """Distinct DB topic strings already present for this (grade, ui_topic)."""
    kws = [k.lower() for k in keywords_for(grade, topic_ui)]
    rows = cur.execute(
        """SELECT topic, COUNT(*) c FROM adaptive_tasks
           WHERE class_level=? AND is_flagged=0
           GROUP BY topic ORDER BY c DESC""",
        (grade,),
    ).fetchall()
    out = []
    for t, _ in rows:
        if not t:
            continue
        if not kws or any(k in t.lower() for k in kws):
            out.append(t)
    return out


def difficulty_distribution(cur: sqlite3.Cursor, grade: int, topic_ui: str) -> dict[int, int]:
    kws = [k.lower() for k in keywords_for(grade, topic_ui)]
    rows = cur.execute(
        "SELECT difficulty_level, topic FROM adaptive_tasks WHERE class_level=? AND is_flagged=0",
        (grade,),
    ).fetchall()
    dist: dict[int, int] = {}
    for d, t in rows:
        if not t:
            continue
        if not kws or any(k in t.lower() for k in kws):
            dist[int(d) if d is not None else 0] = dist.get(int(d) if d is not None else 0, 0) + 1
    return dist


SYSTEM_PROMPT = (
    "Ты — опытный методист по олимпиадной математике для российских школьников, "
    "автор оригинальных задач для подготовки к ВсОШ. "
    "Ты получаешь несколько примеров для калибровки стиля и должен сгенерировать "
    "набор АВТОРСКИХ задач того же класса и темы.\n\n"
    "СТРОГО ЗАПРЕЩЕНО:\n"
    "- Копировать или даже близко перефразировать задачи из реальных олимпиад "
    "(ВсОШ, Турнир городов, Матпраздник, и т.д.) — придумывай задачи с нуля.\n"
    "- Брать классические известные задачи (\"задача о мостах Кёнигсберга\", "
    "\"задача о монахе и горе\", и подобные).\n"
    "- Повторять условия из примеров.\n"
    "- Создавать НЕРЕШАЕМЫЕ или ПЛОХО ПОСТАВЛЕННЫЕ задачи. У КАЖДОЙ задачи "
    "ОБЯЗАТЕЛЬНО должен быть ОДНОЗНАЧНЫЙ конкретный ответ (число, формула, "
    "конструкция). Если по ходу решения задачи получается \"нет решений\", "
    "\"задача не имеет ответа\", \"не существует такого\", \"уточните формулировку\" "
    "— НЕ ВЫДАВАЙ такую задачу, замени её на другую.\n"
    "- Использовать формулировки в духе \"сколько решений имеет задача\", "
    "\"найдите все P такие что…\", если ты не уверен в существовании ответа. "
    "Сначала придумай ОТВЕТ и решение, потом сформулируй задачу.\n"
    "- Создавать задачи с отрицательным результатом существования "
    "(\"докажите, что не существует…\") уровня выше L4 — они слишком хитрые.\n\n"
    "ПРОЦЕСС РАБОТЫ:\n"
    "1. Сначала придумай конкретный ОТВЕТ (число, набор, формулу).\n"
    "2. Затем спроектируй УСЛОВИЕ, которое к нему ведёт.\n"
    "3. Запиши АВТОРСКОЕ ПОЛНОЕ РЕШЕНИЕ — пройди его сам, шаг за шагом.\n"
    "4. Если в процессе обнаружил, что задача неоднозначна, не имеет ответа, "
    "противоречива, или решается тривиально — ПЕРЕДЕЛАЙ задачу с нуля.\n"
    "5. Только когда задача проходит свой же тест на решаемость — выдавай.\n\n"
    "Примеры — только для понимания стиля, формата записи и КАЛИБРОВКИ СЛОЖНОСТИ. "
    "Не используй их как образец содержания.\n\n"
    "Калибровка сложности — относительно этапов ВсОШ:\n"
    "  level 1 — чуть выше школьного учебника (бытовая разминка, 1-2 шага).\n"
    "  level 2 — школьный этап ВсОШ (стандартная задача из учебника, простой ход).\n"
    "  level 3 — школьный/начало муниципального этапа.\n"
    "  level 4 — муниципальный этап (нужна одна нетривиальная идея).\n"
    "  level 5 — сложный муниципальный / лёгкий региональный (комбинация 2 идей).\n"
    "  level 6 — региональный этап (требует серьёзного рассуждения, 3+ идей).\n"
    "  level 7 — сложный регион / заключительный этап (на грани творчества, "
    "нестандартный ход, аккуратное рассуждение).\n\n"
    "Возвращай СТРОГО валидный JSON-массив без markdown, без комментариев, "
    "без преамбулы. Каждый элемент массива — объект с полями:\n"
    "  - class_level (int)\n"
    "  - difficulty_level (int 1..7)\n"
    "  - topic (str, как в примерах)\n"
    "  - subtopic (str, можно пусто)\n"
    "  - task_text (str, условие, LaTeX в \\( ... \\) или \\[ ... \\], не использовать $...$)\n"
    "  - solution (str, полное авторское решение)\n"
    "  - criteria_1_point (str, критерий на 1 балл)\n"
    "  - criteria_2_points (str, критерий на 2 балла)\n"
    "  - correct_answer (str, краткий ответ)\n"
    "Условие — оригинальное, без подсказок к решению и без слов "
    "\"докажите/найдите/покажите\" вне самого вопроса."
)


LEVEL_HINTS = {
    1: "чуть выше школьного учебника — бытовая разминка с одним поворотом, "
       "решается за 1-2 шага без специальных приёмов",
    2: "школьный этап ВсОШ — простая задача из стандартной школьной программы, "
       "2-3 шага рассуждения, привычные приёмы",
    3: "школьный или начало муниципального этапа ВсОШ — задача среднего уровня, "
       "3-4 шага рассуждения, требует аккуратности",
    4: "муниципальный этап ВсОШ — задача требует ОДНУ нетривиальную идею или "
       "конструкцию, не решается прямым школьным методом",
    5: "сложный муниципальный / лёгкий региональный этап — комбинация 2 идей, "
       "аккуратный анализ случаев, грамотная конструкция",
    6: "региональный этап ВсОШ — серьёзная олимпиадная задача, нужно 2-3 связанных "
       "идеи, продуманное доказательство, может потребоваться оценка+пример",
    7: "сложный региональный или заключительный этап ВсОШ — задача на грани творческого "
       "решения, нестандартный ход, тонкая комбинаторная или геометрическая идея",
}


def build_prompt(grade: int, topic_ui: str, examples: list[dict],
                 db_topics: list[str], dist: dict[int, int],
                 batch_size: int, target_level: int | None = None) -> str:
    topic_ru = UI_TOPIC_NAMES_RU.get(topic_ui, topic_ui)
    primary_topic = db_topics[0] if db_topics else f"{topic_ru} ({grade} класс)"
    if target_level is None:
        diff_summary = ", ".join(f"уровень {k}: {v}" for k, v in sorted(dist.items()) if k)
        if not diff_summary:
            diff_summary = "распределить уровни 2..6 равномерно"
        level_clause = (
            f"Распределение сложностей в существующих задачах: {diff_summary}.\n"
            f"Старайся придерживаться этого распределения."
        )
    else:
        hint = LEVEL_HINTS.get(target_level, "")
        level_clause = (
            f"СТРОГО все {batch_size} задачи должны иметь difficulty_level = {target_level} "
            f"({hint}). Не отклоняйся в другие уровни."
        )

    ex_block_parts = []
    for i, ex in enumerate(examples, 1):
        ex_block_parts.append(
            f"Пример {i} (difficulty_level={ex.get('difficulty_level')}, "
            f"topic=\"{ex.get('topic','')}\"):\n"
            f"  task_text: {ex.get('task_text','')}\n"
            f"  solution:  {(ex.get('solution') or '')[:1200]}\n"
            f"  criteria_1_point: {ex.get('criteria_1_point','')}\n"
            f"  criteria_2_points: {ex.get('criteria_2_points','')}\n"
            f"  correct_answer: {ex.get('correct_answer') or ''}"
        )
    ex_block = "\n\n".join(ex_block_parts) if ex_block_parts else "(примеров нет, опирайся на стандарт темы)"

    return (
        f"Класс: {grade}\n"
        f"Тема (UI): {topic_ru}\n"
        f"Допустимые значения поля topic: {db_topics or [primary_topic]}.\n"
        f"Используй основное значение topic = \"{primary_topic}\".\n"
        f"{level_clause}\n\n"
        f"=== ПРИМЕРЫ существующих задач этой комбинации ===\n{ex_block}\n\n"
        f"=== ЗАДАНИЕ ===\n"
        f"Сгенерируй ровно {batch_size} новых уникальных задач строго в формате JSON-массива "
        f"(см. поля в системной инструкции). Не повторяй условия примеров. "
        f"Не используй symbols $...$; вместо этого \\( ... \\) или \\[ ... \\]."
    )


_FENCE_RE = re.compile(r"^```(?:json|JSON)?\s*\n?|\n?```\s*$")


_VALID_ESC_RE = re.compile(r'\\(["\\/bfnrtu])')


def _escape_lone_backslashes(s: str) -> str:
    """Replace lone backslashes (used in raw LaTeX like \\frac, \\(, \\)) with
    properly escaped \\\\ for JSON.

    IMPORTANT FIX: We can't blindly preserve \\f / \\t / \\n / \\r / \\b just
    because they are nominally valid JSON escapes. The LLM very often writes
    raw LaTeX like \\frac, \\theta, \\triangle, \\nabla, \\rho, \\bigcap. If
    we leave \\f/\\t/etc unescaped, json.loads() converts them into form-feed,
    tab, etc. control characters and the LaTeX command name is permanently
    corrupted (e.g. \\frac -> \\x0c rac).

    Heuristic: if \\f / \\t / \\n / \\r / \\b is followed by a LATIN LETTER,
    treat it as a LaTeX command (escape the backslash). Only treat it as a
    real JSON escape if it's followed by punctuation/whitespace/brace/EOF.
    Inside actual model JSON output, real \\n / \\t separators always appear
    between fields/lines, never glued to a Latin word.
    """
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\":
            # Look ahead one char to decide
            nxt = s[i + 1] if i + 1 < n else ""
            after = s[i + 2] if i + 2 < n else ""
            if nxt in ('"', "\\", "/"):
                out.append(ch); out.append(nxt); i += 2; continue
            if nxt == "u" and i + 5 < n and re.match(r"[0-9a-fA-F]{4}", s[i + 2:i + 6]):
                out.append(s[i:i + 6]); i += 6; continue
            if nxt in ("b", "f", "n", "r", "t"):
                # Real JSON escape only if NOT followed by ASCII letter,
                # otherwise it's a LaTeX command like \\frac, \\theta etc.
                if after.isalpha():
                    out.append("\\\\"); i += 1; continue
                out.append(ch); out.append(nxt); i += 2; continue
            # Lone backslash → escape it
            out.append("\\\\"); i += 1; continue
        out.append(ch); i += 1
    return "".join(out)


def _strip_unterminated_tail(s: str) -> str:
    """If a JSON array text is cut off in the middle, drop the partial last
    object so the rest can still parse."""
    last_close = s.rfind("}")
    if last_close == -1:
        return s
    head = s[: last_close + 1]
    # find the matching opening [
    open_b = head.find("[")
    if open_b == -1:
        return s
    return head[open_b:] + "]"


def _extract_objects(s: str) -> list[str]:
    """Walk through `s` and extract substrings of every top-level JSON object.
    Tracks string boundaries so braces inside strings are ignored."""
    out: list[str] = []
    n = len(s)
    i = 0
    while i < n:
        if s[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        start = i
        j = i
        terminated = False
        while j < n:
            ch = s[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        terminated = True
                        out.append(s[start:j + 1])
                        i = j + 1
                        break
            j += 1
        if not terminated:
            # unterminated object — stop
            break
    return out


def parse_json_array(text: str) -> list[dict]:
    """Return list of dicts from model output (tolerant to markdown fences,
    raw LaTeX backslashes, truncated arrays)."""
    s = text.strip()
    s = _FENCE_RE.sub("", s).strip()

    candidates = [s]
    # Heuristic: extract first [...] block
    m = re.search(r"\[\s*\{.*\}\s*\]", s, re.DOTALL)
    if m:
        candidates.append(m.group(0))
    # Add a "truncated tail dropped" version
    candidates.append(_strip_unterminated_tail(s))
    # And a backslash-fixed version of each candidate
    for c in list(candidates):
        candidates.append(_escape_lone_backslashes(c))

    last_err: Exception | None = None
    for cand in candidates:
        try:
            data = json.loads(cand)
        except Exception as e:
            last_err = e
            continue
        if isinstance(data, dict) and "tasks" in data:
            data = data["tasks"]
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]

    # Last resort: extract individual objects and parse them one by one
    rescued: list[dict] = []
    for variant in (s, _escape_lone_backslashes(s)):
        for obj_text in _extract_objects(variant):
            for variant_obj in (obj_text, _escape_lone_backslashes(obj_text)):
                try:
                    obj = json.loads(variant_obj)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    rescued.append(obj)
                    break
        if rescued:
            return rescued
    raise last_err or ValueError("could not parse JSON array")


REQUIRED_FIELDS = ("task_text", "solution",
                   "criteria_1_point", "criteria_2_points")


def normalize(rec: dict, grade: int, primary_topic: str) -> dict | None:
    def _collapse_bs(s):
        """Collapse runs of 2+ backslashes to single backslash for MathJax."""
        if not s:
            return s
        return re.sub(r"\\{2,}", r"\\", s)

    text = _collapse_bs((rec.get("task_text") or "").strip())
    if not text or len(text) < 25:
        return None
    if "$" in text:
        # forbid $...$ (LaTeX leak); convert obvious cases
        text = text.replace("$$", "").replace("$", "")
    rec["task_text"] = text
    rec["solution"] = _collapse_bs((rec.get("solution") or "").strip()) or "(решение отсутствует)"
    rec["criteria_1_point"] = _collapse_bs((rec.get("criteria_1_point") or "").strip()) or "1 балл — частично верное решение."
    rec["criteria_2_points"] = _collapse_bs((rec.get("criteria_2_points") or "").strip()) or "2 балла — полное верное решение."
    rec["topic"] = (rec.get("topic") or primary_topic).strip()
    rec["subtopic"] = (rec.get("subtopic") or None)
    try:
        rec["class_level"] = int(rec.get("class_level") or grade)
    except Exception:
        rec["class_level"] = grade
    try:
        dl = int(rec.get("difficulty_level") or 3)
    except Exception:
        dl = 3
    rec["difficulty_level"] = max(1, min(7, dl))
    rec["correct_answer"] = _collapse_bs(rec.get("correct_answer") or rec.get("answer") or None)
    if any(not rec.get(k) for k in REQUIRED_FIELDS):
        return None
    return rec


INSERT_COLS = ["class_level", "difficulty_level", "topic", "subtopic",
               "task_text", "solution", "criteria_1_point",
               "criteria_2_points", "correct_answer", "is_flagged",
               "reports_count", "attempts_count", "solves_count",
               "needs_reclassification", "created_at"]


def insert_task(cur: sqlite3.Cursor, rec: dict, existing_texts: set[str]) -> bool:
    text = rec["task_text"]
    if text in existing_texts:
        return False
    existing_texts.add(text)
    now = _dt.datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    placeholders = ", ".join(["?"] * len(INSERT_COLS))
    cur.execute(
        f"INSERT INTO adaptive_tasks ({', '.join(INSERT_COLS)}) VALUES ({placeholders})",
        (
            rec["class_level"], rec["difficulty_level"], rec["topic"], rec.get("subtopic"),
            text, rec["solution"], rec["criteria_1_point"], rec["criteria_2_points"],
            rec.get("correct_answer"), 0, 0, 0, 0, 0, now,
        ),
    )
    return True


def process_combo(client: DeepSeekClient, conn: sqlite3.Connection,
                  grade: int, topic_ui: str, target: int, batch_size: int,
                  max_batches: int, dry_run: bool, existing_texts: set[str]) -> int:
    cur = conn.cursor()
    have = fetch_count(cur, grade, topic_ui)
    need = max(0, target - have)
    if need == 0:
        print(f"  [skip] grade={grade} {topic_ui}: уже {have} (>= {target})")
        return 0

    examples = fetch_examples(cur, grade, topic_ui, limit=4)
    if not examples:
        for nearby in sorted(GRADES, key=lambda x: abs(x - grade)):
            if nearby == grade:
                continue
            ex = fetch_examples(cur, nearby, topic_ui, limit=4)
            if ex:
                examples = ex
                print(f"     [info] no examples for grade {grade}; "
                      f"borrowed {len(examples)} from grade {nearby}")
                break
    db_topics = existing_topics(cur, grade, topic_ui)[:5]
    dist = difficulty_distribution(cur, grade, topic_ui)
    primary_topic = db_topics[0] if db_topics else f"{UI_TOPIC_NAMES_RU.get(topic_ui, topic_ui)} ({grade} класс)"

    print(f"\n  >> grade={grade} {topic_ui}: have={have}, need={need}, "
          f"primary_topic=\"{primary_topic}\", examples={len(examples)}")

    ts = _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(OUT_DIR, f"g{grade}_{topic_ui}_{ts}.jsonl")
    inserted_total = 0

    for batch_idx in range(max_batches):
        if inserted_total >= need:
            break
        bs = min(batch_size, need - inserted_total)
        prompt = build_prompt(grade, topic_ui, examples, db_topics, dist, bs)
        if dry_run:
            print(f"     [dry-run] would request batch {batch_idx + 1}, size={bs}")
            return 0

        try:
            raw = client.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.6,
                max_tokens=4096,
            )
        except DeepSeekAPIError as e:
            print(f"     [api-error] {e}")
            time.sleep(5)
            continue

        try:
            recs = parse_json_array(raw)
        except Exception as e:
            print(f"     [parse-error] {e}; saved raw to errors log")
            with open(os.path.join(OUT_DIR, "_parse_errors.log"), "a", encoding="utf-8") as fp:
                fp.write(f"\n--- {ts} grade={grade} topic={topic_ui} batch={batch_idx + 1} ---\n")
                fp.write(raw[:6000] + "\n")
            continue

        kept = 0
        with open(out_path, "a", encoding="utf-8") as fp:
            for r in recs:
                norm = normalize(r, grade, primary_topic)
                if not norm:
                    continue
                if insert_task(cur, norm, existing_texts):
                    fp.write(json.dumps(norm, ensure_ascii=False) + "\n")
                    kept += 1
                    inserted_total += 1
                    if inserted_total >= need:
                        break
        conn.commit()
        print(f"     batch {batch_idx + 1}: model returned {len(recs)}, "
              f"kept & inserted {kept}, total {inserted_total}/{need}")

    print(f"  << grade={grade} {topic_ui}: inserted {inserted_total} → "
          f"now {fetch_count(cur, grade, topic_ui)}; file: {out_path}")
    return inserted_total


def fetch_count_by_level(cur: sqlite3.Cursor, grade: int, topic_ui: str, level: int) -> int:
    kws = [k.lower() for k in keywords_for(grade, topic_ui)]
    rows = cur.execute(
        "SELECT topic FROM adaptive_tasks WHERE class_level=? AND difficulty_level=? AND is_flagged=0",
        (grade, level),
    ).fetchall()
    if not kws:
        return len(rows)
    return sum(1 for (t,) in rows if t and any(k in t.lower() for k in kws))


def fetch_examples_by_level(cur: sqlite3.Cursor, grade: int, topic_ui: str,
                            level: int, limit: int = 3) -> list[dict]:
    kws = [k.lower() for k in keywords_for(grade, topic_ui)]
    rows = cur.execute(
        """SELECT class_level, difficulty_level, topic, subtopic, task_text,
                  solution, criteria_1_point, criteria_2_points, correct_answer
           FROM adaptive_tasks
           WHERE class_level=? AND difficulty_level=? AND is_flagged=0""",
        (grade, level),
    ).fetchall()
    cols = ["class_level", "difficulty_level", "topic", "subtopic",
            "task_text", "solution", "criteria_1_point",
            "criteria_2_points", "correct_answer"]
    matches = []
    for r in rows:
        d = dict(zip(cols, r))
        if not d.get("topic"):
            continue
        if not kws or any(k in d["topic"].lower() for k in kws):
            matches.append(d)
    random.shuffle(matches)
    return matches[:limit]


def process_cell(client: DeepSeekClient, conn: sqlite3.Connection,
                 grade: int, topic_ui: str, level: int, target: int,
                 batch_size: int, max_batches: int, dry_run: bool,
                 existing_texts: set[str]) -> int:
    """Generate tasks for a single (grade, topic, level) cell up to target."""
    cur = conn.cursor()
    have = fetch_count_by_level(cur, grade, topic_ui, level)
    need = max(0, target - have)
    if need == 0:
        return 0

    examples = fetch_examples_by_level(cur, grade, topic_ui, level, limit=3)
    # if no level-specific examples — borrow from same combo, any level
    if not examples:
        examples = fetch_examples(cur, grade, topic_ui, limit=3)
    # still nothing — borrow from neighbouring grade
    if not examples:
        for nearby in sorted(GRADES, key=lambda x: abs(x - grade)):
            if nearby == grade:
                continue
            ex = fetch_examples_by_level(cur, nearby, topic_ui, level, limit=3) \
                 or fetch_examples(cur, nearby, topic_ui, limit=3)
            if ex:
                examples = ex
                break
    db_topics = existing_topics(cur, grade, topic_ui)[:5]
    primary_topic = db_topics[0] if db_topics else f"{UI_TOPIC_NAMES_RU.get(topic_ui, topic_ui)} ({grade} класс)"

    print(f"\n  >> g{grade} {topic_ui} L{level}: have={have}, need={need}, "
          f"primary=\"{primary_topic[:40]}\", examples={len(examples)}")

    ts = _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(OUT_DIR, f"g{grade}_{topic_ui}_L{level}_{ts}.jsonl")
    inserted_total = 0

    for batch_idx in range(max_batches):
        if inserted_total >= need:
            break
        bs = min(batch_size, need - inserted_total)
        prompt = build_prompt(grade, topic_ui, examples, db_topics, {},
                              bs, target_level=level)
        if dry_run:
            print(f"     [dry-run] would request batch {batch_idx + 1}, size={bs}")
            return 0

        try:
            raw = client.generate(
                prompt=prompt, system_prompt=SYSTEM_PROMPT,
                temperature=0.65, max_tokens=4096,
            )
        except DeepSeekAPIError as e:
            print(f"     [api-error] {e}")
            time.sleep(5); continue

        try:
            recs = parse_json_array(raw)
        except Exception as e:
            print(f"     [parse-error] {e}")
            with open(os.path.join(OUT_DIR, "_parse_errors.log"), "a", encoding="utf-8") as fp:
                fp.write(f"\n--- {ts} grade={grade} topic={topic_ui} level={level} batch={batch_idx + 1} ---\n")
                fp.write(raw[:6000] + "\n")
            continue

        kept = 0
        with open(out_path, "a", encoding="utf-8") as fp:
            for r in recs:
                norm = normalize(r, grade, primary_topic)
                if not norm:
                    continue
                # force the requested level (model often drifts)
                norm["difficulty_level"] = level
                if insert_task(cur, norm, existing_texts):
                    fp.write(json.dumps(norm, ensure_ascii=False) + "\n")
                    kept += 1
                    inserted_total += 1
                    if inserted_total >= need:
                        break
        conn.commit()
        print(f"     batch {batch_idx + 1}: model={len(recs)}, kept={kept}, "
              f"total {inserted_total}/{need}")

    print(f"  << g{grade} {topic_ui} L{level}: +{inserted_total} → "
          f"now {fetch_count_by_level(cur, grade, topic_ui, level)}")
    return inserted_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--target", type=int, default=12,
                    help="(legacy mode) желаемое количество задач в комбо (без учёта уровня)")
    ap.add_argument("--per-level", type=int, default=None,
                    help="если задано — режим по сетке (grade × topic × level), "
                         "цель N задач на КАЖДЫЙ уровень 1..7")
    ap.add_argument("--levels", nargs="+", type=int, default=[1,2,3,4,5,6,7],
                    help="какие уровни обрабатывать в режиме --per-level")
    ap.add_argument("--min-count", type=int, default=10,
                    help="(legacy) комбо считается недозалитым если задач < min-count")
    ap.add_argument("--batch-size", type=int, default=5)
    ap.add_argument("--max-batches", type=int, default=8)
    ap.add_argument("--grades", nargs="+", type=int, default=GRADES)
    ap.add_argument("--topics", nargs="+", default=UI_TOPICS)
    ap.add_argument("--only", nargs="+", help="алиас для --topics")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.only:
        args.topics = args.only

    if not os.path.exists(args.db):
        print(f"DB not found: {args.db}")
        sys.exit(2)

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    cur.execute("SELECT task_text FROM adaptive_tasks")
    existing_texts = {row[0] for row in cur.fetchall()}
    print(f"DB ready. Existing tasks: {len(existing_texts)}")

    # ------------- per-level mode (full grid) -------------
    if args.per_level is not None:
        target = args.per_level
        plan = []
        print(f"\n=== План (per-level, target={target}) ===")
        total_need = 0
        for g in args.grades:
            for t in args.topics:
                for l in args.levels:
                    have = fetch_count_by_level(cur, g, t, l)
                    need = max(0, target - have)
                    if need:
                        plan.append((g, t, l, have, need))
                        total_need += need
        if not plan:
            print("  Все ячейки заполнены — генерация не нужна.")
            return
        # sort: largest deficit first → видимый прогресс быстрее
        plan.sort(key=lambda x: -x[4])
        print(f"  Ячеек к заполнению: {len(plan)}; задач к генерации: {total_need}")
        for g, t, l, have, need in plan[:30]:
            print(f"  g{g} {t} L{l}: have={have}, need={need}")
        if len(plan) > 30:
            print(f"  ... и ещё {len(plan) - 30} ячеек")
        if args.dry_run:
            print("\n[dry-run] выходим без вызовов API.")
            return

        client = DeepSeekClient()
        total_inserted = 0
        for g, t, l, _, _ in plan:
            try:
                n = process_cell(client, conn, g, t, l,
                                 target=target,
                                 batch_size=args.batch_size,
                                 max_batches=args.max_batches,
                                 dry_run=False,
                                 existing_texts=existing_texts)
                total_inserted += n
            except KeyboardInterrupt:
                print("\nПрервано (Ctrl+C). Прогресс сохранён.")
                break
            except Exception as e:
                print(f"  [cell-error] g{g} {t} L{l}: {e}")
                continue
        print(f"\n=== Итого вставлено: {total_inserted} ===")
        return

    # ------------- legacy combo mode -------------
    plan = []
    print("\n=== План ===")
    for g in args.grades:
        for t in args.topics:
            have = fetch_count(cur, g, t)
            if have < args.min_count:
                plan.append((g, t, have))
                print(f"  grade {g} {t}: have={have}, need up to {args.target - have}")
    if not plan:
        print("  Все комбинации заполнены, генерация не нужна.")
        return

    if args.dry_run:
        print("\n[dry-run] выходим без вызовов API.")
        return

    client = DeepSeekClient()
    total_inserted = 0
    for g, t, _ in plan:
        try:
            n = process_combo(client, conn, g, t,
                              target=args.target,
                              batch_size=args.batch_size,
                              max_batches=args.max_batches,
                              dry_run=False,
                              existing_texts=existing_texts)
            total_inserted += n
        except KeyboardInterrupt:
            print("\nПрервано пользователем (Ctrl+C). Промежуточные данные сохранены.")
            break
        except Exception as e:
            print(f"  [combo-error] grade={g} topic={t}: {e}")
            continue

    print(f"\n=== Итого вставлено: {total_inserted} ===")


if __name__ == "__main__":
    main()
