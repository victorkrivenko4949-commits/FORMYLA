#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
3-Stage Olympiad Task Generation Pipeline.

Stage 1: Find a real task from the archive (from OLYMPIADS_DB)
Stage 2: Rewrite with uniqueness validation (SequenceMatcher < 35%)
Stage 3: Polish LaTeX (fix bare commands, balance $)

Usage:
    from services.olympiad_3stage import generate_olympiad_3stage
    result = generate_olympiad_3stage('vsosh', 'school', 5, olympiads_db)
"""

import json
import logging
import random
import re
import time
from datetime import datetime
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Запрещённые персонажи (сказочные) ────────────────────────────────────────
FORBIDDEN_NAMES = [
    'шляпник', 'мартовский заяц', 'соня', 'алиса',
    'буратино', 'чеширский', 'винни', 'пятачок',
    'карлсон', 'малыш', 'незнайка', 'знайка',
    'мальвина', 'пьеро', 'артемон',
]

# ─── Минимальная длина текста задачи (отсекает заглушки) ───────────────────────
MIN_TASK_TEXT_LENGTH = 80

# ─── Паттерны заглушек/плейсхолдеров ─────────────────────────────────────────
PLACEHOLDER_PATTERNS = [
    re.compile(r'\(вариант\s*\d+\)', re.IGNORECASE),
    re.compile(r'см\.\s*№'),
    re.compile(r'^Аналогичная задача'),
]


def _is_valid_task_text(text: str) -> bool:
    """
    Проверяет что текст задачи — полноценное условие, а не заглушка.
    Возвращает True если текст валиден для использования.
    """
    if not text or len(text) < MIN_TASK_TEXT_LENGTH:
        return False
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(text):
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 1: Найти задачу из архива
# ═══════════════════════════════════════════════════════════════════════════════

def stage1_find_task(
    olympiad_slug: str,
    round_key: str,
    class_level: int,
    olympiads_db: list,
) -> dict:
    """
    Выбирает случайную РЕАЛЬНУЮ задачу из архива OLYMPIADS_DB.
    Не вызывает DeepSeek — просто берёт из базы.

    Returns:
        {
            'year': 2019,
            'problem_num': 3,
            'task_text': '...',
            'answer': '...',
            'olympiad': 'vsosh',
            'round': 'school',
            'grade': 5,
        }
    """
    # Собираем подходящие задачи
    candidates = []
    for combo in olympiads_db:
        if (combo.get('olympiad') == olympiad_slug
                and str(combo.get('grade', '')) == str(class_level)
                and (not round_key or combo.get('round') == round_key)):
            year = combo.get('year', '?')
            for prob in combo.get('problems', []):
                text = prob.get('text', '').strip()
                if _is_valid_task_text(text) and len(text) < 1500:
                    candidates.append({
                        'year': year,
                        'problem_num': prob.get('num', '?'),
                        'task_text': text,
                        'answer': prob.get('answer', ''),
                        'olympiad': olympiad_slug,
                        'round': round_key,
                        'grade': class_level,
                    })

    # Fallback: любой этап этой олимпиады/класса
    if not candidates:
        for combo in olympiads_db:
            if (combo.get('olympiad') == olympiad_slug
                    and str(combo.get('grade', '')) == str(class_level)):
                year = combo.get('year', '?')
                for prob in combo.get('problems', []):
                    text = prob.get('text', '').strip()
                    if _is_valid_task_text(text) and len(text) < 1500:
                        candidates.append({
                            'year': year,
                            'problem_num': prob.get('num', '?'),
                            'task_text': text,
                            'answer': prob.get('answer', ''),
                            'olympiad': olympiad_slug,
                            'round': combo.get('round', ''),
                            'grade': class_level,
                        })

    if not candidates:
        raise ValueError(
            f"Нет задач в архиве для {olympiad_slug}/{round_key}/класс {class_level} "
            f"(все задачи отфильтрованы как заглушки < {MIN_TASK_TEXT_LENGTH} символов)"
        )

    chosen = random.choice(candidates)
    logger.info(
        f"[Stage 1] Найдено {len(candidates)} валидных задач, выбрана: "
        f"{chosen['olympiad']}, "
        f"{chosen['year']} год, №{chosen['problem_num']}"
    )
    return chosen


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 2: Рерайт с валидацией сходства
# ═══════════════════════════════════════════════════════════════════════════════

REWRITE_PROMPT = """Ты — составитель олимпиадных задач по математике.

ОРИГИНАЛ (из архива {olympiad}, {year} год, задача №{problem_num}):
---
{task_text}
---

