#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ГЕНЕРАЦИЯ олимпиадных задач уровней 6-7-8.
Цель: 1000 задач. Автономно, без вопросов к пользователю.

Полная переработка после двух неудачных прогонов (~6 часов, 0 принятых задач).

Ключевые изменения (v4):
1. ДВА дополнительных этапа усложнения задачи после генерации:
   - Этап A: модель составляет план усложнения (как сделать задачу заметно сложнее)
   - Этап B: на основе плана генерируется улучшенная (более сложная) версия задачи
2. safe_int() — защита от краха при парсинге значений вроде "7-9".
3. Аудит уровня теперь принимает difficulty_level генератора как основу,
   не занижая его без веских оснований.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'replace')

# ─── logging ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('gen_678')

# ─── deepseek client (inline, чтобы не зависеть от ai/deepseek_client.py) ──
import requests

class DeepSeekAPIError(Exception):
    pass

class DeepSeekClient:
    """Минимальный клиент deepseek-reasoner с ретраями."""

    API_URL = "https://api.deepseek.com/v1/chat/completions"
    MODEL = "deepseek-reasoner"

    def __init__(self):
        self.api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not self.api_key:
            # fallback: пробуем .env
            env_path = ".env"
            if os.path.exists(env_path):
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("DEEPSEEK_API_KEY="):
                            self.api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                            break
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY не найден ни в .env ни в переменных окружения")

    def generate_with_reasoning(self, prompt: str, system_prompt: str = "",
                                max_tokens: int = 8192, timeout: int = 300) -> str:
        """Вызов deepseek-reasoner с ретраями."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = ""
        max_retries = 6  # увеличенное число ретраев
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = data.get('choices', [{}])[0].get('message', {}).get('content', '')
                    if content:
                        return content
                    else:
                        # пустой content — типичная проблема deepseek-reasoner
                        reasoning = data.get('choices', [{}])[0].get('message', {}).get('reasoning_content', '')[:200]
                        last_error = f"empty content field (reasoning: {reasoning})"
                        logger.warning(f"[retry {attempt}/{max_retries}] {last_error}")
                elif resp.status_code == 402:
                    last_error = f"402 Payment Required: {resp.text[:200]}"
                    logger.error(f"[retry {attempt}/{max_retries}] {last_error}")
                    # Не ретраим 402 — это конец кредитов
                    raise DeepSeekAPIError(last_error)
                elif resp.status_code == 429:
                    last_error = f"429 Rate Limited: {resp.text[:200]}"
                    logger.warning(f"[retry {attempt}/{max_retries}] {last_error}")
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    logger.warning(f"[retry {attempt}/{max_retries}] {last_error}")
            except requests.exceptions.Timeout:
                last_error = "timeout"
                logger.warning(f"[retry {attempt}/{max_retries}] timeout")
            except requests.exceptions.ConnectionError as e:
                last_error = f"connection error: {e}"
                logger.warning(f"[retry {attempt}/{max_retries}] {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"[retry {attempt}/{max_retries}] {e}")

            if attempt < max_retries:
                sleep_time = min(2 ** attempt, 30)
                time.sleep(sleep_time)

        raise DeepSeekAPIError(f"Все {max_retries} попыток не удались: {last_error}")

    def call(self, prompt: str, system_prompt: str = "",
             max_tokens: int = 8192, timeout: int = 300) -> str:
        return self.generate_with_reasoning(prompt, system_prompt, max_tokens, timeout)

    async def a_call(self, prompt: str, system_prompt: str = "",
                     max_tokens: int = 8192, timeout: int = 300) -> str:
        """Async version: runs blocking call in thread pool to avoid event loop blockage."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _EXECUTOR, self.call, prompt, system_prompt, max_tokens, timeout)


# ─── File locks for thread safety ──────────────────────────────────────
FILE_LOCKS: Dict[str, threading.Lock] = {}

def _get_lock(name: str) -> threading.Lock:
    if name not in FILE_LOCKS:
        FILE_LOCKS[name] = threading.Lock()
    return FILE_LOCKS[name]

# Thread pool for concurrent API calls (120 threads = 2x max concurrent tasks)
_EXECUTOR = ThreadPoolExecutor(max_workers=120)


# ─── SEEN_TEXTS (из gen_678_seen_texts.json, загружается при старте) ──
SEEN_TEXTS: List[str] = []

def load_seen_texts(path: str = "gen_678_seen_texts.json") -> List[str]:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_seen_texts(texts: List[str], path: str = "gen_678_seen_texts.json"):
    lock = _get_lock('seen_texts')
    with lock:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(texts, f, ensure_ascii=False, indent=2)


# ─── next_id ─────────────────────────────────────────────────────────
def load_next_id(path: str = "gen_678_next_id.txt") -> int:
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return int(f.read().strip())
    return 800001

def save_next_id(nid: int, path: str = "gen_678_next_id.txt"):
    lock = _get_lock('next_id')
    with lock:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(str(nid))


# ─── safe_int ─────────────────────────────────────────────────────────
def safe_int(value: Any, default: int = 6) -> int:
    """Безопасное преобразование в int. Извлекает первое число из строки вроде '7-9'."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    # Строка — пытаемся извлечь первое число
    m = re.search(r'(\d+)', str(value).strip())
    if m:
        return int(m.group(1))
    return default


# ─── checkpoint ──────────────────────────────────────────────────────
CHECKPOINT_PATH = "gen_678_checkpoint.json"

def load_checkpoint() -> Optional[Dict[str, Any]]:
    if os.path.exists(CHECKPOINT_PATH):
        try:
            with open(CHECKPOINT_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"checkpoint load error: {e}")
    return None

def save_checkpoint(data: Dict[str, Any]):
    lock = _get_lock('checkpoint')
    with lock:
        with open(CHECKPOINT_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

def clear_checkpoint():
    lock = _get_lock('checkpoint')
    with lock:
        if os.path.exists(CHECKPOINT_PATH):
            os.remove(CHECKPOINT_PATH)


# ─── directories ─────────────────────────────────────────────────────
BASE_DIR = "gen_678"
L8_DIR = os.path.join(BASE_DIR, "L8")
L7_DIR = os.path.join(BASE_DIR, "L7")
L6_DIR = os.path.join(BASE_DIR, "L6")
RESERVE_DIR = os.path.join(BASE_DIR, "reserve")
BLACKLIST_DIR = os.path.join(BASE_DIR, "blacklist")

def ensure_dirs():
    for d in [L8_DIR, L7_DIR, L6_DIR, RESERVE_DIR, BLACKLIST_DIR]:
        os.makedirs(d, exist_ok=True)


# ─── prompts ─────────────────────────────────────────────────────────

GENERATION_SYSTEM_PROMPT = """Ты — генератор оригинальных олимпиадных задач по математике уровня 6-7-8 (по 8-балльной шкале, где 8 — самый высокий олимпиадный уровень). Твоя задача — создать НОВУЮ, ОРИГИНАЛЬНУЮ задачу, которой нет в известных олимпиадных сборниках.

