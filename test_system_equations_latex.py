"""
Тест генерации системы уравнений с правильным LaTeX форматированием
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.deepseek_client import DeepSeekClient

def test_system_equations():
    """Тестируем генерацию системы уравнений"""
    
    print("="*80)
    print("TEST: Generatsija sistemy uravnenij s LaTeX")
    print("="*80)
    
    deepseek = DeepSeekClient()
    
    system_prompt = r"""Ты - профессиональный составитель математических задач.

КРИТИЧЕСКИЕ ПРАВИЛА ОФОРМЛЕНИЯ МАТЕМАТИКИ (LaTeX) — ПРИ НАРУШЕНИИ ОТКЛОНЕНО:
1. ВЕСЬ математический текст оборачивай в \( ... \) для инлайн и \[ ... \] для блоков
2. ЗАПРЕЩЕНО использовать юникод ², ³, √ или ^ вне LaTeX!
3. ЗАПРЕЩЕНО использовать / для дробей! Используй \( \frac{1}{2} \)
4. Знаки умножения: \( \cdot \)
5. СИСТЕМЫ УРАВНЕНИЙ: ОБЯЗАТЕЛЬНО используй \begin{cases} ... \end{cases}
   Пример:
   \[
   \begin{cases}
   x + y = 5 \\
   x - y = 1
   \end{cases}
   \]

ВЕРНИ ТОЛЬКО JSON:
{
  "text": "Условие с системой уравнений в LaTeX",
  "answer": "Ответ",
  "solution": "Решение"
}"""
    
    user_prompt = """Сгенерируй задачу для 9 класса: "Решите систему уравнений".
Система должна содержать 2-3 уравнения с дробями, степенями и корнями.
ОБЯЗАТЕЛЬНО используй окружение \\begin{cases} для системы!"""
    
    print("\n[REQUEST] Otpravlyaem zapros k DeepSeek...")
    
    response = deepseek.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=1500
    )
    
    print("\n[RESPONSE] Syroj otvet ot nejroseti:")
    print("="*80)
    print(response)
    print("="*80)
    
    # Проверяем наличие правильных LaTeX команд
    checks = {
        r'\begin{cases}': '\\begin{cases}' in response,
        r'\end{cases}': '\\end{cases}' in response,
        r'\frac': '\\frac' in response,
        r'\sqrt': '\\sqrt' in response,
        r'\(': '\\(' in response,
        r'\[': '\\[' in response
    }
    
    print("\n[CHECKS] Proverka LaTeX komand:")
    print("="*80)
    for command, found in checks.items():
        status = "[OK]" if found else "[FAIL]"
        print(f"{status} {command}: {'Najdeno' if found else 'NE najdeno'}")
    
    # Проверяем ОТСУТСТВИЕ плохих паттернов
    bad_patterns = {
        'Unicode ²³√': any(c in response for c in ['²', '³', '√']),
        'sqrt( bez LaTeX': 'sqrt(' in response,
        '/ bez \\frac': ('/' in response and '\\frac' not in response),
        '^ bez LaTeX': ('^' in response and '\\(' not in response)
    }
    
    print("\n[CHECKS] Proverka OTSUTSTVIJA ploho formatirovannyh formul:")
    print("="*80)
    for pattern, found in bad_patterns.items():
        status = "[FAIL]" if found else "[OK]"
        print(f"{status} {pattern}: {'Obnaruzheno (PLOHO!)' if found else 'Net (HOROSHO!)'}")
    
    print("\n" + "="*80)
    if checks[r'\begin{cases}'] and checks[r'\end{cases}'] and not any(bad_patterns.values()):
        print("[SUCCESS] Test PROJDEN! Sistema uravnenij v pravilnom LaTeX!")
    else:
        print("[WARNING] Test NE PROJDEN. Nuzhno usilit prompt.")
    print("="*80)

if __name__ == '__main__':
    try:
        test_system_equations()
    except Exception as e:
        print(f"\n[ERROR] Oshibka: {e}")
        import traceback
        traceback.print_exc()
