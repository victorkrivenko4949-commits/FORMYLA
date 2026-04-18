"""
Тест: Проверка что нейросеть использует \sqrt{} с фигурными скобками
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.deepseek_client import DeepSeekClient
import json

client = DeepSeekClient()

system_prompt = r"""Ты - профессиональный составитель математических задач.

КРИТИЧЕСКИ ВАЖНО ПРО КОРНИ:
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать √50, sqrt(50) или \sqrt 50 (без фигурных скобок)!
Ты ОБЯЗАН использовать команду \sqrt СТРОГО с фигурными скобками {}!
❌ ПЛОХО: √50, sqrt(50), \sqrt 50, \sqrt 4
✅ ОТЛИЧНО: \( \sqrt{50} \), \( \sqrt{4} \), \( \sqrt{x^2 + y^2} \)

Если под корнем длинное выражение, оно ВСЁ должно быть внутри фигурных скобок!

В JSON используй ДВОЙНЫЕ слэши: "\\\\( \\\\sqrt{50} \\\\)"

Верни ТОЛЬКО JSON:
{
  "text": "Условие",
  "answer": "Ответ"
}"""

user_prompt = """Сгенерируй задачу: "Упростите выражение с корнями: корень из 50 плюс корень из 32 минус корень из 8"

ОБЯЗАТЕЛЬНО используй \\\\sqrt{} с фигурными скобками для КАЖДОГО корня!"""

print("="*80)
print("TEST: Korni s figurnymi skobkami")
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
has_sqrt_braces = '\\sqrt{' in response or '\\\\sqrt{' in response
has_sqrt_no_braces = '\\sqrt ' in response or 'sqrt(' in response
has_unicode = '√' in response

print("\n[CHECKS]:")
print(f"[{'OK' if has_sqrt_braces else 'FAIL'}] sqrt{{}} najdeno: {has_sqrt_braces}")
print(f"[{'FAIL' if has_sqrt_no_braces else 'OK'}] sqrt bez {{}} (PLOHO): {has_sqrt_no_braces}")
print(f"[{'FAIL' if has_unicode else 'OK'}] Unicode √ (PLOHO): {has_unicode}")

if has_sqrt_braces and not has_sqrt_no_braces and not has_unicode:
    print("\n[SUCCESS] OTLICHNO! Vse korni s figurnymi skobkami!")
else:
    print("\n[FAIL] Est problemy s formatom kornej")
