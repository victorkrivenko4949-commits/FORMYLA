#!/usr/bin/env python3
"""Write the fixed gen_solutions.py to Downloads."""
import os, json

CONTENT = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генерация решений для олимпиадных задач через DeepSeek с двойным проходом:
  генератор -> аудитор -> (при необходимости) регенерация.
  Поддерживает checkpointing, обработку битых JSON от DeepSeek и продолжение прерванных прогонов.

Fixes applied:
  1. _escape_control_chars_in_strings() — экранирует управляющие символы (\n, \t) внутри JSON-строк
  2. _sanitize_json_content() — расширена: control-char -> backslash fix -> brute force
  3. sys.stdout переключён на utf-8 для предотвращения UnicodeEncodeError на Windows
"""
import os, sys, json, time, requests, io, re

DEEPSEEK_KEY = os.environ["DEEPSEEK_API_KEY"]
API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"   # самый дешёвый; для сложных можно deepseek-reasoner

_IN_DIR = os.path.dirname(os.path.abspath(__file__))
IN_FILE   = os.path.join(_IN_DIR, "tasks_need_solutions.json")
DB_PATH   = os.path.join(_IN_DIR, "tasks_solutions_out.json")
LOG_OK    = os.path.join(_IN_DIR, "solutions_log.jsonl")
LOG_BROKEN= os.path.join(_IN_DIR, "solutions_broken.jsonl")
LOG_FAIL  = os.path.join(_IN_DIR, "solutions_fail.jsonl")
CHECKPOINT_INTERVAL = 20

# ---------- SANITIZE DeepSeek JSON ----------

def _escape_control_chars_in_strings(text):
    """
    Экранирует управляющие символы (< 0x20), которые находятся ВНУТРИ JSON-строк.
    DeepSeek иногда возвращает JSON с реальными символами новой строки (0x0A)
    внутри строковых значений, что вызывает "Invalid control character" при парсинге.
    """
    result = []
    in_string = False
    escape = False
    for ch in text:
        if escape:
            result.append(ch)
            escape = False
            continue
        if ch == '\\':
            result.append(ch)
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string and ord(ch) < 0x20:
            if ch == '\n':
                result.append('\\n')
            elif ch == '\t':
                result.append('\\t')
            elif ch == '\r':
                result.append('\\r')
            else:
                result.append('\\u{:04x}'.format(ord(ch)))
        else:
            result.append(ch)
    return ''.join(result)


def _sanitize_json_content(content):
    """
    Пытается распарсить content как JSON.
    DeepSeek иногда возвращает JSON с двумя проблемами:
      1. Управляющие символы (\n, \t) внутри строковых значений
      2. Неэкранированные LaTeX-обратные слэши: \( x^2 \) вместо \\\\( x^2 \\\)
    Валидный JSON требует \\\\( и \\\[.
    При ошибке парсинга применяет многоступенчатую обработку.
    """
    # Шаг 0: Сначала пробуем как есть
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Шаг 1: Экранируем управляющие символы внутри JSON-строк
    step1 = _escape_control_chars_in_strings(content)
    try:
        return json.loads(step1)
    except json.JSONDecodeError:
        pass

    # Шаг 2: Экранируем управляющие символы + фиксим неэкранированные LaTeX-слэши
    step2 = re.sub(
        r'\\(?![\\"/bfnrtu]|u[0-9a-fA-F]{4})',
        r'\\\\',
        step1
    )
    try:
        return json.loads(step2)
    except json.JSONDecodeError:
        pass

    # Шаг 3: Brute force - экранируем ВСЕ обратные слэши (после control-char escape)
    step3 = step1.replace('\\', '\\\\')
    try:
