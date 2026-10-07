
import argparse, json, os, re, time, hashlib
from pathlib import Path

SYSTEM_RULES = 'Ты генерируешь задачи FORMYLA. Верни только JSON-объект задачи. Поля: id, grade, method_code, difficulty, task_text, correct_answer, solution, theme, subtopic, method. LaTeX только с $, команды экранировать. Уровни: L6=регион, L7=сложный регион, L8=финал/перечневые; нельзя одношаговые остатки/НОД/проценты/делители на L7-L8. Решение должно доказывать ответ.'

def validate_task(t):
    issues=[]
    for f in ['id','grade','method_code','difficulty','task_text','correct_answer','solution','theme','subtopic','method']:
        if f not in t or t[f] in [None,'']: issues.append('missing_'+f)
    s=' '.join(str(t.get(f,'')) for f in ['task_text','correct_answer','solution'])
    if s.count('$')%2: issues.append('odd_dollar')
    bal=0
    for ch in s:
        if ch=='{': bal+=1
        elif ch=='}': bal-=1
        if bal<0: issues.append('brace_order'); break
    if bal!=0: issues.append('brace_balance')
    if t.get('difficulty',0)>=7 and len(str(t.get('solution','')))<260: issues.append('short_solution_high_level')
    bad=['остаток от деления','наибольший общий делитель','сколько натуральных делителей','среднее арифметическое']
    if t.get('difficulty',0)>=7 and any(x in str(t.get('task_text','')).lower() for x in bad): issues.append('too_easy_template')
    return issues

def make_prompt(job):
    if job['mode']=='fill_missing':
        return f"Создай новую задачу для класса {job['grade']}, уровня L{job['difficulty']}, тема: {job['theme']}, подтема: {job['subtopic']}, method_code: {job['method_code']}. Требование: {job.get('quality_target','соответствие уровню')}. Ответ должен быть проверяемым, решение полным."
    return f"Замени плохую задачу id={job['id']} новой задачей того же класса {job['grade']}, уровня L{job['difficulty']}, тема: {job['theme']}, подтема: {job['subtopic']}, method_code: {job.get('method_code')}. Причины замены: {job.get('reasons')}. Сохрани тот же id."

def call_model(prompt, model):
    raise RuntimeError('Подключи здесь вызов API модели: prompt -> JSON задачи. Этот файл готов к 20 параллельным потокам, но API-ключ не хранится в коде.')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--worker', type=int, required=True)
    ap.add_argument('--queue', default='output')
    ap.add_argument('--out', default='output/formyla_parallel/results')
    ap.add_argument('--model', default='gpt-5.5-thinking')
    args=ap.parse_args()
    jobs=json.loads(Path(args.queue, f'formyla_worker_{args.worker:02d}_jobs.json').read_text(encoding='utf-8'))['jobs']
    Path(args.out).mkdir(parents=True, exist_ok=True)
    out_path=Path(args.out, f'worker_{args.worker:02d}_results.jsonl')
    with out_path.open('w',encoding='utf-8') as out:
        for job in jobs:
            rec={'job':job,'prompt':make_prompt(job),'status':'pending_api_connection'}
            out.write(json.dumps(rec,ensure_ascii=False)+'\n')
if __name__=='__main__': main()
