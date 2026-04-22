#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор олимпиадных задач для 6 класса (STRICT MODE v3)
Создает 1050 задач: 10 тем x 7 уровней x 15 задач
Выходной файл: grade6_olympiad_RAW.jsonl

ИСПРАВЛЕНИЯ v3:
- Bulletproof JSON парсер с полным списком LaTeX escape sequences
- Продолжение с места остановки (resume mode)
- Улучшенный промпт без проблемных LaTeX команд в JSON
"""

import json
import os
import sys
import time
import re
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
import requests
from topics_grade6 import GRADE_6_TOPICS, DIFFICULTY_LEVELS, TASKS_PER_CELL

# Настройка кодировки для Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
API_URL = "https://api.deepseek.com/v1/chat/completions"
OUTPUT_FILE = "grade6_olympiad_RAW.jsonl"

# Статистика
fallback_count = 0
total_generated = 0


def fix_latex_escapes(text: str) -> str:
    """
    Исправляет все LaTeX escape sequences в JSON строке.
    Заменяет одинарные обратные слеши на двойные для всех LaTeX команд.
    """
    # Полный список LaTeX команд, которые нужно экранировать
    latex_commands = [
        'overline', 'underline', 'overrightarrow', 'overleftarrow',
        'sqrt', 'frac', 'dfrac', 'tfrac', 'cfrac',
        'sum', 'prod', 'int', 'oint', 'iint',
        'lim', 'max', 'min', 'sup', 'inf',
        'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'varepsilon',
        'zeta', 'eta', 'theta', 'vartheta', 'iota', 'kappa',
        'lambda', 'mu', 'nu', 'xi', 'pi', 'varpi',
        'rho', 'varrho', 'sigma', 'varsigma', 'tau', 'upsilon',
        'phi', 'varphi', 'chi', 'psi', 'omega',
        'Gamma', 'Delta', 'Theta', 'Lambda', 'Xi', 'Pi',
        'Sigma', 'Upsilon', 'Phi', 'Psi', 'Omega',
        'geq', 'leq', 'neq', 'approx', 'equiv', 'sim',
        'cdot', 'times', 'div', 'pm', 'mp',
        'infty', 'partial', 'nabla', 'forall', 'exists',
        'in', 'notin', 'subset', 'supset', 'subseteq', 'supseteq',
        'cup', 'cap', 'setminus', 'emptyset',
        'rightarrow', 'leftarrow', 'Rightarrow', 'Leftarrow',
        'leftrightarrow', 'Leftrightarrow',
        'pmod', 'bmod', 'mod',
        'text', 'mathrm', 'mathbf', 'mathit', 'mathbb', 'mathcal',
        'left', 'right', 'big', 'Big', 'bigg', 'Bigg',
        'ldots', 'cdots', 'vdots', 'ddots',
        'begin', 'end', 'quad', 'qquad',
        'hline', 'vline', 'cline',
        'le', 'ge', 'ne', 'to', 'gets',
        'land', 'lor', 'lnot', 'neg',
        'lceil', 'rceil', 'lfloor', 'rfloor',
        'langle', 'rangle',
        'hat', 'tilde', 'bar', 'vec', 'dot', 'ddot',
        'widehat', 'widetilde', 'overbrace', 'underbrace',
        'not', 'mid', 'nmid',
        'binom', 'tbinom', 'dbinom',
        'gcd', 'lcm',
    ]
    
    # Заменяем одинарные слеши на двойные для всех LaTeX команд
    for cmd in latex_commands:
        # Заменяем \cmd на \\cmd (только если уже не \\cmd)
        text = re.sub(r'(?<!\\)\\(' + cmd + r')(?![a-zA-Z])', r'\\\\\1', text)
    
    # Также исправляем \( \) \[ \]
    text = re.sub(r'(?<!\\)\\([\(\)\[\]])', r'\\\\\1', text)
    
    return text


def extract_json_bulletproof(raw_response: str) -> Dict[str, Any]:
    """
    Bulletproof JSON парсер с множеством fallback стратегий.
    """
    global fallback_count
    
    # Шаг 1: Снятие markdown обертки
    cleaned = raw_response.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'\s*```\s*$', '', cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()
    
    # Стратегия 1: Прямой парсинг
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Стратегия 2: Фикс LaTeX escape sequences
    try:
        fixed = fix_latex_escapes(cleaned)
        result = json.loads(fixed)
        fallback_count += 1
        return result
    except json.JSONDecodeError:
        pass
    
    # Стратегия 3: Агрессивный фикс - заменяем все одинарные слеши на двойные
    try:
        # Находим JSON блок
        json_match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if json_match:
            json_str = json_match.group()
            # Заменяем все одинарные \ на \\ (кроме уже двойных)
            fixed = re.sub(r'(?<!\\)\\(?!\\)', r'\\\\', json_str)
            result = json.loads(fixed)
            fallback_count += 1
            return result
    except (json.JSONDecodeError, Exception):
        pass
    
    # Стратегия 4: Извлечение полей через regex
    try:
        question_match = re.search(r'"question"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,', cleaned, re.DOTALL)
        answer_match = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned, re.DOTALL)
        explanation_match = re.search(r'"explanation"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]', cleaned, re.DOTALL)
        
        if question_match and answer_match and explanation_match:
            fallback_count += 1
            return {
                "question": question_match.group(1),
                "answer": answer_match.group(1),
                "explanation": explanation_match.group(1)
            }
    except Exception:
        pass
    
    raise Exception(f"All JSON parsing strategies failed. Response: {raw_response[:300]}")


def get_system_prompt(topic: Dict[str, Any], level: int) -> str:
    """
    Формирует промпт v3 - без проблемных LaTeX команд в JSON.
    Просим модель использовать простые обозначения.
    """
    topic_name = topic['name']
    topic_desc = topic['description']
    keywords = ', '.join(topic['keywords'])
    
    return f"""Ты — составитель олимпиадных задач для 6 класса.
