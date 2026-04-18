"""
Скрипт для получения оригинальных авторских решений олимпиадных задач
Использует LLM для поиска решений в базе знаний
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from olympiads import OLYMPIADS_DB
from ai.deepseek_client import DeepSeekClient
import json
import time

def fetch_original_solution(client, problem_text, olympiad_name, year, grade):
    """Получить оригинальное решение из базы знаний LLM"""
    
    system_prompt = r"""Ты — агрегатор олимпиадной математики с доступом к базе знаний problems.ru, mccme.ru и официальным архивам.

Твоя задача: найти ТОЧНОЕ, ОФИЦИАЛЬНОЕ АВТОРСКОЕ решение для этой известной олимпиадной задачи.

КРИТИЧЕСКИ ВАЖНО:
- НИЧЕГО НЕ ВЫДУМЫВАЙ ОТ СЕБЯ
- Если задача имеет классическое решение в 2-3 строчки — выдай именно его
- Ищи решение из официальных источников: problems.ru, mccme.ru, архивы ВсОШ, Турнира Городов, ММО
- Если не можешь найти точное решение, честно признайся

ВЕРНИ ТОЛЬКО JSON:
{
  "original_solution": "Текст оригинального авторского решения (БЕЗ LaTeX пока, просто текст)"
}

Если не можешь найти точное решение, верни: {"original_solution": "NOT_FOUND"}"""
    
    user_prompt = f"""Найди оригинальное авторское решение этой задачи:

Олимпиада: {olympiad_name}
Год: {year}
Класс: {grade}

Условие задачи:
{problem_text}

Верни ТОЧНОЕ авторское решение из официальных источников."""
    
    try:
        response = client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=3000
        )
        
        # Парсим
        response_text = response.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)
        
        data = json.loads(response_text)
        solution = data.get('original_solution', 'NOT_FOUND')
        
        if solution == 'NOT_FOUND':
            return None
        
        return solution
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return None

def format_solution_latex(client, solution_text):
    """Отформатировать решение в LaTeX (только форматирование, не меняя суть)"""
    
    system_prompt = r"""Ты — LaTeX-редактор для математических текстов.

Перед тобой текст официального авторского решения олимпиадной задачи.

ТВОЯ ЗАДАЧА: ТОЛЬКО форматирование математики в строгий LaTeX.
НИ В КОЕМ СЛУЧАЕ не меняй слова, логику или ход решения автора!

ЖЕСТКИЕ ПРАВИЛА ФОРМАТИРОВАНИЯ:
1. Инлайн-формулы: строго в \\( ... \\) (например, \\( x=5 \\))
2. Блочные формулы (системы, длинные уравнения): строго в \\[ ... \\]
3. Дроби: ТОЛЬКО \\frac{числитель}{знаменатель} (запрещен символ /)
4. Корни: ТОЛЬКО \\sqrt{подкоренное} (с фигурными скобками)
5. Степени и индексы: ТОЛЬКО x^2 и p_n внутри \\( ... \\). Если индекс сложный — в скобках: \\( a_{n+1} \\)
6. ВСЕ числа, переменные и формулы в тексте должны быть в \\( ... \\)

ПРИМЕРЫ ПРАВИЛЬНОГО ФОРМАТИРОВАНИЯ:
- "Пусть \\( n = 5 \\)" (не "Пусть n = 5")
- "Тогда \\( x^2 + y^2 = z^2 \\)" (не "x² + y² = z²")
- "Дробь \\( \\frac{a+b}{2} \\)" (не "дробь (a+b)/2")
- "Корень \\( \\sqrt{2} \\)" (не "корень √2")

