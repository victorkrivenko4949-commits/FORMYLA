#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Последовательная генерация задач для всех оставшихся классов.
Запускает generate_grade.py для каждого класса по очереди.
"""
import subprocess, sys, os, time
from datetime import datetime

GRADES = [10, 8, 9, 6]  # Порядок: сначала самый большой дефицит

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(BASE_DIR, 'scripts', 'generate_grade.py')


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'{ts} {msg}', flush=True)


def main():
    log('=== ЗАПУСК ПОСЛЕДОВАТЕЛЬНОЙ ГЕНЕРАЦИИ ===')
    log(f'Классы: {GRADES}')

    for grade in GRADES:
        plan_file = os.path.join(BASE_DIR, 'data', 'audit', f'grade{grade}_gen_plan.json')
        if not os.path.exists(plan_file):
            log(f'!!! План для {grade} класса не найден: {plan_file}')
            log(f'    Пропускаю {grade} класс')
            continue

        log(f'--- Запускаю генерацию {grade} класса ---')
        result = subprocess.run(
            [sys.executable, SCRIPT, str(grade)],
            cwd=BASE_DIR,
            timeout=7200  # 2 часа максимум на класс
        )
        log(f'--- {grade} класс завершён (код: {result.returncode}) ---')
        time.sleep(10)  # Пауза между классами

    log('=== ВСЕ КЛАССЫ ОБРАБОТАНЫ ===')


if __name__ == '__main__':
    main()