Придумай ОДНУ оригинальную задачу.

ТЕМА: {topic_name}
ОПИСАНИЕ: {topic_desc}
КЛЮЧЕВЫЕ СЛОВА: {keywords}
СЛОЖНОСТЬ: {level} из 7

ШКАЛА СЛОЖНОСТИ:
1 - Базовая, 2 - Школьный этап ВсОШ, 3 - Муниципальный этап,
4 - Сложный муниципальный, 5 - МГУ Математический праздник,
6 - Региональный Эйлер, 7 - Заключительный ВсОШ

КРИТИЧЕСКИ ВАЖНО ДЛЯ JSON:
- Используй ТОЛЬКО $...$ для inline формул (одинарные доллары)
- Используй ТОЛЬКО $$...$$ для display формул (двойные доллары)
- НЕ используй обратные слеши вне LaTeX формул
- Для трёхзначного числа abc пиши: $\\overline{{abc}}$ (двойной слеш!)
- Для дроби: $\\frac{{a}}{{b}}$ (двойной слеш!)
- Для корня: $\\sqrt{{x}}$ (двойной слеш!)
- Все LaTeX команды внутри $ $ должны иметь ДВОЙНОЙ обратный слеш: \\\\overline, \\\\frac, \\\\sqrt

ФОРМАТ ОТВЕТА (строго JSON, без markdown):
{{
  "question": "Текст задачи с формулами в $...$",
  "answer": "Краткий ответ без слова Ответ:",
  "explanation": "Пошаговое решение"
}}