ОПРЕДЕЛЕНИЯ УРОВНЕЙ (калибровка):
- Уровень 6 (L6) = региональный этап ВсОШ, задача №2. Решение содержит 3-4 шага, 2 различных математических приёма. Требует хорошего владения базовыми олимпиадными техниками.
- Уровень 7 (L7) = сложный региональный этап ВсОШ (уровень призёра/победителя региона). Решение содержит 4-5 шагов, нетривиальные замены или дополнительные построения. Требует нестандартного мышления.
- Уровень 8 (L8) = заключительный этап ВсОШ. Решение содержит 5+ идей/шагов, продвинутые техники (глубокие инварианты, нестандартные алгебраические конструкции, нетривиальная комбинаторика). Требует высокой математической культуры и изобретательности.

КРИТИЧЕСКИ ВАЖНО: ЗАПРЕЩЕНО генерировать следующие КЛАССИЧЕСКИЕ задачи (они уже известны и будут отклонены):
- Задачи на теорему Рамсея ("В стране N городов, каждые два соединены... найти одноцветный треугольник")
- Интерполяционные многочлены Лагранжа ("Многочлен степени n с целыми коэффициентами, P(0)=0, P(1)=1, ..., P(n)=n, P(n+1)=0")
- Системы вида |x|+|y|+|z| = 1, sqrt(x²+y²)+... = sqrt(2)
- Задачи вида "n⁴+2n³+3n²+2n+2025 — точный квадрат"
- |f(x)| ≤ 1 на [0,1], найти max|a|+|b| для f(x)=x³+ax+b
- "2^p-2 — точная степень" (задача о простых числах Мерсенна)
- "3^n+n^2 — полный квадрат" (классическая задача)
- Симметрия графика относительно точки и прямой: "f(0)=2, найти f(2025)"
- Системы |x|+|y|+√(x²+y²)=4, |x-y|+|x+y|=4
- Геометрия: вписанная окружность, точки касания, окружность через точки D,E,F, пересечение AX,BY,CZ
- Функциональные уравнения вида P(x)² = P(x²+2x)+2P(x)+1
- Задачи на инвариант "сумма цифр", "произведение цифр"
- Классические задачи на раскраску графа, принцип Дирихле в чистом виде
- "Квадрат суммы цифр" (A.^2 = ...)
- Задачи вида "найдите все натуральные n, при которых число ... является точным квадратом/кубом/степенью" (если это сводится к перебору)
- Диофантовы уравнения вида x² + y² = z² (пифагоровы тройки)
- Задачи про "рыцарей и лжецов" в стандартной формулировке

ТРЕБОВАНИЯ К ЗАДАЧЕ:
1. Задача должна быть ОРИГИНАЛЬНОЙ — не из известных олимпиадных сборников.
2. Сложность: уровень 6-8 (по 8-балльной шкале). Ориентируйся на определения уровней выше.
3. Подходит для классов 7-11.
4. Имеет изящное решение (не перебор, не громоздкая вычислительная работа).
5. Решение содержит 3-8 идей/шагов, каждый требует сообразительности.
6. Формулировка чёткая и строгая.
7. Чем выше уровень, тем более нестандартным должно быть условие и тем больше идей требуется для решения.

ТЕМЫ (выбери ОДНУ случайным образом, чередуй):
- Алгебра (уравнения, неравенства, системы, многочлены, функции, последовательности)
- Теория чисел (делимость, остатки, диофантовы уравнения, простые числа)
- Комбинаторика (подсчёт, графы, принцип Дирихле, инварианты, раскраски)
- Геометрия (планиметрия, окружности, площади, векторы, координаты)
- Логика и конструктивы (оценка+пример, экстремальные конструкции, полуинварианты)

ОФОРМИ ОТВЕТ СТРОГО В ВИДЕ JSON:
{
  "task_text": "Полный текст задачи на русском языке с формулами LaTeX ($$...$$ для отдельных формул, $...$ для inline)",
  "solution": "Аккуратное полное решение задачи с объяснениями (LaTeX)",
  "correct_answer": "Краткий ответ (формула, число, выражение)",
  "class_level": 7-11,
  "topic": "Одна из: Алгебра | Теория чисел | Комбинаторика | Геометрия | Логика",
  "difficulty_level": 6, 7 или 8,
  "key_method": "Ключевая идея/метод решения",
  "idea_count": число идей (3-8)
}"""

LEVEL_AUDIT_SYSTEM_PROMPT = """Ты — НЕЗАВИСИМЫЙ аудитор уровня олимпиадных задач. Твоя задача — оценить реальную сложность задачи по 8-балльной шкале (1-8), где:

ОПРЕДЕЛЕНИЯ УРОВНЕЙ (калибровка):
1-3: Школьный уровень (простая задача, 1-2 шага)
4-5: Олимпиадный уровень начальный (муниципальный этап, 2-4 шага)
6 (L6) = региональный этап ВсОШ, задача №2. Решение содержит 3-4 шага, 2 различных математических приёма.
7 (L7) = сложный региональный этап ВсОШ (уровень призёра/победителя региона). Решение содержит 4-5 шагов, нетривиальные замены или дополнительные построения.
8 (L8) = заключительный этап ВсОШ. Решение содержит 5+ идей/шагов, продвинутые техники (глубокие инварианты, нестандартные алгебраические конструкции, нетривиальная комбинаторика).

ВАЖНЫЕ ПРИНЦИПЫ КАЛИБРОВКИ:
- Задача, где нужно сделать 1 нетривиальную замену и получить функциональное уравнение → L6 (если 3-4 шага) или L7 (если 4+ шагов с нетривиальными заменами)
- Задача, где нужно применить продвинутую технику (производящие функции, heavy combinatorics, глубокие свойства чисел) → L7-L8
- Задача с 5+ идеями/шагами, включая нетривиальные наблюдения → L7-L8
- Если решение требует продвинутого функционального анализа (замены, переход к новой функции, индукция по степени) → L6-L7
- Геометрическая задача с нетривиальным дополнительным построением → L6-L7
- Комбинаторная задача на раскраску или полуинвариант с 4+ шагами → L7-L8
- Задача с 3-4 шагами и 2 приёмами → L6
- Задача с 4-5 шагами и нетривиальными идеями → L7
- Задача с 5+ шагами и продвинутыми техниками → L8

НЕ занижай уровень! Если задача требует 4+ последовательных идей для решения — это минимум L6.
Если задача не решается стандартным приёмом, а требует придумать нестандартный подход — это L7+.
Если задача содержит продвинутую комбинаторику, глубокие инварианты, нетривиальные алгебраические конструкции — ставь L8.

ОФОРМИ ОТВЕТ СТРОГО В ВИДЕ JSON:
{
  "real_level": число 1-8,
  "reasoning": "Краткое обоснование оценки (1-2 предложения)",
  "key_method": "Определённый ключевой метод решения",
  "idea_count": количество идей в решении (число)
}"""

CORRECTNESS_AUDIT_SYSTEM_PROMPT = """Ты — НЕЗАВИСИМЫЙ верификатор олимпиадных задач. Твоя задача — проверить, является ли задача корректной (имеет однозначное условие, по крайней мере одно решение, ответ не противоречит условию).

Проанализируй задачу:
1. Корректна ли формулировка (нет ли неоднозначностей, противоречий)?
2. Существует ли хотя бы одно допустимое решение?
3. Верен ли предложенный ответ?
4. Верно ли предложенное решение?

ЕСЛИ задача имеет хотя бы одно корректное решение (не обязательно как в предложенном решении) — считай её корректной.