В JSON используй ДВОЙНЫЕ слэши (\\\\( вместо \\()!

Верни ТОЛЬКО JSON:
{
  "formatted_solution": "Решение с идеальным LaTeX форматированием"
}"""
    
    user_prompt = f"""Отформатируй это авторское решение в LaTeX (НЕ МЕНЯЙ ТЕКСТ, только добавь LaTeX разметку):

{solution_text}"""
    
    try:
        response = client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
            max_tokens=4000
        )
        
        # Парсим
        response_text = response.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)
        
        data = json.loads(response_text)
        return data.get('formatted_solution', solution_text)
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return solution_text

def main():
    print("="*80)
    print("🔍 МАССОВЫЙ ПОИСК ОРИГИНАЛЬНЫХ РЕШЕНИЙ - ВСЯ БАЗА")
    print("="*80)
    
    client = DeepSeekClient()
    
    # МАССОВЫЙ ЗАПУСК - БЕЗ ЛИМИТА
    test_limit = None  # Обрабатываем ВСЕ задачи
    processed = 0
    found = 0
    skipped = 0
    batch_count = 0
    BATCH_SIZE = 5
    SAVE_EVERY = 10
    
    # Подсчёт общего количества задач
    total_problems = sum(len(combo.get('problems', [])) for combo in OLYMPIADS_DB)
    print(f"\n📊 Всего задач в базе: {total_problems}")
    print(f"🎯 Режим: МАССОВАЯ ОБРАБОТКА (без лимита)")
    print(f"📦 Размер батча: {BATCH_SIZE} задач")
    print(f"💾 Сохранение каждые: {SAVE_EVERY} задач")
    print(f"\n{'='*80}\n")
    
    for combo in OLYMPIADS_DB:
        olympiad_name = combo.get('olympiad_title', combo.get('olympiad', ''))
        year = combo.get('year', '')
        grade = combo.get('grade', '')
        
        for problem in combo.get('problems', []):
            processed += 1
            problem_text = problem.get('text', '')
            current_solution = problem.get('solution', '')
            
            # Пропускаем, если уже есть хорошее решение (>500 символов с LaTeX)
            if current_solution and len(current_solution) > 500 and '\\(' in current_solution:
                skipped += 1
                if processed % 50 == 0:
                    print(f"⏭️  Пропущено (уже есть): {olympiad_name} {year}, задача #{problem.get('num')}")
                continue
            
            # Прогресс-бар
            progress_pct = (processed / total_problems) * 100
            print(f"\r🔄 [{processed}/{total_problems}] {progress_pct:.1f}% | Найдено: {found} | Пропущено: {skipped}", end='', flush=True)
            
            # Каждую 10-ю задачу показываем подробно
            if processed % 10 == 0:
                print(f"\n\n📝 Обрабатываем: {olympiad_name} {year}, {grade} класс, #{problem.get('num')}")
            
            # ШАГ 1: Поиск
            original_solution = fetch_original_solution(client, problem_text, olympiad_name, year, grade)
            
            if not original_solution:
                problem['solution_status'] = 'not_found'  # Помечаем как не найденное
                continue
            
            found += 1
            
            # ШАГ 2: Форматирование
            formatted_solution = format_solution_latex(client, original_solution)
            problem['solution'] = formatted_solution
            problem['solution_status'] = 'found'
            
            # Батчинг: пауза каждые BATCH_SIZE задач
            batch_count += 1
            if batch_count >= BATCH_SIZE:
                time.sleep(2)  # Пауза между батчами
                batch_count = 0
            
            # Безопасное сохранение каждые SAVE_EVERY задач
            if found % SAVE_EVERY == 0:
                print(f"\n\n💾 Сохранение прогресса... (найдено {found} решений)")
                with open('olympiads_with_original_solutions.py', 'w', encoding='utf-8') as f:
                    f.write('# -*- coding: utf-8 -*-\n')
                    f.write('# Baza olimpiad s originalnymi reshenijami\n\n')
                    f.write('OLYMPIADS_DB = ')
                    f.write(repr(OLYMPIADS_DB))
                print(f"✅ Прогресс сохранён!")
    
    # Финальное сохранение
    print(f"\n\n{'='*80}")
    print(f"💾 ФИНАЛЬНОЕ СОХРАНЕНИЕ...")
    with open('olympiads_with_original_solutions.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# Baza olimpiad s originalnymi reshenijami\n\n')
        f.write('OLYMPIADS_DB = ')
        f.write(repr(OLYMPIADS_DB))
    
    print(f"\n{'='*80}")
    print(f"✅ МАССОВАЯ ОБРАБОТКА ЗАВЕРШЕНА!")
    print(f"{'='*80}")
    print(f"📊 ИТОГОВАЯ СТАТИСТИКА:")
    print(f"   Всего задач в базе: {total_problems}")
    print(f"   Обработано: {processed}")
    print(f"   Пропущено (уже есть решение): {skipped}")
    print(f"   Найдено новых решений: {found}")
    print(f"   Не найдено: {processed - skipped - found}")
    print(f"   Успешность поиска: {100*found//(processed-skipped) if (processed-skipped) > 0 else 0}%")
    print(f"\n💾 Результат сохранён в: olympiads_with_original_solutions.py")
    print(f"{'='*80}")

if __name__ == '__main__':
    main()
