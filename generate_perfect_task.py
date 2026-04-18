"""
Генерация идеальной задачи с правильным LaTeX
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.deepseek_client import DeepSeekClient
import json

def generate_perfect_task():
    """Генерируем идеальную задачу"""
    
    client = DeepSeekClient()
    
    system_prompt = r"""Ты - профессиональный составитель математических задач.

КРИТИЧЕСКИЕ ПРАВИЛА ОФОРМЛЕНИЯ МАТЕМАТИКИ (LaTeX) — ПРИ НАРУШЕНИИ ОТКЛОНЕНО:
1. ВЕСЬ математический текст оборачивай в \\( ... \\) для инлайн и \\[ ... \\] для блоков
2. ЗАПРЕЩЕНО использовать юникод ², ³, √ или ^ вне LaTeX!
3. Дроби ТОЛЬКО через \\frac{}{}, корни ТОЛЬКО через \\sqrt{}
4. Знаки умножения: \\cdot (не * и не x)
5. СИСТЕМЫ УРАВНЕНИЙ: Используй \\begin{cases} ... \\end{cases}

ВАЖНО ДЛЯ JSON: В JSON все обратные слэши должны быть ДВОЙНЫМИ!
Пример: "\\\\( x^2 \\\\)" в JSON

Верни ТОЛЬКО JSON:
{
  "text": "Условие задачи",
  "answer": "Ответ",
  "solution": "Решение"
}"""
    
    user_prompt = """Сгенерируй красивую задачу для 9 класса на тему "Квадратные уравнения с параметром".

Задача должна содержать:
- Квадратное уравнение с параметром a
- Дроби (используй \\\\frac)
- Корни (используй \\\\sqrt)
- Условие на дискриминант

ОБЯЗАТЕЛЬНО используй правильный LaTeX!"""
    
    print("="*80)
    print("GENERATSIJA IDEALNOJ ZADACHI")
    print("="*80)
    
    response = client.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=1500
    )
    
    print("\n[RAW RESPONSE]:")
    print(response)
    print("\n" + "="*80)
    
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
    
    task = json.loads(response_text)
    
    print("\n[PARSED TASK]:")
    print("="*80)
    print(f"TEXT:\n{task['text']}\n")
    print(f"ANSWER:\n{task['answer']}\n")
    print(f"SOLUTION:\n{task['solution']}\n")
    print("="*80)
    
    # Проверки
    checks = {
        '\\\\frac': '\\\\frac' in response,
        '\\\\sqrt': '\\\\sqrt' in response,
        '\\\\(': '\\\\(' in response,
        'No unicode': not any(c in response for c in ['²', '³', '√'])
    }
    
    print("\n[CHECKS]:")
    for check, passed in checks.items():
        status = "[OK]" if passed else "[FAIL]"
        print(f"{status} {check}")
    
    if all(checks.values()):
        print("\n[SUCCESS] ZADACHA IDEALNA!")
    else:
        print("\n[WARNING] Est problemy")

if __name__ == '__main__':
    generate_perfect_task()