Перепиши эту задачу так, чтобы:
[OK] МАТЕМАТИЧЕСКИЙ МЕТОД остался тем же
[OK] СЛОЖНОСТЬ осталась той же (для {grade} класса)
[OK] Тип ответа остался тем же
[ERROR] ВСЕ числа заменены на другие (но ответ красивый)
[ERROR] ВСЕ персонажи заменены (используй: Петя, Вася, Маша, Аня, Коля, Даша)
[ERROR] Контекст полностью другой
[ERROR] Формулировка переписана своими словами
[ERROR] Задача НЕ ГУГЛИТСЯ — никаких уникальных фраз из оригинала

 ЗАПРЕЩЕНЫ сказочные персонажи (Алиса, Шляпник, Буратино, Незнайка и т.д.)
[OK] Используй обычные русские имена.

{extra_pressure}

[!]️ ФОРМАТИРОВАНИЕ LaTeX — КРИТИЧНО:
- КАЖДАЯ переменная в $...$: $x$, $y$, $n$, $a$
- КАЖДАЯ степень через ^: $x^2$, $n^3$, $a^{{10}}$
- КАЖДЫЙ индекс через _: $a_1$, $x_{{12}}$
- Углы: $\\angle ABC = 60^\\circ$ (НЕ юникод ∠°)
- Треугольники: $\\triangle ABC$ (НЕ юникод △)
- Дроби: $\\frac{{a}}{{b}}$ (НЕ a/b)
- Корни: $\\sqrt{{n}}$ (НЕ √n)
- Неравенства: $\\leq$, $\\geq$ (НЕ юникод ≤≥)
- Display формулы: $$y^2 - 1 = a^2(x^2 - 1)$$
- НИ ОДНОГО голого x2, y3, a10 без $!

