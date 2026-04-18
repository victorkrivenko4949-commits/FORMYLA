"""
Тест генерации задач с правильным LaTeX форматированием
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.deepseek_client import DeepSeekClient

def test_latex_formatting():
    """Тестируем, что нейросеть генерирует задачи с правильным LaTeX"""
    
    print("="*80)
    print("TEST: Generatsija zadachi s LaTeX formatami")
    print("="*80)
    
    deepseek = DeepSeekClient()
    
    system_prompt = r"""Ты - профессиональный составитель математических задач.

КРИТИЧЕСКИЕ ПРАВИЛА ОФОРМЛЕНИЯ МАТЕМАТИКИ (LaTeX):
1. ВЕСЬ математический текст оборачивай в \( ... \) для строчных формул
2. ЗАПРЕЩЕНО использовать ^ без LaTeX! Используй \( x^2 \)
3. ЗАПРЕЩЕНО использовать / для дробей! Используй \( \frac{1}{2} \)
4. ЗАПРЕЩЕНО писать sqrt! Используй \( \sqrt{4} \)
5. Знаки умножения: \( \cdot \)

ВЕРНИ ТОЛЬКО JSON:
{
  "text": "Условие с формулами в LaTeX",
  "answer": "Ответ",
  "solution": "Решение с формулами в LaTeX"
}"""
    
    user_prompt = """Сгенерируй задачу для 8 класса с дробями, степенями и корнями.
Например: "Найдите значение выражения, содержащего дробь 3/4, степень 2^3 и корень sqrt(16)".
ОБЯЗАТЕЛЬНО используй LaTeX форматирование!"""
    
    print("\n[REQUEST] Otpravlyaem zapros k DeepSeek...")
    
    response = deepseek.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        temperature=0.7,
        max_tokens=1000
    )
    
    print("\n[RESPONSE] Syroj otvet ot nejroseti:")
    print("="*80)
    print(response)
    print("="*80)
    
    # Проверяем наличие LaTeX команд
    latex_checks = {
        r'\frac': '\\frac' in response,
        r'\sqrt': '\\sqrt' in response,
        r'\(': '\\(' in response,
        r'x^': 'x^' in response or '^' in response
    }
    
    print("\n[CHECKS] Proverka LaTeX komand:")
    print("="*80)
    for command, found in latex_checks.items():
        status = "[OK]" if found else "[FAIL]"
        print(f"{status} {command}: {'Najdeno' if found else 'NE najdeno'}")
    
    # Проверяем ОТСУТСТВИЕ плохих паттернов
    bad_patterns = {
        'sqrt(': 'sqrt(' in response and '\\sqrt' not in response,
        'x/y bez LaTeX': '/' in response and '\\frac' not in response,
        '^ bez LaTeX': '^' in response and '\\(' not in response
    }
    
    print("\n[CHECKS] Proverka OTSUTSTVIJA ploho formatirovannyh formul:")
    print("="*80)
    for pattern, found in bad_patterns.items():
        status = "[FAIL]" if found else "[OK]"
        print(f"{status} {pattern}: {'Obnaruzheno (PLOHO!)' if found else 'Net (HOROSHO!)'}")
    
    print("\n" + "="*80)
    if all(latex_checks.values()) and not any(bad_patterns.values()):
        print("[SUCCESS] Test PROJDEN! Nejroset ispolzuet pravilnyj LaTeX!")
    else:
        print("[WARNING] Test NE PROJDEN. Nuzhno usilit prompt.")
    print("="*80)

if __name__ == '__main__':
    try:
        test_latex_formatting()
    except Exception as e:
        print(f"\n[ERROR] Oshibka: {e}")
        import traceback
        traceback.print_exc()