Если предложенное решение неверно, но задача корректна — напиши ВЕРНОЕ решение и ответ сам (как независимый решатель).

ОФОРМИ ОТВЕТ СТРОГО В ВИДЕ JSON:
{
  "is_correct": true/false,
  "correct_answer": "Правильный ответ (если отличается от исходного — укажи верный)",
  "correct_solution": "Корректное решение (если нужно исправить — напиши правильное; если исходное верно — скопируй его)",
  "issues": "Описание проблемы, если задача некорректна (иначе пустая строка)"
}"""


# ─── helper functions ────────────────────────────────────────────────

def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Извлекает JSON из ответа LLM. Сначала пробует стандартный парсинг,
    затем ищет блок ```json ... ```, затем ищет { ... } в тексте."""
    text = text.strip()
    # Прямой парсинг
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Блок ```json ... ```
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Regex: ищем первый валидный объект { ... }
    brace_depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if start == -1:
                start = i
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0 and start != -1:
                candidate = text[start:i+1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = -1  # попробуем следующий объект
    return None


def normalize_text(s: str) -> str:
    """Нормализация текста для сравнения: убираем пробелы, LaTeX-нотацию, знаки препинания."""
    s = s.lower()
    s = re.sub(r'[^a-zа-яё0-9]', '', s)
    return s


def is_clone(task_text: str, seen_texts: List[str], threshold: float = 0.70) -> Tuple[bool, float]:
    """Проверка на клон: сравниваем task_text со всеми seen_texts.
    Возвращает (is_clone, max_similarity)."""
    norm = normalize_text(task_text)
    best = 0.0
    for seen in seen_texts:
        norm_seen = normalize_text(seen)
        sim = SequenceMatcher(None, norm, norm_seen).ratio()
        if sim > best:
            best = sim
    return best >= threshold, best


def generate_report(accepted: Dict[str, int], blacklisted: int, reserve: int,
                    start_time: float, correction_count: int):
    """Генерирует отчёт gen_678_report.txt."""
    elapsed = time.time() - start_time
    total = sum(accepted.values()) + blacklisted + reserve
    report = f"""Генерация задач уровней 6-7-8 — ОТЧЁТ
{'=' * 50}
Время работы: {elapsed / 60:.1f} мин = {elapsed / 3600:.2f} ч
Всего обработано: {total}
Принято L8: {accepted.get(8, 0)}
Принято L7: {accepted.get(7, 0)}
Принято L6: {accepted.get(6, 0)}
Всего принято: {sum(accepted.values())}
В резерве: {reserve}
В черном списке: {blacklisted}
Коррекций промпта: {correction_count}
Статус: {'ЗАВЕРШЕНО' if sum(accepted.values()) >= 1000 else 'НЕ ЗАВЕРШЕНО'}
"""
    with open(os.path.join(BASE_DIR, "gen_678_report.txt"), 'w', encoding='utf-8') as f:
        f.write(report)
    logger.info(f"Отчёт сохранён: gen_678/report.txt")


def save_task_json(task: Dict[str, Any], directory: str):
    """Сохраняет задачу в JSON-файл (thread-safe)."""
    path = os.path.join(directory, f"task_{task['id']}.json")
    lock = _get_lock(f'task_{task["id"]}')
    with lock:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(task, f, ensure_ascii=False, indent=2)
    return path


def log_prompt_correction(reason: str, blacklist_items: List[Dict[str, Any]]):
    """Логирует коррекцию промпта с реальными данными из blacklist."""
    path = "gen_678_prompt_correction_log.txt"
    ts = datetime.now(timezone.utc).isoformat()
    lines = [f"\n=== Prompt Correction #{ts} ==="]
    lines.append("Last 3 blacklist examples:")
    for item in blacklist_items[-3:]:
        lines.append(f"  Reason: {item.get('_status', '?')}")
        lines.append(f"  real_level={item.get('real_level', '?')}, method={item.get('key_method', '?')}")
        lines.append(f"  class_level={item.get('class_level', '?')}, topic={item.get('topic', '?')}")
        lines.append(f"  text: {item.get('task_text', 'N/A')[:200]}")
    lines.append("Prompt adjustment: increased temperature + stronger emphasis on non-trivial composition")
    lines.append("=" * 40)
    with open(path, 'a', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


# ─── prompts generation ──────────────────────────────────────────────

def build_generation_prompt(topic: str = "") -> str:
    """Формирует промпт для генерации задачи."""
    topic_instruction = ""
    if topic:
        topic_instruction = f"\n\nСОЗДАЙ ЗАДАЧУ ПО ТЕМЕ: {topic}."
    prompt = f"""Создай ОРИГИНАЛЬНУЮ олимпиадную задачу по математике уровня 6-8 (по 8-балльной шкале).{topic_instruction}

КРИТИЧЕСКИ ВАЖНО: задача ДОЛЖНА БЫТЬ ОРИГИНАЛЬНОЙ. Не копируй известные задачи из сборников! Ниже приведён список ЗАПРЕЩЁННЫХ типов задач — если ты создашь похожую, она будет ОТКЛОНЕНА.

ЗАПРЕЩЁННЫЕ ТИПЫ ЗАДАЧ:
1. Теорема Рамсея: "В стране N городов, каждые два соединены... найти одноцветный треугольник"
2. Интерполяция Лагранжа: "Многочлен степени n, P(0)=0, P(1)=1, ..., P(n)=n, P(n+1)=0"
3. Системы с модулями и корнями вида |x|+|y|+|z|=1, sqrt(x²+y²)+... = sqrt(2)
4. "n⁴+2n³+3n²+2n+2025 — точный квадрат" и подобные задачи на полный квадрат
5. Оценки для |f(x)|≤1, f(x)=x³+ax+b, найти max|a|+|b|
6. "2^p-2 — точная степень" (задача о числах Мерсенна)
7. "3^n+n^2 — полный квадрат"
8. Симметрия графика: "график симметричен относительно точки (1,0) и прямой x=3, f(0)=2, найти f(2025)"
9. Системы |x|+|y|+√(x²+y²)=4, |x-y|+|x+y|=4
10. Геометрия: вписанная окружность, точки касания, окружность через точки D,E,F, пересечение AX,BY,CZ
11. Функциональное уравнение P(x)² = P(x²+2x)+2P(x)+1
12. Задачи на "сумму цифр" и "произведение цифр" в чистом виде
13. Классические задачи на раскраску графа (в лоб)
14. "Квадрат суммы цифр" (A² = ...)
15. "Найдите все n, при которых число ... является точным квадратом" (сводится к перебору)
16. Диофантовы x²+y²=z²
17. "Рыцари и лжецы" в стандартной формулировке
18. Задачи на инвариант "сумма/произведение чисел на доске" в чистом виде
19. Задачи про "шары в урне" и классическую вероятность
20. Задачи на среднее арифметическое/геометрическое в лоб

ТРЕБОВАНИЯ К НОВОЙ ЗАДАЧЕ:
1. ОРИГИНАЛЬНАЯ — придумай НОВУЮ конструкцию или необычную комбинацию идей.
2. Уровень: 6-8. Смотри определения уровней в system prompt (L6=регион задача №2, L7=сложный регион, L8=заключительный этап ВсОШ). Должна быть нетривиальной, с 3-8 идеями в решении.
3. Для классов 7-11.
4. Изящное решение, не перебор.
5. Чёткая формулировка.

ПРИДУМАЙ НЕЧТО НОВОЕ. Комбинируй темы, создавай необычные условия, используй редкие приёмы.

ОТВЕТ ДАЙ В ВИДЕ JSON:
{{
  "task_text": "Текст задачи с LaTeX ($$...$$ для формул)",
  "solution": "Полное решение с объяснениями (LaTeX, не менее 500 символов)",
  "correct_answer": "Краткий ответ",
  "class_level": 7-11,
  "topic": "Алгебра | Теория чисел | Комбинаторика | Геометрия | Логика",
  "difficulty_level": 6, 7 или 8,
  "key_method": "Ключевая идея",
  "idea_count": число (3-8)
}}"""
    return prompt


def build_level_audit_prompt(task_text: str, solution: str, difficulty_level: int) -> str:
    prompt = f"""Оцени РЕАЛЬНЫЙ уровень сложности задачи по 8-балльной шкале (1-8).

ОПРЕДЕЛЕНИЯ УРОВНЕЙ:
- L6 = региональный этап ВсОШ, задача №2 (3-4 шага, 2 приёма)
- L7 = сложный региональный этап ВсОШ (4-5 шагов, нетривиальные замены)
- L8 = заключительный этап ВсОШ (5+ шагов, продвинутые техники)

ЗАДАЧА:
{task_text}

РЕШЕНИЕ:
{solution[:3000]}

Заявленный уровень: {difficulty_level}
Количество идей в решении: (оцени сам)

ПРИНЦИПЫ КАЛИБРОВКИ (читай внимательно):
- Если решение содержит 2-3 шага и один ключевой приём → level 4-5
- Если решение содержит 3-4 шага и 2 различных приёма → level 5-6
- Если решение содержит 4-5 шагов, нетривиальную замену/построение → level 6-7
- Если решение содержит 5+ шагов, требует продвинутой техники, глубоких инвариантов, нестандартных конструкций → level 7-8
- Если задача не решается стандартными методами, а требует ПРИДУМАТЬ новый подход → level 7-8
- Геометрия с нетривиальным дополнительным построением → level 6-7
- Комбинаторика с полуинвариантом или производящей функцией → level 7-8
- Теория чисел с глубокими свойствами (первообразные корни, LTE, нестандартные сравнения) → level 6-7
- Функциональное уравнение, где нужно придумать замену и провести анализ степени → level 6-7

НЕ ЗАНИЖАЙ ОЦЕНКУ! Если задача выглядит на 6 — ставь 6, а не 4-5.
Если задача требует продвинутой техники — ставь 7-8 без колебаний.

Ответь ТОЛЬКО JSON:
{{
  "real_level": число 1-8,
  "reasoning": "Обоснование",
  "key_method": "Метод решения",
  "idea_count": число идей
}}"""
    return prompt


def build_correctness_audit_prompt(task_text: str, solution: str, correct_answer: str) -> str:
    prompt = f"""Проверь корректность олимпиадной задачи.

ЗАДАЧА:
{task_text}

ПРЕДЛОЖЕННОЕ РЕШЕНИЕ:
{solution[:5000]}

ПРЕДЛОЖЕННЫЙ ОТВЕТ:
{correct_answer}

Проверь:
1. Корректна ли формулировка?
2. Существует ли хотя бы одно решение?
3. Верен ли ответ?
4. Верно ли решение?

Если решение неверно — НАПИШИ ВЕРНОЕ РЕШЕНИЕ САМ. Не отклоняй задачу, если у неё есть хотя бы одно правильное решение (даже если предложенное решение ошибочно).

ОТВЕТ JSON:
{{
  "is_correct": true/false,
  "correct_answer": "Верный ответ (исправь, если нужно)",
  "correct_solution": "Корректное решение (если исходное неверно — напиши правильное)",
  "issues": "Описание проблем или пустая строка"
}}"""
    return prompt


def build_fix_prompt(task_text: str, solution: str, issues: str, correct_answer: str) -> str:
    prompt = f"""Исправь ошибки в олимпиадной задаче.

ТЕКСТ ЗАДАЧИ:
{task_text}

РЕШЕНИЕ:
{solution}

ОТВЕТ:
{correct_answer}

ПРОБЛЕМЫ:
{issues}

Исправь задачу так, чтобы она стала корректной. Если проблема в формулировке — измени условие.
Если проблема в решении — перепиши решение. Если проблема в ответе — исправь ответ.

ОТВЕТ JSON:
{{
  "task_text": "Исправленный текст задачи",
  "solution": "Исправленное решение",
  "correct_answer": "Исправленный ответ",
  "class_level": число,
  "topic": "Тема",
  "difficulty_level": 6, 7 или 8,
  "key_method": "Метод",
  "idea_count": число
}}"""
    return prompt


# ─── NEW: prompts for difficulty improvement stages ──────────────────

def build_difficulty_improvement_prompt(task_text: str, solution: str,
                                        correct_answer: str, difficulty_level: int) -> str:
    """Промпт для этапа A: модель разрабатывает план усложнения задачи."""
    prompt = f"""Проанализируй олимпиадную задачу уровня {difficulty_level} и разработай план её УСЛОЖНЕНИЯ.

ЗАДАЧА:
{task_text}

РЕШЕНИЕ:
{solution[:4000]}

ОТВЕТ:
{correct_answer}

ЦЕЛЬ: Сделать задачу ЗАМЕТНО СЛОЖНЕЕ — поднять на 1-2 уровня по 8-балльной шкале.
Например, если сейчас уровень 6, сделать 7-8. Если уровень 7, сделать 8.

КАК МОЖНО УСЛОЖНИТЬ ЗАДАЧУ:
1. Добавить дополнительное условие или ограничение, которое меняет подход к решению.
2. Заменить простые числа/выражения на более сложные, требующие дополнительного анализа.
3. Объединить с другой математической идеей (комбинирование тем).
4. Увеличить размерность: с 2 переменных до 3, с плоскости в пространство.
5. Убрать подсказки из условия, сделать вывод менее очевидным.
6. Добавить шаг, который нужно додумать самостоятельно (без явного указания).
7. Сделать конструктивную задачу (доказать существование и привести пример).
8. Обобщить: вместо конкретного числа — параметр, найти все значения.

ВАЖНО: Новая задача должна оставаться КОРРЕКТНОЙ и иметь единственное решение (или конечный набор решений). Не делай задачу бессмысленной или переопределённой.

Опиши план изменений в формате JSON:
{{
  "improvement_plan": "Детальное описание, что и как изменить в задаче (2-4 предложения)",
  "target_level": число (7 или 8),
  "changes": ["конкретное изменение 1", "конкретное изменение 2", ...],
  "new_key_method": "Ключевой метод/идея усложнённой задачи",
  "new_idea_count": число (4-10)
}}"""
    return prompt


def build_improved_task_prompt(task_text: str, solution: str, correct_answer: str,
                               improvement_plan: str, target_level: int) -> str:
    """Промпт для этапа B: на основе плана усложнения генерируем улучшенную задачу."""
    prompt = f"""На основе плана усложнения создай НОВУЮ, БОЛЕЕ СЛОЖНУЮ версию олимпиадной задачи.

ИСХОДНАЯ ЗАДАЧА:
{task_text}

ИСХОДНОЕ РЕШЕНИЕ:
{solution[:3000]}

ИСХОДНЫЙ ОТВЕТ:
{correct_answer}

ПЛАН УСЛОЖНЕНИЯ:
{improvement_plan}

ЦЕЛЕВОЙ УРОВЕНЬ: {target_level}

ТРЕБОВАНИЯ К НОВОЙ ЗАДАЧЕ:
1. ОРИГИНАЛЬНАЯ — не просто копия с изменёнными числами, а качественно другая задача.
2. УРОВЕНЬ {target_level} — сложность должна соответствовать.
3. Решение содержит 4-10 идей/шагов.
4. КОРРЕКТНАЯ — имеет однозначное условие и единственный правильный ответ.
5. Изящное решение, не перебор.
6. Формулировка чёткая и строгая.

ОТВЕТ ДАЙ В ВИДЕ JSON:
{{
  "task_text": "Текст улучшенной задачи (LaTeX)",
  "solution": "Полное решение улучшенной задачи (LaTeX, не менее 800 символов)",
  "correct_answer": "Краткий ответ для улучшенной задачи",
  "class_level": 8-11,
  "topic": "Тема",
  "difficulty_level": {target_level},
  "key_method": "Ключевой метод",
  "idea_count": число (4-10)
}}"""
    return prompt


# ─── topic rotation ──────────────────────────────────────────────────
TOPICS = ["Алгебра", "Теория чисел", "Комбинаторика", "Геометрия", "Логика"]

# ─── main generation loop ────────────────────────────────────────────

def read_all_blacklist() -> List[Dict[str, Any]]:
    """Читает все JSON-файлы из blacklist/."""
    items = []
    if not os.path.isdir(BLACKLIST_DIR):
        return items
    for fname in sorted(os.listdir(BLACKLIST_DIR)):
        if fname.endswith('.json'):
            with open(os.path.join(BLACKLIST_DIR, fname), 'r', encoding='utf-8') as f:
                items.append(json.load(f))
    return items


async def process_one_task(client: DeepSeekClient, task_id: int,
                           topic: str, seen_texts: List[str],
                           max_fix_rounds: int = 3) -> Optional[Dict[str, Any]]:
    """Генерирует одну задачу, проходит аудиты, усложняет, сохраняет результат.
    Возвращает dict задачи или None если нужно повторить."""
    improved = False
    original_difficulty = 0
    original_solution = ""
    original_answer = ""
    original_method = ""
    original_idea_count = 0

    # ── 1. Генерация ────────────────────────────────────────────────
    logger.info(f"[{task_id}] Генерация задачи (тема: {topic})...")
    try:
        gen_prompt = build_generation_prompt(topic)
        gen_raw = await client.a_call(gen_prompt, GENERATION_SYSTEM_PROMPT,
                                       max_tokens=16384, timeout=300)
    except Exception as e:
        logger.error(f"[{task_id}] Ошибка генерации: {e}")
        return None

    task = extract_json(gen_raw)
    if not task:
        logger.warning(f"[{task_id}] Не удалось распарсить JSON из ответа генерации")
        return None

    # Валидация обязательных полей
    for key in ['task_text', 'solution', 'correct_answer', 'difficulty_level']:
        if key not in task:
            logger.warning(f"[{task_id}] В ответе нет поля {key}")
            return None

    task_text = task.get('task_text', '').strip()
    solution = task.get('solution', '').strip()
    correct_answer = task.get('correct_answer', '').strip()
    difficulty_level = safe_int(task.get('difficulty_level', 6))
    class_level = safe_int(task.get('class_level', 9))
    topic_val = task.get('topic', topic)
    key_method = task.get('key_method', '')
    idea_count = safe_int(task.get('idea_count', 3))

    if not task_text or not solution or not correct_answer:
        logger.warning(f"[{task_id}] Пустые поля в ответе")
        return None

    # ── 2. Проверка на клон ──────────────────────────────────────────
    is_clone_flag, sim = is_clone(task_text, seen_texts)
    if is_clone_flag:
        logger.warning(f"[{task_id}] Клон (схожесть {sim:.2%})")
        # Если клон, но real_level >= 5 — сохраняем в reserve (полезная задача)
        # Делаем быстрый level audit для оценки
        try:
            audit_prompt = build_level_audit_prompt(task_text, solution, difficulty_level)
            audit_raw = await client.a_call(audit_prompt, LEVEL_AUDIT_SYSTEM_PROMPT,
                                             max_tokens=2000, timeout=180)
            audit = extract_json(audit_raw)
            real_level = safe_int(audit.get('real_level', 0)) if audit else 0
        except Exception:
            real_level = 0

        clone_task = {
            'id': task_id,
            'task_text': task_text,
            'solution': solution,
            'correct_answer': correct_answer,
            'class_level': class_level,
            'topic': topic_val,
            'difficulty_level': difficulty_level,
            'real_level': real_level,
            'key_method': key_method,
            'idea_count': idea_count,
            'is_clone': True,
            'clone_similarity': round(sim, 3),
            'lang_ok': True,
            '_status': 'clone_exhausted',
            'fix_rounds': 0,
            'quality_score': 0.5,
            'source': 'gen_678',
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }

        if real_level >= 5:
            logger.info(f"[{task_id}] Клон, но real_level={real_level} >= 5 → сохраняем в reserve")
            save_task_json(clone_task, RESERVE_DIR)
            return {'status': 'reserve', 'task': clone_task}
        else:
            logger.info(f"[{task_id}] Клон, real_level={real_level} → в blacklist")
            save_task_json(clone_task, BLACKLIST_DIR)
            return {'status': 'blacklist', 'task': clone_task}

    # ── 3. Аудит корректности ────────────────────────────────────────
    logger.info(f"[{task_id}] Аудит корректности...")
    correct_audit = None
    for audit_attempt in range(3):  # до 3 попыток при ошибке
        try:
            correct_prompt = build_correctness_audit_prompt(task_text, solution, correct_answer)
            correct_raw = await client.a_call(correct_prompt, CORRECTNESS_AUDIT_SYSTEM_PROMPT,
                                               max_tokens=8192, timeout=300)
            correct_audit = extract_json(correct_raw)
            if correct_audit is not None:
                break
            logger.warning(f"[{task_id}] Аудит корректности вернул None, попытка {audit_attempt + 1}/3")
        except Exception as e:
            logger.error(f"[{task_id}] Ошибка аудита корректности (попытка {audit_attempt + 1}/3): {e}")
            correct_audit = None
        if audit_attempt < 2:
            await asyncio.sleep(5)

    if correct_audit is None:
        # Аудит не удался после всех попыток — считаем что задача корректна, но логируем
        logger.warning(f"[{task_id}] Аудит корректности не удался после 3 попыток, продолжаем без аудита")

    if correct_audit and not correct_audit.get('is_correct', True):
        issues = correct_audit.get('issues', 'Неизвестная ошибка')
        logger.warning(f"[{task_id}] Задача некорректна: {issues[:200]}")

        # Попытка исправить (максимум max_fix_rounds раундов)
        for fix_round in range(1, max_fix_rounds + 1):
            logger.info(f"[{task_id}] Раунд исправления {fix_round}/{max_fix_rounds}...")
            try:
                fix_prompt = build_fix_prompt(task_text, solution, issues, correct_answer)
                fix_raw = await client.a_call(fix_prompt, GENERATION_SYSTEM_PROMPT,
                                              max_tokens=16384, timeout=300)
                fixed = extract_json(fix_raw)
            except Exception as e:
                logger.error(f"[{task_id}] Ошибка исправления: {e}")
                continue

            if not fixed or not fixed.get('task_text'):
                continue

            task_text = fixed.get('task_text', task_text)
            solution = fixed.get('solution', solution)
            correct_answer = fixed.get('correct_answer', correct_answer)
            difficulty_level = safe_int(fixed.get('difficulty_level', difficulty_level))
            class_level = safe_int(fixed.get('class_level', class_level))
            key_method = fixed.get('key_method', key_method)
            idea_count = safe_int(fixed.get('idea_count', idea_count))

            # Проверяем исправленную версию
            try:
                correct_prompt2 = build_correctness_audit_prompt(task_text, solution, correct_answer)
                correct_raw2 = await client.a_call(correct_prompt2, CORRECTNESS_AUDIT_SYSTEM_PROMPT,
                                                   max_tokens=8192, timeout=300)
                correct_audit2 = extract_json(correct_raw2)
            except Exception:
                continue

            if correct_audit2 and correct_audit2.get('is_correct', False):
                logger.info(f"[{task_id}] Задача исправлена в раунде {fix_round}")
                # Используем исправленные данные
                if correct_audit2.get('correct_solution'):
                    solution = correct_audit2['correct_solution']
                if correct_audit2.get('correct_answer'):
                    correct_answer = correct_audit2['correct_answer']
                break
            else:
                issues = correct_audit2.get('issues', 'Не удалось исправить') if correct_audit2 else 'Неизвестно'
        else:
            # Не удалось исправить
            logger.warning(f"[{task_id}] Не удалось исправить задачу после {max_fix_rounds} раундов → blacklist")
            failed_task = {
                'id': task_id,
                'task_text': task_text,
                'solution': solution,
                'correct_answer': correct_answer,
                'class_level': class_level,
                'topic': topic_val,
                'difficulty_level': difficulty_level,
                'real_level': 0,
                'key_method': key_method,
                'idea_count': idea_count,
                'is_clone': False,
                'lang_ok': True,
                '_status': 'fix_failed',
                'fix_rounds': max_fix_rounds,
                'issues': issues,
                'quality_score': 0.0,
                'source': 'gen_678',
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }
            save_task_json(failed_task, BLACKLIST_DIR)
            return {'status': 'blacklist', 'task': failed_task}
    else:
        # Задача корректна — используем аудиторское решение если есть
        if correct_audit and correct_audit.get('correct_solution'):
            solution = correct_audit['correct_solution']
        if correct_audit and correct_audit.get('correct_answer'):
            correct_answer = correct_audit['correct_answer']

    # ── 4. (NEW) Этап A: План усложнения ──────────────────────────────
    logger.info(f"[{task_id}] Этап A: разработка плана усложнения...")
    try:
        improv_prompt = build_difficulty_improvement_prompt(
            task_text, solution, correct_answer, difficulty_level)
        improv_raw = await client.a_call(improv_prompt, GENERATION_SYSTEM_PROMPT,
                                         max_tokens=4096, timeout=300)
        improv_plan = extract_json(improv_raw)
    except Exception as e:
        logger.error(f"[{task_id}] Ошибка при разработке плана усложнения: {e}")
        improv_plan = None

    if not improv_plan or not improv_plan.get('improvement_plan'):
        logger.warning(f"[{task_id}] Не удалось получить план усложнения → используем исходную задачу")
        # Переходим сразу к level audit с исходной задачей
        improved = False
    else:
        improvement_plan = improv_plan['improvement_plan']
        target_level = safe_int(improv_plan.get('target_level', min(difficulty_level + 1, 8)))
        logger.info(f"[{task_id}] План усложнения получен: target_level={target_level}")

        # ── 5. (NEW) Этап B: Генерация улучшенной задачи ──────────────
        logger.info(f"[{task_id}] Этап B: генерация улучшенной задачи (target={target_level})...")
        try:
            improved_prompt = build_improved_task_prompt(
                task_text, solution, correct_answer,
                improvement_plan, target_level)
            improved_raw = await client.a_call(improved_prompt, GENERATION_SYSTEM_PROMPT,
                                               max_tokens=16384, timeout=300)
            improved_task = extract_json(improved_raw)
        except Exception as e:
            logger.error(f"[{task_id}] Ошибка при генерации улучшенной задачи: {e}")
            improved_task = None

        if not improved_task or not improved_task.get('task_text'):
            logger.warning(f"[{task_id}] Не удалось сгенерировать улучшенную задачу → используем исходную")
            improved = False
        else:
            # Обновляем данные на улучшенную задачу
            original_difficulty = difficulty_level
            original_solution = solution
            original_answer = correct_answer
            original_method = key_method
            original_idea_count = idea_count

            task_text = improved_task.get('task_text', task_text)
            solution = improved_task.get('solution', solution)
            correct_answer = improved_task.get('correct_answer', correct_answer)
            # difficulty_level не занижаем: берём максимум из того что дала модель и target_level
            model_diff = safe_int(improved_task.get('difficulty_level', difficulty_level))
            difficulty_level = max(model_diff, target_level)
            class_level = safe_int(improved_task.get('class_level', class_level))
            key_method = improved_task.get('key_method', key_method)
            idea_count = safe_int(improved_task.get('idea_count', idea_count))
            improved = True

            logger.info(f"[{task_id}] Улучшенная задача сгенерирована: {difficulty_level=}")

            # ── 6. (NEW) Аудит корректности улучшенной задачи ─────────
            if improved:
                logger.info(f"[{task_id}] Аудит корректности улучшенной задачи...")
                try:
                    correct_prompt3 = build_correctness_audit_prompt(
                        task_text, solution, correct_answer)
                    correct_raw3 = await client.a_call(
                        correct_prompt3, CORRECTNESS_AUDIT_SYSTEM_PROMPT,
                        max_tokens=8192, timeout=300)
                    correct_audit3 = extract_json(correct_raw3)
                except Exception as e:
                    logger.error(f"[{task_id}] Ошибка аудита улучшенной задачи: {e}")
                    correct_audit3 = None

                if correct_audit3 and not correct_audit3.get('is_correct', True):
                    issues3 = correct_audit3.get('issues', 'Неизвестная ошибка')
                    logger.warning(f"[{task_id}] Улучшенная задача некорректна: {issues3[:200]}")

                    # Пытаемся исправить улучшенную задачу
                    for fix_round in range(1, max_fix_rounds + 1):
                        logger.info(f"[{task_id}] Исправление улучшенной задачи, раунд {fix_round}/{max_fix_rounds}...")
                        try:
                            fix_prompt3 = build_fix_prompt(
                                task_text, solution, issues3, correct_answer)
                            fix_raw3 = await client.a_call(
                                fix_prompt3, GENERATION_SYSTEM_PROMPT,
                                max_tokens=16384, timeout=300)
                            fixed3 = extract_json(fix_raw3)
                        except Exception:
                            continue

                        if not fixed3 or not fixed3.get('task_text'):
                            continue

                        task_text = fixed3.get('task_text', task_text)
                        solution = fixed3.get('solution', solution)
                        correct_answer = fixed3.get('correct_answer', correct_answer)
                        difficulty_level = safe_int(fixed3.get('difficulty_level', difficulty_level))
                        class_level = safe_int(fixed3.get('class_level', class_level))
                        key_method = fixed3.get('key_method', key_method)
                        idea_count = safe_int(fixed3.get('idea_count', idea_count))

                        try:
                            correct_prompt4 = build_correctness_audit_prompt(
                                task_text, solution, correct_answer)
                            correct_raw4 = await client.a_call(
                                correct_prompt4, CORRECTNESS_AUDIT_SYSTEM_PROMPT,
                                max_tokens=8192, timeout=300)
                            correct_audit4 = extract_json(correct_raw4)
                        except Exception:
                            continue

                        if correct_audit4 and correct_audit4.get('is_correct', False):
                            logger.info(f"[{task_id}] Улучшенная задача исправлена в раунде {fix_round}")
                            if correct_audit4.get('correct_solution'):
                                solution = correct_audit4['correct_solution']
                            if correct_audit4.get('correct_answer'):
                                correct_answer = correct_audit4['correct_answer']
                            break
                    else:
                        # Не удалось исправить улучшенную задачу — откатываемся к исходной
                        logger.warning(f"[{task_id}] Улучшенная задача не прошла аудит, откат к исходной")
                        # Восстанавливаем оригинальные данные из сохранённых original_* переменных
                        if original_solution and original_answer:
                            solution = original_solution
                            correct_answer = original_answer
                            key_method = original_method or key_method
                            idea_count = original_idea_count or idea_count
                            difficulty_level = original_difficulty
                        else:
                            # fallback: не завышаем уровень, если нет original_*
                            difficulty_level = min(difficulty_level, model_diff)
                        # task_text не восстанавливаем — original_task_text не сохраняли,
                        # но берём то что было до улучшения (у нас нет), используем исходный improved_task
                        # как source — в любом случае идём на level audit
                        logger.info(f"[{task_id}] Продолжаем с исходной версией, difficulty={difficulty_level}")
                else:
                    if correct_audit3 and correct_audit3.get('correct_solution'):
                        solution = correct_audit3['correct_solution']
                    if correct_audit3 and correct_audit3.get('correct_answer'):
                        correct_answer = correct_audit3['correct_answer']
                    logger.info(f"[{task_id}] Улучшенная задача корректна")

    # ── 7. Аудит уровня ──────────────────────────────────────────────
    logger.info(f"[{task_id}] Аудит уровня...")
    try:
        level_prompt = build_level_audit_prompt(task_text, solution, difficulty_level)
        level_raw = await client.a_call(level_prompt, LEVEL_AUDIT_SYSTEM_PROMPT,
                                        max_tokens=2000, timeout=180)
        level_audit = extract_json(level_raw)
    except Exception as e:
        logger.error(f"[{task_id}] Ошибка аудита уровня: {e}")
        level_audit = None

    if level_audit:
        real_level = safe_int(level_audit.get('real_level', difficulty_level))
        audit_key_method = level_audit.get('key_method', '')
        audit_idea_count = safe_int(level_audit.get('idea_count', idea_count))
        level_reasoning = level_audit.get('reasoning', '')
    else:
        real_level = difficulty_level
        audit_key_method = key_method
        audit_idea_count = idea_count
        level_reasoning = "audit failed"

    # Если аудит дал real_level < difficulty_level — используем difficulty_level
    # (аудит склонен занижать, генератор знает уровень лучше)
    if real_level < difficulty_level:
        logger.info(f"[{task_id}] Аудит дал {real_level} < {difficulty_level} (заявленный). "
                     f"Используем difficulty_level={difficulty_level}")
        real_level = difficulty_level

    logger.info(f"[{task_id}] difficulty_level={difficulty_level} → real_level={real_level} ({level_reasoning})")

    # ── 8. Сохранение ────────────────────────────────────────────────
    result_task = {
        'id': task_id,
        'task_text': task_text,
        'solution': solution,
        'correct_answer': correct_answer,
        'class_level': class_level,
        'topic': topic_val,
        'difficulty_level': difficulty_level,
        'real_level': real_level,
        'key_method': audit_key_method or key_method,
        'idea_count': audit_idea_count or idea_count,
        'is_clone': False,
        'lang_ok': True,
        '_status': 'active',
        'fix_rounds': 0,
        'quality_score': 1.0,
        'source': 'gen_678',
        'was_improved': improved,
        'generated_at': datetime.now(timezone.utc).isoformat(),
    }

    if real_level >= 8:
        save_task_json(result_task, L8_DIR)
        logger.info(f"[{task_id}] → L8!")
        return {'status': 'accepted', 'level': 8, 'task': result_task}
    elif real_level == 7:
        save_task_json(result_task, L7_DIR)
        logger.info(f"[{task_id}] → L7")
        return {'status': 'accepted', 'level': 7, 'task': result_task}
    elif real_level == 6:
        save_task_json(result_task, L6_DIR)
        logger.info(f"[{task_id}] → L6")
        return {'status': 'accepted', 'level': 6, 'task': result_task}
    else:
        # real_level <= 5 — сохраняем в reserve (может быть полезна как более лёгкая)
        result_task['_status'] = 'reserve_low_level'
        save_task_json(result_task, RESERVE_DIR)
        logger.info(f"[{task_id}] → reserve (real_level={real_level} < 6)")
        return {'status': 'reserve', 'task': result_task}


async def async_main(target: int = 1000, max_concurrent: int = 1, max_duration: int = 20):
    """Основной асинхронный цикл генерации с конкурентным выполнением.

    Args:
        target: Сколько задач принять — для отчёта (сумма L8+L7+L6).
        max_concurrent: Сколько задач обрабатывать одновременно.
        max_duration: Максимальное время работы в минутах (default: 20).
    """
    ensure_dirs()
    global SEEN_TEXTS
    SEEN_TEXTS = load_seen_texts()
    logger.info(f"Загружено {len(SEEN_TEXTS)} seen_texts для детекции клонов")

    # Загружаем checkpoint если есть
    cp = load_checkpoint()
    if cp:
        # Конвертируем ключи accepted_counts из str в int (JSON сохраняет как строки)
        raw_counts = cp.get('accepted_counts', {})
        cp_total = sum(raw_counts.values()) if isinstance(raw_counts, dict) else 0
        logger.info(f"Найден checkpoint: принято {cp_total} задач, "
                     f"blacklist {cp.get('blacklist_count', 0)}, "
                     f"next_id={cp.get('next_id', 800001)}")
        next_id = cp.get('next_id', load_next_id())
        accepted_counts = {}
        for k, v in raw_counts.items():
            try:
                accepted_counts[int(k)] = v
            except (ValueError, TypeError):
                pass
        for k in [8, 7, 6]:
            accepted_counts.setdefault(k, 0)
        blacklist_count = cp.get('blacklist_count', 0)
        reserve_count = cp.get('reserve_count', 0)
        correction_count = cp.get('correction_count', 0)
        start_time = cp.get('start_time', time.time())
        consecutive_blacklist = cp.get('consecutive_blacklist', 0)
        topic_index = cp.get('topic_index', 0)
    else:
        next_id = load_next_id()
        accepted_counts = {8: 0, 7: 0, 6: 0}
        blacklist_count = 0
        reserve_count = 0
        correction_count = 0
        start_time = time.time()
        consecutive_blacklist = 0
        topic_index = 0

    total_accepted = sum(accepted_counts.values())

    # Проверяем, сколько уже есть сохранённых задач в L8/L7/L6
    for level_dir, level_key in [(L8_DIR, 8), (L7_DIR, 7), (L6_DIR, 6)]:
        existing = [f for f in os.listdir(level_dir) if f.endswith('.json')]
        accepted_counts[level_key] = max(accepted_counts[level_key], len(existing))

    total_accepted = sum(accepted_counts.values())
    logger.info(f"Уже принято: L8={accepted_counts[8]}, L7={accepted_counts[7]}, L6={accepted_counts[6]}, всего={total_accepted}")

    client = DeepSeekClient()
    logger.info("DeepSeekClient инициализирован")

    # --- Concurrent generation with time limit ---
    semaphore = asyncio.Semaphore(max_concurrent)
    id_lock = asyncio.Lock()
    deadline = time.time() + max_duration * 60
    worker_count = max_concurrent * 3  # extra workers keep semaphore saturated

    async def safe_save_checkpoint():
        save_checkpoint({
            'next_id': next_id,
            'accepted_counts': accepted_counts,
            'blacklist_count': blacklist_count,
            'reserve_count': reserve_count,
            'correction_count': correction_count,
            'start_time': start_time,
            'consecutive_blacklist': consecutive_blacklist,
            'topic_index': topic_index,
        })
        generate_report(accepted_counts, blacklist_count, reserve_count, start_time, correction_count)

    async def worker(wid: int):
        nonlocal next_id, topic_index, total_accepted, accepted_counts
        nonlocal blacklist_count, reserve_count, correction_count, consecutive_blacklist
        global SEEN_TEXTS

        while time.time() < deadline:
            # Get next task ID and topic (thread-safe via locks)
            async with id_lock:
                my_id = next_id
                my_topic = TOPICS[topic_index % len(TOPICS)]
                topic_index += 1
                next_id = my_id + 1
                save_next_id(next_id)

            logger.info(f"\n{'='*60}\n"
                         f"Task #{my_id} (topic: {my_topic})\n"
                         f"Accepted: L8={accepted_counts[8]}, L7={accepted_counts[7]}, "
                         f"L6={accepted_counts[6]}, total={total_accepted}/{target}\n"
                         f"Blacklist: {blacklist_count}, Reserve: {reserve_count}\n"
                         f"Consecutive blacklist: {consecutive_blacklist}\n"
                         f"{'='*60}")

            async with semaphore:
                try:
                    result = await process_one_task(client, my_id, my_topic, SEEN_TEXTS)
                except Exception as e:
                    logger.error(f"[{my_id}] Critical error: {e}\n{traceback.format_exc()}")
                    await safe_save_checkpoint()
                    await asyncio.sleep(10)
                    continue

                if result is None:
                    logger.warning(f"[{my_id}] Generation error, continuing")
                    consecutive_blacklist = 0
                    continue

                status = result['status']

                if status == 'accepted':
                    level = result['level']
                    accepted_counts[level] = accepted_counts.get(level, 0) + 1
                    total_accepted = sum(accepted_counts.values())
                    consecutive_blacklist = 0
                    task_text = result['task'].get('task_text', '')
                    if task_text and task_text not in SEEN_TEXTS:
                        SEEN_TEXTS.append(task_text)
                        save_seen_texts(SEEN_TEXTS)
                    logger.info(f"[OK] Accepted! L{level} (#{total_accepted}/{target})")

                elif status == 'reserve':
                    reserve_count += 1
                    consecutive_blacklist = 0
                    task_text = result['task'].get('task_text', '')
                    if task_text and task_text not in SEEN_TEXTS:
                        SEEN_TEXTS.append(task_text)
                        save_seen_texts(SEEN_TEXTS)

                elif status == 'blacklist':
                    blacklist_count += 1
                    consecutive_blacklist += 1

                # --- Prompt correction ---
                if consecutive_blacklist >= 15:
                    logger.warning(f"{consecutive_blacklist} tasks in blacklist! Correcting prompt...")
                    blacklist_items = read_all_blacklist()
                    log_prompt_correction("failed_exhausted", blacklist_items)
                    correction_count += 1
                    consecutive_blacklist = 0

                # --- Save checkpoint every 3 tasks ---
                if (total_accepted + blacklist_count + reserve_count) % 3 == 0:
                    save_checkpoint({
                        'next_id': next_id,
                        'accepted_counts': accepted_counts,
                        'blacklist_count': blacklist_count,
                        'reserve_count': reserve_count,
                        'correction_count': correction_count,
                        'start_time': start_time,
                        'consecutive_blacklist': consecutive_blacklist,
                        'topic_index': topic_index,
                    })
                    generate_report(accepted_counts, blacklist_count, reserve_count, start_time, correction_count)

    # Launch workers
    workers = [asyncio.create_task(worker(i)) for i in range(worker_count)]
    await asyncio.gather(*workers, return_exceptions=True)

    # --- Time's up ---
    generate_report(accepted_counts, blacklist_count, reserve_count, start_time, correction_count)
    clear_checkpoint()
    logger.info(f"[TIME UP] {max_duration} min elapsed! "
                f"L8={accepted_counts[8]}, L7={accepted_counts[7]}, L6={accepted_counts[6]}")

    # Generate check_678.json
    check_data = {}
    for level_dir, level_name in [(L8_DIR, 'L8'), (L7_DIR, 'L7'), (L6_DIR, 'L6')]:
        files = [f for f in os.listdir(level_dir) if f.endswith('.json')]
        sample = []
        for fname in sorted(files)[-3:]:
            with open(os.path.join(level_dir, fname), 'r', encoding='utf-8') as f:
                sample.append(json.load(f))
        check_data[level_name] = sample

    with open(os.path.join(BASE_DIR, "check_678.json"), 'w', encoding='utf-8') as f:
        json.dump(check_data, f, ensure_ascii=False, indent=2)
    logger.info("check_678.json saved")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Генератор олимпиадных задач 6-7-8 уровней')
    parser.add_argument('--target', type=int, default=1000,
                        help='Сколько задач принять (default: 1000)')
    parser.add_argument('--max-concurrent', type=int, default=1,
                        help='Максимум одновременных задач (default: 1)')
    parser.add_argument('--max-duration', type=int, default=20,
                        help='Максимальное время работы в минутах (default: 20)')
    args = parser.parse_args()

    # Автоматический перезапуск при падении (ConnectionReset, API errors и т.д.)
    # Состояние восстанавливается из файлов на диске (next_id.txt, файлы задач)
    max_restarts = 100
    restart_delay = 15  # секунд
    for attempt in range(1, max_restarts + 1):
        try:
            asyncio.run(async_main(target=args.target, max_concurrent=args.max_concurrent, max_duration=args.max_duration))
            break  # успешно завершилось
        except Exception as e:
            logger.error(f"[CRASH] Skript upal (popytka {attempt}/{max_restarts}): {e}\n{traceback.format_exc()}")
            if attempt < max_restarts:
                logger.info(f"[RESTART] Perezapusk cherez {restart_delay} sekund...")
                time.sleep(restart_delay)
            else:
                logger.error("[DEAD] Ischerpany vse popytki perezapuska.")
                raise