Верни СТРОГО JSON без markdown-блоков:
{{
  "task_text": "Новая задача с формулами в $...$",
  "solution": "Полное пошаговое решение новой задачи с LaTeX",
  "correct_answer": "Краткий ответ",
  "topic": "Тема задачи",
  "method": "Метод решения",
  "difficulty": {difficulty},
  "key_idea": "Ключевая идея в одно предложение"
}}
"""


def stage2_rewrite(
    original: dict,
    max_attempts: int = 4,
) -> dict:
    """
    DeepSeek переписывает условие.
    SequenceMatcher валидирует что сходство < 35%.
    До 4 попыток с усилением давления.

    Returns:
        {
            'task_text': '...',
            'solution': '...',
            'correct_answer': '...',
            'topic': '...',
            'method': '...',
            'difficulty': 3,
            'key_idea': '...',
            'similarity_to_original': 0.25,
            'rewrite_attempts': 2,
        }
    """
    from ai.deepseek_client import DeepSeekClient
    from services.task_validator import validate_generated_task

    # Защита: если оригинал — заглушка, отказываемся переписывать
    orig_text = original.get('task_text', '')
    if not _is_valid_task_text(orig_text):
        raise ValueError(
            f"Stage 2 отказ: оригинал слишком короткий или является заглушкой "
            f"({len(orig_text)} chars): '{orig_text[:100]}'"
        )

    client = DeepSeekClient()

    for attempt in range(1, max_attempts + 1):
        extra = ""
        if attempt > 1:
            extra = (
                f"\n[!]️ ВНИМАНИЕ: попытка {attempt}. Предыдущая была СЛИШКОМ ПОХОЖА.\n"
                "ПОЛНОСТЬЮ ПОМЕНЯЙ:\n"
                "- Всех персонажей (запрещены имена из оригинала!)\n"
                "- Все числа (каждое!)\n"
                "- Весь контекст (другая тема: спорт/школа/магазин/поезда)\n"
                "- Формулировку переписать до последнего слова.\n"
            )

        prompt = REWRITE_PROMPT.format(
            olympiad=original.get('olympiad', ''),
            year=original.get('year', '?'),
            problem_num=original.get('problem_num', '?'),
            task_text=original['task_text'],
            grade=original.get('grade', 5),
            difficulty=original.get('difficulty', 3),
            extra_pressure=extra,
        )

        temperature = 0.8 + (attempt - 1) * 0.05

        try:
            raw_response = client.generate(
                prompt=prompt,
                system_prompt=(
                    "Ты — составитель олимпиадных задач. "
                    "Отвечай ТОЛЬКО валидным JSON без markdown-блоков."
                ),
                temperature=temperature,
                max_tokens=2500,
            )
        except Exception as e:
            logger.warning(f"[Stage 2] API error attempt {attempt}: {e}")
            continue

        # Валидация через существующий валидатор
        result = validate_generated_task(
            raw_response,
            few_shot_texts=[original['task_text']]
        )

        if not result['valid']:
            logger.warning(
                f"[Stage 2] Attempt {attempt} validation failed: {result['errors']}"
            )
            continue

        parsed = result['task']

        # Проверка сходства
        sim = SequenceMatcher(
            None,
            original['task_text'].lower(),
            parsed['task_text'].lower()
        ).ratio()

        # Проверка запрещённых имён
        has_forbidden = any(
            name in parsed['task_text'].lower()
            for name in FORBIDDEN_NAMES
        )

        logger.info(
            f"[Stage 2] Attempt {attempt}: similarity={sim:.2%}, "
            f"forbidden_names={has_forbidden}"
        )

        if sim < 0.35 and not has_forbidden:
            parsed['similarity_to_original'] = sim
            parsed['rewrite_attempts'] = attempt
            parsed['solution_hidden'] = parsed.get('solution', '')
            return parsed

        logger.warning(
            f"[Stage 2] Attempt {attempt} REJECTED: "
            f"sim={sim:.2%}, forbidden={has_forbidden}"
        )

    # Все попытки провалились — возвращаем последний результат с предупреждением
    if result and result.get('task'):
        parsed = result['task']
        parsed['similarity_to_original'] = sim
        parsed['rewrite_attempts'] = max_attempts
        parsed['solution_hidden'] = parsed.get('solution', '')
        parsed['warning'] = 'low_uniqueness'
        logger.error(
            f"[Stage 2] All {max_attempts} attempts failed, "
            f"returning last result with warning (sim={sim:.2%})"
        )
        return parsed

    raise ValueError(
        f"Stage 2 failed after {max_attempts} attempts: no valid result"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 3: Полировка LaTeX
# ═══════════════════════════════════════════════════════════════════════════════

def stage3_polish_latex(task: dict) -> dict:
    """
    Проверяет LaTeX в task_text:
    - Все формулы в $...$ или $$...$$
    - Нет голых \\sqrt, \\frac без обёртки
    - Сбалансированы $

    Если всё ОК — возвращает как есть.
    Если есть проблемы — вызывает LaTeX-агента.
    """
    text = task.get('task_text', '')
    issues = []

    # 1. Голые LaTeX-команды без $
    bare_latex = re.findall(
        r'(?<!\$)(\\(?:sqrt|frac|lfloor|rfloor|sum|int|prod|'
        r'mathbb|mathcal|leq|geq|neq|cdot|times|pm)\b)',
        text
    )
    if bare_latex:
        issues.append('bare_latex_commands')

    # 2. Нет $ вообще, но есть LaTeX-команды
    if '\\' in text and '$' not in text:
        issues.append('no_dollar_wrapping')

    # 3. Нечётное количество $ (несбалансированы)
    dollar_count = text.count('$') - 2 * text.count('$$')
    if dollar_count % 2 != 0:
        issues.append('unbalanced_dollars')

    # Если проблем нет — возврат
    if not issues:
        task['latex_polished'] = False
        return task

    logger.warning(f"[Stage 3] LaTeX issues: {issues}, calling polish agent")

    # Вызов агента полировки
    from ai.deepseek_client import DeepSeekClient
    client = DeepSeekClient()

    polish_prompt = f"""Исправь LaTeX в тексте математической задачи.

ПРАВИЛА:
1. ВСЕ математические выражения оберни в $...$ (inline) или $$...$$ (display).
2. Команды \\sqrt, \\frac, \\lfloor, \\sum и т.д. НЕ должны стоять без $.
3. Сбалансируй количество $.
4. Не трогай обычный русский текст.
5. Не меняй математику — только обёртку.
6. Индексы: $a_1, a_2, \\ldots, a_n$. Степени: $x^2$.

ВХОД:
{text}

