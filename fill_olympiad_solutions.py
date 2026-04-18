"""
Скрипт для генерации авторских решений олимпиадных задач
Использует асинхронные запросы к DeepSeek API
"""
import asyncio
import json
import sys
import os
from typing import List, Dict
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.deepseek_client import DeepSeekClient

# Настройки
BATCH_SIZE = 5  # Количество одновременных запросов
MAX_TASKS = 10  # None = все задачи, или число для тестирования

def load_olympiads():
    """Загрузить базу олимпиад"""
    try:
        from olympiads import OLYMPIADS_DB
        return OLYMPIADS_DB
    except ImportError:
        print("[ERROR] Ne udalos importirovat olympiads.py")
        sys.exit(1)

def count_tasks_without_solutions(olympiads_db):
    """Подсчитать задачи без решений"""
    count = 0
    for combo in olympiads_db:
        for problem in combo.get('problems', []):
            solution = problem.get('solution', '').strip()
            if not solution or solution == 'ч.т.д.' or len(solution) < 50:
                count += 1
    return count

async def generate_solution(client: DeepSeekClient, problem_text: str, combo_id: int, problem_num: int) -> Dict:
    """
    Генерировать решение для одной задачи
    
    Returns:
        dict: {'combo_id': int, 'problem_num': int, 'solution': str, 'success': bool}
    """
    system_prompt = """Ты - эксперт по олимпиадной математике.

Найди в своей базе знаний или вспомни официальное, КРАТКОЕ АВТОРСКОЕ решение для следующей олимпиадной задачи.

КРИТИЧЕСКИЕ ПРАВИЛА ОФОРМЛЕНИЯ (LaTeX):
1. Всю математику оборачивай в \\\\( ... \\\\) для инлайн и \\\\[ ... \\\\] для блоков
2. ЗАПРЕЩЕНО использовать юникод ², ³, √ или ^ вне LaTeX!
3. Дроби ТОЛЬКО через \\\\frac{}{}, корни ТОЛЬКО через \\\\sqrt{}
4. Знаки умножения: \\\\cdot (не * и не x)
5. СИСТЕМЫ УРАВНЕНИЙ: Используй \\\\begin{cases} ... \\\\end{cases}

ВАЖНО ДЛЯ JSON: В JSON все обратные слэши должны быть ДВОЙНЫМИ!
Пример: "\\\\( x^2 \\\\)" в JSON, чтобы после парсинга получилось "\\( x^2 \\)"

ПРАВИЛА РЕШЕНИЯ:
1. НЕ ПИШИ ДЛИННЫЕ ВЫЧИСЛЕНИЯ. Выдай ровно ту идею, которая была задумана авторами.
2. Решение должно быть КРАТКИМ (3-5 предложений максимум).
3. Если задача на доказательство - дай ключевую идею доказательства.

Верни ТОЛЬКО JSON:
{
  "author_solution": "Текст решения с ДВОЙНЫМИ слэшами для LaTeX"
}"""
    
    user_prompt = f"""Олимпиадная задача:

{problem_text}

Найди или вспомни авторское решение этой задачи. Оформи его с правильным LaTeX."""
    
    try:
        response = client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,  # Низкая температура для точности
            max_tokens=2000
        )
        
        # Парсим JSON
        response_text = response.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        # Извлекаем JSON
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)
        
        # НЕ экранируем слэши - они нужны для LaTeX!
        # json.loads() корректно обрабатывает \( и \frac
        data = json.loads(response_text)
        solution = data.get('author_solution', '')
        
        return {
            'combo_id': combo_id,
            'problem_num': problem_num,
            'solution': solution,
            'success': True
        }
        
    except Exception as e:
        print(f"[ERROR] Combo {combo_id}, Problem {problem_num}: {e}")
        return {
            'combo_id': combo_id,
            'problem_num': problem_num,
            'solution': '',
            'success': False
        }

async def process_batch(client: DeepSeekClient, tasks: List[Dict]) -> List[Dict]:
    """Обработать пачку задач асинхронно"""
    # Создаем задачи для asyncio
    coroutines = []
    for task in tasks:
        # Имитируем асинхронность через синхронные вызовы с задержкой
        coroutines.append(generate_solution(
            client,
            task['text'],
            task['combo_id'],
            task['problem_num']
        ))
    
    # Запускаем параллельно (на самом деле последовательно, т.к. DeepSeek API синхронный)
    results = []
    for i, coro in enumerate(coroutines):
        print(f"  [{i+1}/{len(coroutines)}] Generacija reshenija...")
        result = await coro
        results.append(result)
        # Небольшая задержка между запросами
        if i < len(coroutines) - 1:
            await asyncio.sleep(1)
    
    return results