ВАЖНО: Задача должна быть логически корректной и иметь однозначный ответ."""


def call_llm(system_prompt: str, max_retries: int = 3) -> Dict[str, str]:
    """
    Вызывает LLM API с bulletproof парсером.
    """
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Сгенерируй задачу. Верни только JSON."}
        ],
        "temperature": 0.9,
        "max_tokens": 2000
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=90)
            response.raise_for_status()
            
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            
            task_json = extract_json_bulletproof(content)
            
            if not all(key in task_json for key in ["question", "answer", "explanation"]):
                raise ValueError("Missing required fields")
            
            if not task_json["question"] or not task_json["answer"]:
                raise ValueError("Empty fields")
            
            # Очистка ответа от "Ответ:"
            answer = task_json["answer"]
            for prefix in ["Ответ:", "Ответ —", "ответ:", "Answer:"]:
                if answer.lower().startswith(prefix.lower()):
                    answer = answer[len(prefix):].strip()
            task_json["answer"] = answer
            
            return task_json
            
        except Exception as e:
            print(f"  [WARN] Попытка {attempt + 1}/{max_retries}: {str(e)[:100]}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise Exception(f"Failed after {max_retries} attempts: {e}")


def load_existing_tasks() -> set:
    """
    Загружает уже сгенерированные задачи для resume mode.
    Возвращает set из (topic, level, task_number).
    """
    existing = set()
    if not os.path.exists(OUTPUT_FILE):
        return existing
    
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                task = json.loads(line)
                key = (task['topic'], task['level'], task['task_number'])
                existing.add(key)
            except:
                pass
    
    return existing


def save_task_to_jsonl(task: Dict[str, Any]):
    """Добавляет задачу в JSONL файл."""
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False)
        f.write("\n")


def generate_all_tasks():
    """Генерирует все 1050 задач с поддержкой resume."""
    global fallback_count, total_generated
    
    total_tasks = len(GRADE_6_TOPICS) * len(DIFFICULTY_LEVELS) * TASKS_PER_CELL
    
    # Загружаем уже сгенерированные задачи
    existing = load_existing_tasks()
    already_done = len(existing)
    
    print(f"\n{'='*80}")
    print(f">>> ГЕНЕРАЦИЯ ЗАДАЧ ДЛЯ 6 КЛАССА (v3 - Bulletproof Parser)")
    print(f"{'='*80}")
    print(f"[*] Всего задач: {total_tasks}")
    print(f"[*] Уже сгенерировано: {already_done}")
    print(f"[*] Осталось: {total_tasks - already_done}")
    print(f"[*] Файл: {OUTPUT_FILE}")
    print(f"{'='*80}\n")
    
    start_time = time.time()
    successful_tasks = already_done
    failed_tasks = 0
    current_task = 0
    
    for topic_idx, topic in enumerate(GRADE_6_TOPICS, 1):
        print(f"\n{'-'*80}")
        print(f"[ТЕМА {topic_idx}/{len(GRADE_6_TOPICS)}] {topic['name']}")
        print(f"{'-'*80}")
        
        for level in DIFFICULTY_LEVELS:
            print(f"\n  [Уровень {level}/7]:")
            
            for task_num in range(1, TASKS_PER_CELL + 1):
                current_task += 1
                
                # Пропускаем уже сгенерированные
                key = (topic['name'], level, task_num)
                if key in existing:
                    continue
                
                try:
                    system_prompt = get_system_prompt(topic, level)
                    ai_response = call_llm(system_prompt)
                    
                    task_data = {
                        "grade": 6,
                        "topic": topic['name'],
                        "level": level,
                        "task_number": task_num,
                        "question": ai_response["question"],
                        "answer": ai_response["answer"],
                        "explanation": ai_response["explanation"],
                        "keywords": topic['keywords']
                    }
                    
                    save_task_to_jsonl(task_data)
                    successful_tasks += 1
                    total_generated += 1
                    
                    elapsed = time.time() - start_time
                    done = successful_tasks - already_done
                    remaining = total_tasks - successful_tasks
                    avg = elapsed / max(done, 1)
                    eta = avg * remaining
                    
                    print(f"  [OK] {successful_tasks}/{total_tasks} ({successful_tasks/total_tasks*100:.1f}%) | "
                          f"ETA: {eta/60:.0f}мин | Fallback: {fallback_count}")
                    
                    time.sleep(1.0)
                    
                except Exception as e:
                    failed_tasks += 1
                    print(f"  [ERR] Тема={topic['name']}, Ур={level}, №{task_num}: {str(e)[:80]}")
                    continue
    
    total_time = time.time() - start_time
    
    print(f"\n{'='*80}")
    print(f">>> ГЕНЕРАЦИЯ ЗАВЕРШЕНА!")
    print(f"[OK] Успешно: {successful_tasks}/{total_tasks}")
    print(f"[FAIL] Ошибок: {failed_tasks}")
    print(f"[FALLBACK] Regex-фиксов: {fallback_count}")
    print(f"[TIME] Время: {total_time/60:.1f} мин")
    print(f"{'='*80}\n")


def main():
    if not API_KEY:
        print("[ERROR] DEEPSEEK_API_KEY не найден!")
        return
    
    try:
        generate_all_tasks()
        print("[DONE] Генерация завершена!")
    except KeyboardInterrupt:
        print(f"\n[STOP] Прервано. Сгенерировано: {total_generated}, Fallback: {fallback_count}")
    except Exception as e:
        print(f"\n[CRITICAL] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
