# -*- coding: utf-8 -*-
"""Полный прогон file2 (2187 задач) через run_batch.py в отдельную папку.

Запуск:
    python _run_file2_full.py [--limit N]
"""
import sys, os, subprocess
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None
import argparse

SCRIPT_DIR = 'scripts/batch'
OUT = os.path.join(SCRIPT_DIR, 'out')

p = argparse.ArgumentParser()
p.add_argument('--limit', type=int, default=0)
args = p.parse_args()

sample = os.path.join(OUT, 'sample_file2.jsonl')
outdir = os.path.join(OUT, 'file2_full_out')

cmd = [
    sys.executable,
    os.path.join(SCRIPT_DIR, 'run_batch.py'),
    '--sample', sample,
    '--out-dir', outdir,
    '--deadline-sec', '240',
]
if args.limit > 0:
    cmd += ['--limit', str(args.limit)]

print('[file2_full] запуск: ' + ' '.join(cmd))
raise SystemExit(subprocess.call(cmd))
