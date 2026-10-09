#!/usr/bin/env python3
"""Helper script to write regenerate.py with the complete fixed content."""

import os, sys

content = '''#!/usr/bin/env python3
"""
regenerate.py -- Перегенерация 311 завышенных задач через DeepSeek API.

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
DB_PATH = r"C:\\Users\\Victor\\Downloads\\final_db_1_5.json"
BACKUP_PATH = r"C:\\Users\\Victor\\Downloads\\final_db_1_5_backup.json"
OUT_LOG = os.path.join(BASE_DIR, "regenerate_log.jsonl")

LEVEL_DESC = {
    1: "лёгкая школьная: одно действие, устный счёт",
    2: "школьная: 1-2 стандартных шага, знакомый шаблон",
    3: "школьный этап олимпиады: нужна идея, 2-3 шага, немного разбора случаев",
    4: "муниципальный этап: нетривиальная идея, комбинация методов, оценка+пример",
    5: "сложный муниципальный: несколько идей, доказательство, инвариант/крайнее, трудная конструкция",
}
'''

sys.stdout.write("Part 1 done")
if True:
    print("ok")
