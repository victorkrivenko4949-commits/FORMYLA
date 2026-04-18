"""
Тест: Проверка нижних индексов в LaTeX
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.deepseek_client import DeepSeekClient
import json

client = DeepSeekClient()

system_prompt = r"""Ты - профессиональный составитель математических задач.

ПРАВИЛО ДЛЯ НИЖНИХ ИНДЕКСОВ:
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать индексы слитно как обычный текст (p1, pn, xi)!
Ты ОБЯЗАН использовать символ подчеркивания _ строго внутри математического блока \( ... \).
❌ ПЛОХО: p1, pn, x_i (как текст), xi
✅ ОТЛИЧНО: \( p_1 \), \( p_n \), \( x_i \)
ВАЖНО: Если индекс из нескольких символов, он ОБЯЗАТЕЛЬНО в фигурных скобках!
✅ ОТЛИЧНО: \( a_{n+1} \), \( y_{i,j} \), \( x_{max} \)

В JSON используй ДВОЙНЫЕ слэши: "\\\\( x_1 \\\\)"

Верни ТОЛЬКО JSON:
{
  "text": "Условие"
}"""

user_prompt = """Сгенерируй задачу про последовательность для 9 класса.

Условие должно содержать: "Дана последовательность x1, x2, x3, ..., xn, xn+1"

ОБЯЗАТЕЛЬНО используй правильные нижние индексы с подчеркиванием!"""

print("="*80)
print("TEST: Nizhnie indeksy")
print("="*80)

response = client.generate(
    prompt=user_prompt,
    system_prompt=system_prompt,
    temperature=0.5,
    max_tokens=800
)

print("\n[RAW RESPONSE]:")
print(response)
print("\n" + "="*80)

# Проверки
checks = {
    'x_1': 'x_1' in response or 'x_{1}' in response,
    'x_n': 'x_n' in response or 'x_{n}' in response,
    'x_{n+1}': 'x_{n+1}' in response or 'x_{n + 1}' in response,
    'Ploho x1': 'x1' in response and 'x_1' not in response,
    'Ploho xn': 'xn' in response and 'x_n' not in response
}

print("\n[CHECKS]:")
print(f"[{'OK' if checks['x_1'] else 'FAIL'}] x_1 najdeno: {checks['x_1']}")
print(f"[{'OK' if checks['x_n'] else 'FAIL'}] x_n najdeno: {checks['x_n']}")
print(f"[{'OK' if checks['x_{n+1}'] else 'FAIL'}] x_{{n+1}} najdeno: {checks['x_{n+1}']}")
print(f"[{'FAIL' if checks['Ploho x1'] else 'OK'}] Ploho x1 (bez _): {checks['Ploho x1']}")
print(f"[{'FAIL' if checks['Ploho xn'] else 'OK'}] Ploho xn (bez _): {checks['Ploho xn']}")

if checks['x_1'] and checks['x_n'] and not checks['Ploho x1'] and not checks['Ploho xn']:
    print("\n[SUCCESS] OTLICHNO! Vse indeksy pravilnye!")
else:
    print("\n[FAIL] Est problemy s indeksami")

print("="*80)
