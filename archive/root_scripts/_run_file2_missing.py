# -*- coding: utf-8 -*-
"""Прогнать ТОЛЬКО недостающие file2-задачи (380) в отдельную папку."""
import sys, os, subprocess
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

SCRIPT_DIR = 'scripts/batch'
OUT = os.path.join(SCRIPT_DIR, 'out')

sample = os.path.join(OUT, 'sample_file2_missing.jsonl')
outdir = os.path.join(OUT, 'file2_missing_out')

cmd = [
    sys.executable,
    os.path.join(SCRIPT_DIR, 'run_batch.py'),
    '--sample', sample,
    '--out-dir', outdir,
    '--deadline-sec', '240',
]
print('[file2_missing] запуск: ' + ' '.join(cmd))
raise SystemExit(subprocess.call(cmd))