def update_olympiads_file(olympiads_db, updates: List[Dict]):
    """Обновить файл olympiads.py с новыми решениями"""
    updated_count = 0
    
    for update in updates:
        if not update['success']:
            continue
        
        combo_id = update['combo_id']
        problem_num = update['problem_num']
        solution = update['solution']
        
        # Находим комбо и задачу
        combo = next((c for c in olympiads_db if c.get('id') == combo_id), None)
        if not combo:
            continue
        
        problems = combo.get('problems', [])
        problem = next((p for p in problems if p.get('num') == problem_num), None)
        if not problem:
            continue
        
        # Обновляем решение
        problem['solution'] = solution
        updated_count += 1
    
    return updated_count

def save_olympiads(olympiads_db):
    """Сохранить обновленную базу олимпиад"""
    output_file = 'olympiads_with_solutions.py'
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# -*- coding: utf-8 -*-\n")
        f.write("# Baza olimpiad s avtorskimi reshenijami\n\n")
        f.write("OLYMPIADS_DB = ")
        f.write(repr(olympiads_db))
    
    print(f"\n[SAVE] Obnovlennaja baza sohranena v {output_file}")
    print(f"[INFO] Zamenite olympiads.py na olympiads_with_solutions.py")
    print(f"       Komanda: move olympiads_with_solutions.py olympiads.py")

async def main():
    print("="*80)
    print("GENERATSIJA AVTORSKIH RESHENIJ DLJA OLIMPIADNYH ZADACH")
    print("="*80)
    
    # Загружаем базу
    olympiads_db = load_olympiads()
    print(f"[INFO] Zagruzheno probnikov: {len(olympiads_db)}")
    
    # Собираем задачи без решений
    tasks_to_process = []
    for combo in olympiads_db:
        combo_id = combo.get('id')
        for problem in combo.get('problems', []):
            solution = problem.get('solution', '').strip()
            # Считаем задачу без решения, если решение пустое или слишком короткое
            if not solution or solution == 'ч.т.д.' or len(solution) < 50:
                tasks_to_process.append({
                    'combo_id': combo_id,
                    'problem_num': problem.get('num'),
                    'text': problem.get('text', '')
                })
    
    total_tasks = len(tasks_to_process)
    print(f"[INFO] Najdeno zadach bez reshenij: {total_tasks}")
    
    if MAX_TASKS:
        tasks_to_process = tasks_to_process[:MAX_TASKS]
        print(f"[INFO] Ogranichenie: obrabotaem tolko {MAX_TASKS} zadach")
    
    if not tasks_to_process:
        print("[INFO] Vse zadachi uzhe imejut reshenija!")
        return
    
    # Инициализируем клиент
    client = DeepSeekClient()
    
    # Обрабатываем пачками
    all_updates = []
    processed = 0
    
    for i in range(0, len(tasks_to_process), BATCH_SIZE):
        batch = tasks_to_process[i:i+BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(tasks_to_process) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f"\n[BATCH {batch_num}/{total_batches}] Obrabotka {len(batch)} zadach...")
        
        results = await process_batch(client, batch)
        all_updates.extend(results)
        
        # Статистика
        successful = sum(1 for r in results if r['success'])
        processed += len(batch)
        
        print(f"[STATS] Obrabotano: {processed}/{len(tasks_to_process)}")
        print(f"[STATS] Uspeshno v etoj pachke: {successful}/{len(batch)}")
        
        # Показываем пример решения
        for result in results:
            if result['success'] and result['solution']:
                solution_preview = result['solution'][:150]
                print(f"[EXAMPLE] Combo {result['combo_id']}, Problem {result['problem_num']}:")
                print(f"          {solution_preview}...")
                break
    
    # Обновляем файл
    print(f"\n[UPDATE] Obnovlyaem fajl olympiads.py...")
    updated_count = update_olympiads_file(olympiads_db, all_updates)
    print(f"[SUCCESS] Obnovleno reshenij: {updated_count}")
    
    # Сохраняем
    save_olympiads(olympiads_db)
    
    print("\n" + "="*80)
    print(f"[DONE] Obrabotano zadach: {processed}")
    print(f"[DONE] Uspeshno sgenerirovan reshenij: {sum(1 for u in all_updates if u['success'])}")
    print("="*80)

if __name__ == '__main__':
    asyncio.run(main())
