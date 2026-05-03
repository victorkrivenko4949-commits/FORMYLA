#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Цепочка генерации: ждёт завершения 11 класса, потом запускает 10, 8, 9, 6.
Запускать в отдельном терминале!
"""
import json, time, os, sys, subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(BASE_DIR, 'scripts', 'generate_grade.py')
CHECKPOINT_11 = os.path.join(BASE_DIR, 'data', 'audit', 'gen_progress_grade11.json')

GRADES_TO_RUN = [10, 8, 9, 6]


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'{ts} [CHAIN] {msg}', flush=True)


def wait_for_grade11():
    """Ждём пока 11 класс завершит генерацию (проверяем чекпоинт)."""
    log('Ожидаю завершения генерации 11 класса...')
    target = 1050
    while True:
        try:
            done = json.load(open(CHECKPOINT_11, encoding='utf-8'))
            total = sum(done.values())
            log(f'  11 класс: {total}/{target} задач')
            if total >= target * 0.95:  # 95% = считаем завершённым (ошибки парсинга)
                log(f'  11 класс достаточно заполнен ({total} задач)')
                return total
        except:
            pass
        time.sleep(120)  # Проверяем каждые 2 минуты


def run_grade(grade):
    plan_file = os.path.join(BASE_DIR, 'data', 'audit', f'grade{grade}_gen_plan.json')
    if not os.path.exists(plan_file):
        log(f'!!! План для {grade} класса не найден, пропускаю')
        return

    log(f'=== Запускаю генерацию {grade} класса ===')
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, str(grade)],
            cwd=BASE_DIR,
            timeout=7200  # 2 часа максимум
        )
        log(f'=== {grade} класс завершён (код: {result.returncode}) ===')
    except subprocess.TimeoutExpired:
        log(f'!!! {grade} класс: таймаут 2 часа, прерываю')
    except Exception as e:
        log(f'!!! {grade} класс: ошибка {e}')


def main():
    log('СТАРТ ЦЕПОЧКИ ГЕНЕРАЦИИ')
    log(f'Классы для генерации: {GRADES_TO_RUN}')

    # Ждём 11 класс
    wait_for_grade11()
    time.sleep(30)  # Пауза после 11 класса

    # Запускаем остальные
    for grade in GRADES_TO_RUN:
        run_grade(grade)
        time.sleep(10)

    log('=== ВСЯ ЦЕПОЧКА ЗАВЕРШЕНА ===')


if __name__ == '__main__':
    main()
