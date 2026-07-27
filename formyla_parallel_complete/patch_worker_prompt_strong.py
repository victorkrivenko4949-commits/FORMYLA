from pathlib import Path
import re

p = Path("deepseek_worker.py")
text = p.read_text(encoding="utf-8")

new_make_prompt = r'''def make_prompt(job):
    method = job.get('method_code') or 'GEN'
    grade = job.get('grade')
    diff = job.get('difficulty')
    theme = job.get('theme') or ''
    subtopic = job.get('subtopic') or ''
    task_id = job.get('id') or f"{grade}-{method}-L{diff}-{job.get('job_id','gen')}"
    quality = job.get('quality_target', 'соответствие уровню, корректность ответа и решения')

    l8_rules = ""
    if int(diff) >= 8:
        l8_rules = """
Для L8:
- уровень финала/последних задач сильной олимпиады;
- запрещены одношаговые задачи на прямую формулу;
- нужна неочевидная идея, несколько шагов и доказательство единственности/оптимальности/невозможности;
- ответ должен быть однозначным и проверяемым;
- решение должно полностью доказывать ответ.
"""

    common = f"""
Ты генерируешь задачу для базы FORMYLA.

Верни строго один JSON-объект без markdown и без текста вне JSON.

Обязательные поля:
id, grade, method_code, difficulty, task_text, correct_answer, solution, theme, subtopic, method.

Параметры:
id: {task_id}
grade: {grade}
method_code: {method}
difficulty: {diff}
theme: {theme}
subtopic: {subtopic}
method: {method}

Требование к качеству:
{quality}
{l8_rules}

Запреты:
- не используй фразы “не удалось”, “условие противоречиво”, “решение не найдено”, “заменим задачу”;
- не создавай противоречивые условия;
- не оставляй placeholder-ответы;
- не используй markdown;
- LaTeX пиши внутри строк через $...$;
- все поля JSON должны быть валидными строками/числами без обрыва кавычек.

Финальный JSON должен иметь такой вид:
{{
  "id": "{task_id}",
  "grade": {grade},
  "method_code": "{method}",
  "difficulty": {diff},
  "task_text": "...",
  "correct_answer": "...",
  "solution": "...",
  "theme": "{theme}",
  "subtopic": "{subtopic}",
  "method": "{method}"
}}
"""

    if job.get('mode') == 'fill_missing':
        return common + """

Сгенерируй НОВУЮ оригинальную корректную задачу строго по указанной теме, подтеме, классу и уровню.
"""

    return common + f"""

Замени плохую задачу новой корректной задачей с тем же id.
Причины замены: {job.get('reasons', '')}
Сохрани тот же id: {task_id}
"""
'''

text2 = re.sub(
    r"def make_prompt\(job\):\n.*?\ndef extract_json\(text\):",
    new_make_prompt + "\ndef extract_json(text):",
    text,
    flags=re.S
)

if text2 == text:
    print("WARN: make_prompt block not replaced")
else:
    p.write_text(text2, encoding="utf-8")
    print("OK: deepseek_worker.py prompt upgraded")
