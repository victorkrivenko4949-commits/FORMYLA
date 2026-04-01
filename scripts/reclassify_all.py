# -*- coding: utf-8 -*-
"""
Переклассификация ВСЕХ задач через DeepSeek API
Каждая задача получит правильный класс и уровень сложности
"""
import sys
import os
import json
import shutil
import codecs
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == 'win32':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

from problems import PROBLEMS_DB
from ai.deepseek_client import DeepSeekClient

# Системный промпт
SYSTEM_PROMPT = """Ты — эксперт по классификации математических задач.

Проанализируй задачу и определи:
1. Класс (grade): 5, 6, 7, 8, 9, 10 или 11
2. Уровень сложности (difficulty): от 1 до 10

Шкала сложности:
1-2: Простые задачи для 5-6 класса
3-4: Задачи среднего уровня для 6-7 класса
5-6: Сложные школьные задачи для 7-9 класса
7-8: Олимпиадные задачи для 9-10 класса
9-10: Сложные олимпиадные задачи для 10-11 класса

Отвечай ТОЛЬКО JSON: {"grade": 7, "difficulty": 5}"""

print("="*70)
print("Переклассификация всех задач через DeepSeek API")
print("="*70)

# Инициализация DeepSeek
try:
    client = DeepSeekClient()
    print("✓ DeepSeek client initialized")
except Exception as e:
    print(f"❌ Failed to initialize DeepSeek: {e}")
    sys.exit(1)

# Создаем бэкап
print("\n💾 Создание бэкапа...")
shutil.copy2("problems.py", "problems.py.before_reclassify.bak")
print("✓ Бэкап: problems.py.before_reclassify.bak")

# Переклассифицируем
print(f"\n🔄 Переклассификация {len(PROBLEMS_DB)} задач...")
print("Это займет ~6 часов (3 сек на задачу)")

reclassified = 0
failed = 0

for i, problem in enumerate(PROBLEMS_DB, 1):
    if i % 50 == 0:
        print(f"[{i}/{len(PROBLEMS_DB)}] Обработано...")
        # Сохраняем checkpoint
        with open("problems.py", 'w', encoding='utf-8') as f:
            f.write("# -*- coding: utf-8 -*-\n")
            f.write(f"# База задач — {len(PROBLEMS_DB)} задач (переклассификация)\n\n")
            f.write("PROBLEMS_DB = ")
            json.dump(PROBLEMS_DB, f, ensure_ascii=False, indent=0)
            f.write("\n")
    
    text = problem.get('text', '')
    if not text:
        failed += 1
        continue
    
    try:
        prompt = f"Проанализируй задачу и определи класс и сложность:\n\n{text[:500]}"
        response = client.generate(prompt, SYSTEM_PROMPT, temperature=0.1, max_tokens=50)
        
        # Parse JSON
        response = response.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(response)
        
        if 'grade' in data and 'difficulty' in data:
            problem['grade'] = data['grade']
            problem['difficulty'] = data['difficulty']
            reclassified += 1
        else:
            failed += 1
            
    except Exception as e:
        failed += 1
    
    time.sleep(1)  # Rate limiting

# Сохраняем финальную версию
print(f"\n💾 Сохранение финальной версии...")
with open("problems.py", 'w', encoding='utf-8') as f:
    f.write("# -*- coding: utf-8 -*-\n")
    f.write(f"# База задач — {len(PROBLEMS_DB)} задач\n")
    f.write("# Переклассифицировано через DeepSeek API\n\n")
    f.write("PROBLEMS_DB = ")
    json.dump(PROBLEMS_DB, f, ensure_ascii=False, indent=0)
    f.write("\n")

print("✓ Сохранено")

print("\n" + "="*70)
print("✅ ПЕРЕКЛАССИФИКАЦИЯ ЗАВЕРШЕНА!")
print("="*70)
print(f"\nУспешно: {reclassified} задач")
print(f"Ошибок: {failed} задач")