ВЫХОД: ТОЛЬКО исправленный текст задачи, без комментариев, без JSON.
"""

    try:
        polished = client.generate(
            prompt=polish_prompt,
            system_prompt="Ты — специалист по LaTeX. Исправь обёртку формул.",
            temperature=0.1,
            max_tokens=1500,
        )
        # Убираем возможные markdown-блоки
        polished = polished.strip()
        if polished.startswith('```'):
            polished = re.sub(r'^```\w*\n?', '', polished)
            polished = re.sub(r'\n?```$', '', polished)
        task['task_text'] = polished.strip()
        task['latex_polished'] = True
    except Exception as e:
        logger.warning(f"[Stage 3] Polish failed: {e}, keeping original")
        task['latex_polished'] = False

    return task


# ═══════════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ: 3-Stage Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

def generate_olympiad_3stage(
    olympiad_slug: str,
    round_key: str,
    class_level: int,
    olympiads_db: list,
    olympiad_name: str = '',
    round_name: str = '',
    user_id: Optional[int] = None,
) -> dict:
    """
    Генерирует олимпиадную задачу через 3-этапный pipeline:
    1. Выбор реальной задачи из архива
    2. Рерайт с валидацией уникальности (sim < 35%)
    3. Полировка LaTeX

    Returns:
        {
            'success': bool,
            'task': dict | None,  # task_text, solution_hidden, correct_answer, etc.
            'attempts': int,
            'stage1_source': dict,  # year, problem_num
            'similarity': float,
            'latex_polished': bool,
            'last_errors': list,
        }
    """
    t_start = time.time()

    try:
        # ── STAGE 1: Найти задачу из архива ──
        original = stage1_find_task(
            olympiad_slug, round_key, class_level, olympiads_db
        )
        t_stage1 = time.time() - t_start
        logger.info(
            f"[3Stage] Stage 1 OK ({t_stage1:.1f}s): "
            f"{original['year']} год, №{original['problem_num']}"
        )

        # ── STAGE 2: Рерайт ──
        t2_start = time.time()
        rewritten = stage2_rewrite(original, max_attempts=4)
        t_stage2 = time.time() - t2_start
        logger.info(
            f"[3Stage] Stage 2 OK ({t_stage2:.1f}s): "
            f"sim={rewritten.get('similarity_to_original', 0):.2%}, "
            f"attempts={rewritten.get('rewrite_attempts', '?')}"
        )

        # ── STAGE 3: Полировка LaTeX ──
        t3_start = time.time()
        final = stage3_polish_latex(rewritten)
        t_stage3 = time.time() - t3_start
        logger.info(
            f"[3Stage] Stage 3 OK ({t_stage3:.1f}s): "
            f"polished={final.get('latex_polished', False)}"
        )

        # Логируем
        _log_3stage(
            olympiad_slug=olympiad_slug,
            round_key=round_key,
            class_level=class_level,
            success=True,
            stage1_time=t_stage1,
            stage2_time=t_stage2,
            stage2_attempts=rewritten.get('rewrite_attempts', 1),
            stage3_called=final.get('latex_polished', False),
            similarity=rewritten.get('similarity_to_original', 0),
            user_id=user_id,
        )

        return {
            'success': True,
            'task': final,
            'attempts': rewritten.get('rewrite_attempts', 1),
            'stage1_source': {
                'year': original.get('year'),
                'problem_num': original.get('problem_num'),
                'olympiad': original.get('olympiad'),
            },
            'similarity': rewritten.get('similarity_to_original', 0),
            'latex_polished': final.get('latex_polished', False),
            'last_errors': [],
        }

    except Exception as e:
        t_total = time.time() - t_start
        logger.error(
            f"[3Stage] FAILED ({t_total:.1f}s): {e}",
            exc_info=True
        )

        _log_3stage(
            olympiad_slug=olympiad_slug,
            round_key=round_key,
            class_level=class_level,
            success=False,
            user_id=user_id,
        )

        return {
            'success': False,
            'task': None,
            'attempts': 0,
            'stage1_source': None,
            'similarity': 0,
            'latex_polished': False,
            'last_errors': [str(e)],
        }


def _log_3stage(
    olympiad_slug: str,
    round_key: str,
    class_level: int,
    success: bool,
    stage1_time: float = 0,
    stage2_time: float = 0,
    stage2_attempts: int = 0,
    stage3_called: bool = False,
    similarity: float = 0,
    user_id: Optional[int] = None,
) -> None:
    """Логирует результат 3-stage генерации."""
    try:
        from models import db, OlympiadGenerationLog
        log_entry = OlympiadGenerationLog(
            olympiad_slug=olympiad_slug,
            round_key=round_key,
            class_level=class_level,
            attempts=stage2_attempts,
            success=1 if success else 0,
            errors_json=json.dumps({
                'pipeline': '3stage',
                'stage1_time_ms': int(stage1_time * 1000),
                'stage2_time_ms': int(stage2_time * 1000),
                'stage2_attempts': stage2_attempts,
                'stage3_called': stage3_called,
                'similarity_score': round(similarity, 4),
            }, ensure_ascii=False),
            user_id=user_id,
            created_at=datetime.utcnow(),
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        logger.warning(f"Не удалось записать лог 3stage: {e}")
