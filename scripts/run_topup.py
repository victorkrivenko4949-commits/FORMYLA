#!/usr/bin/env python3
"""Top-up: generate remaining tasks for grades 8, 9, 11 sequentially."""
import subprocess, sys, os, time
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(BASE_DIR, 'scripts', 'generate_grade.py')
GRADES = [11, 8, 9]  # 11 first (93 tasks), then 8 (12), then 9 (4)


def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f'{ts} [TOPUP] {msg}', flush=True)


def main():
    log(f'Top-up for grades: {GRADES}')
    for grade in GRADES:
        log(f'=== Grade {grade} ===')
        try:
            result = subprocess.run(
                [sys.executable, SCRIPT, str(grade)],
                cwd=BASE_DIR,
                timeout=7200
            )
            log(f'=== Grade {grade} done (code: {result.returncode}) ===')
        except Exception as e:
            log(f'!!! Grade {grade} error: {e}')
        time.sleep(5)
    log('=== ALL TOPUP DONE ===')


if __name__ == '__main__':
    main()
