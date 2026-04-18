"""
Генерация задачи с корнями для демонстрации
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai.deepseek_client import DeepSeekClient
import json

client = DeepSeekClient()

system_prompt = r"""Ты - профессиональный составитель математических задач.

КРИТИЧЕСКИЕ ПРАВИЛА ОФОРМЛЕНИЯ (LaTeX):
1. Все формулы в \\( ... \\) для инлайн
2. Корни ТОЛЬКО через \\sqrt{}: \\( \\sqrt{16} \\), \\( \\sqrt{x+1} \\)
3. Дроби ТОЛЬКО через \\frac{}{}: \\( \\frac{1}{2} \\)
4. Степени: \\( x^2 \\)

В JSON используй ДВОЙНЫЕ слэши: "\\\\( \\\\sqrt{16} \\\\)"

Верни ТОЛЬКО JSON:
{
  "text": "Условие",
  "answer": "Ответ",
  "solution": "Решение"
}"""

user_prompt = """Сгенерируй простую задачу для 8 класса на упрощение выражения с корнями.

Пример: "Упростите выражение: корень из 50 плюс корень из 8 минус корень из 18"

ОБЯЗАТЕЛЬНО используй \\\\sqrt{} для всех корней!"""

print("="*80)
print("ZADACHA S KORNJAMI")
print("="*80)

response = client.generate(
    prompt=user_prompt,
    system_prompt=system_prompt,
    temperature=0.7,
    max_tokens=1000
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

print("\n[IDEALNAJA ZADACHA]:")
print("="*80)
print(f"USLOVIE:\n{task['text']}\n")
print(f"OTVET:\n{task['answer']}\n")
print(f"RESHENIE:\n{task['solution']}\n")
print("="*80)

# Сохраним в HTML для просмотра
html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
    <style>
        body {{ font-family: Arial; padding: 40px; background: #0f172a; color: #e2e8f0; }}
        .task {{ background: #1e293b; padding: 30px; border-radius: 12px; margin-bottom: 20px; }}
        h2 {{ color: #38bdf8; }}
    </style>
</head>
<body>
    <h1>Идеальная задача с корнями</h1>
    
    <div class="task">
        <h2>Условие:</h2>
        <p>{task['text']}</p>
    </div>
    
    <div class="task">
        <h2>Ответ:</h2>
        <p>{task['answer']}</p>
    </div>
    
    <div class="task">
        <h2>Решение:</h2>
        <p>{task['solution']}</p>
    </div>
    
    <script>
        document.addEventListener("DOMContentLoaded", function() {{
            renderMathInElement(document.body, {{
                delimiters: [
                    {{left: '\\\\(', right: '\\\\)', display: false}},
                    {{left: '\\\\[', right: '\\\\]', display: true}}
                ],
                throwOnError: false
            }});
        }});
    </script>
</body>
</html>"""

with open('perfect_sqrt_task.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("\n[INFO] Zadacha sohranena v perfect_sqrt_task.html")
print("[INFO] Otkrojte etot fajl v brauzere, chtoby uvidet rendernuju zadachu!")
