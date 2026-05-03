#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Последовательная генерация 8, 9, 6 классов (после 10 класса)."""
import subprocess, sys, os, time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(BASE_DIR, 'scripts', 'generate_grade.py')
GRADES = [8, 9, 6]


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'{ts} [RUN] {msg}', flush=True)


def main():
    log(f'Запуск генерации для классов: {GRADES}')
    for grade in GRADES:
        plan = os.path.join(BASE_DIR, 'data', 'audit', f'grade{grade}_gen_plan.json')
        if not os.path.exists(plan):
            log(f'План для {grade} класса не найден, пропускаю')
            continue
        log(f'=== Генерация {grade} класса ===')
        try:
            result = subprocess.run(
                [sys.executable, SCRIPT, str(grade)],
                cwd=BASE_DIR,
                timeout=7200
            )
            log(f'=== {grade} класс завершён (код: {result.returncode}) ===')
        except subprocess.TimeoutExpired:
            log(f'!!! {grade} класс: таймаут')
        except Exception as e:
            log(f'!!! {grade} класс: ошибка {e}')
        time.sleep(10)
    log('=== ВСЕ ЗАВЕРШЕНО ===')


if __name__ == '__main__':
    main()
