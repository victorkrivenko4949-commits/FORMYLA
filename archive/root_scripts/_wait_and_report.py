# -*- coding: utf-8 -*-
import io, sys, time, os, json, glob, sqlite3
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 300
time.sleep(SECS)

# read current monitor state
out = io.StringIO()
if os.path.exists('_monitor.txt'):
    out.write(open('_monitor.txt', encoding='utf-8').read())
out.write('\n--- autopilot last lines ---\n')
if os.path.exists('_autopilot.log'):
    lines = open('_autopilot.log', encoding='utf-8').read().strip().splitlines()
    for l in lines[-6:]:
        out.write(l + '\n')

# geometry completeness quick
sf = [json.loads(l) for l in open('scripts/batch/out/sample_full.jsonl', encoding='utf-8') if l.strip()]
svg = set(os.path.basename(f).replace('.svg', '') for f in glob.glob('scripts/batch/out/svg_ready/*.svg'))
have = 0
for r in sf:
    tid = str(r.get('task_id'))
    if f"{tid}_{r.get('grade')}" in svg or any(b == tid or b.startswith(tid + '_') for b in svg):
        have += 1
out.write('\ngeometry completeness: %d/362\n' % have)
print(out.getvalue())
