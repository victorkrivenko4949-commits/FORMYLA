#!/usr/bin/env python
"""Diagnostic: show tail content of the 4 failing raw files."""
import os

basedir = 'l4_l5_completion_work/stage6_failed_responses'
files = ['raw_G5_L5_T004_S2.txt', 'raw_G6_L5_T016_S1.txt', 'raw_G6_L5_T018_S2.txt', 'raw_G6_L5_T018_S1.txt']

out_path = os.path.join('l4_l5_completion_work', '_diag_tails_output.txt')
with open(out_path, 'w', encoding='utf-8') as out:
    for f in files:
        path = os.path.join(basedir, f)
        with open(path, 'r', encoding='utf-8') as fh:
            text = fh.read()
        out.write(f'=== {f} === len={len(text)}\n')
        out.write(f'TAIL (last 300 chars): ...{text[-300:]}\n')
        out.write('\n')

print(f"Diagnostic written to {out_path}")
