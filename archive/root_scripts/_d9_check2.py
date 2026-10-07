# -*- coding: utf-8 -*-
"""D9_FIX diagnostics - write results to file."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

out_path = '_recon/_d9_diag.txt'
with open(out_path, 'w', encoding='utf-8') as out:

    # --- Formula calculation (correct order from level_engine.py) ---
    out.write("=== FORMULA 5 STEPS (CORRECT ORDER) ===\n")
    mu, sigma = 3.0, 1.5
    for step in range(1, 6):
        delta = sigma + 0.3
        mu = mu + 0.22 * delta
        sigma = max(0.35, sigma * 0.94)
        mu = max(1.0, min(5.0, mu))
        out.write("step=%d mu=%.3f sigma=%.3f\n" % (step, mu, sigma))
    out.write("FINAL_MU: %.3f\n\n" % mu)

    # --- Search mu/sigma in level_engine.py ---
    out.write("=== MU/SIGMA IN level_engine.py ===\n")
    for i, line in enumerate(open('services/level_engine.py', encoding='utf-8').readlines(), 1):
        ll = line.lower()
        if ('mu' in ll or 'sigma' in ll) and ('=' in line or 'clamp' in ll or 'min(' in line or 'max(' in line or 'round' in line or 'default_mu' in ll or 'default_sigma' in ll):
            out.write("%d: %s\n" % (i, line.rstrip()))
    
    out.write("\n=== MU/SIGMA IN theme_probe.py ===\n")
    for i, line in enumerate(open('services/theme_probe.py', encoding='utf-8').readlines(), 1):
        ll = line.lower()
        if ('mu' in ll or 'sigma' in ll) and ('=' in line or 'clamp' in ll or 'min(' in line or 'max(' in line or 'round' in line):
            out.write("%d: %s\n" % (i, line.rstrip()))

    out.write("\n=== MU/SIGMA IN routes/prep.py ===\n")
    for i, line in enumerate(open('routes/prep.py', encoding='utf-8').readlines(), 1):
        ll = line.lower()
        if ('mu' in ll or 'sigma' in ll) and ('=' in line or 'clamp' in ll or 'min(' in line or 'max(' in line or 'round' in line):
            out.write("%d: %s\n" % (i, line.rstrip()))

    # --- SolutionAttempt creation ---
    out.write("\n=== SolutionAttempt CREATION ===\n")
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in ('.git','node_modules','__pycache__','venv','.venv')]
        for fn in files:
            if fn.endswith('.py'):
                try:
                    for i,line in enumerate(open(os.path.join(root,fn),encoding='utf-8',errors='ignore').readlines(),1):
                        if 'SolutionAttempt(' in line and 'class ' not in line:
                            out.write("%s:%d: %s\n" % (os.path.join(root,fn), i, line.rstrip()))
                except: pass

    # --- record_answer references ---
    out.write("\n=== record_answer REFERENCES ===\n")
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d not in ('.git','node_modules','__pycache__','venv','.venv')]
        for fn in files:
            if fn.endswith('.py'):
                try:
                    for i,line in enumerate(open(os.path.join(root,fn),encoding='utf-8',errors='ignore').readlines(),1):
                        if 'record_answer' in line:
                            out.write("%s:%d: %s\n" % (os.path.join(root,fn), i, line.rstrip()))
                except: pass

    # --- adaptive_tasks ---
    import sqlite3
    c = sqlite3.connect('instance/formyla.db')
    c.row_factory = sqlite3.Row
    out.write("\n=== ADAPTIVE_TASKS ===\n")
    total = c.execute('SELECT COUNT(*) FROM adaptive_tasks').fetchone()
    out.write("TOTAL %s\n" % str(total))
    for r in c.execute('SELECT difficulty_level, COUNT(*) FROM adaptive_tasks GROUP BY difficulty_level ORDER BY difficulty_level'):
        out.write("%s\n" % str(r))
    
    # --- solution_attempts ---
    out.write("\n=== SOLUTION_ATTEMPTS ===\n")
    rows = c.execute('SELECT * FROM solution_attempts ORDER BY id DESC LIMIT 10').fetchall()
    out.write("COUNT: %d\n" % len(rows))
    for r in rows:
        d = dict(r)
        out.write("id=%s probe_id=%s\n" % (d.get('id'), d.get('probe_id')))
    
    # --- users ---
    out.write("\n=== USERS ===\n")
    out.write("COUNT: %s\n" % str(c.execute('SELECT COUNT(*) FROM users').fetchone()))
    
    c.close()

    # --- file lengths ---
    out.write("\n=== FILE LENGTHS ===\n")
    for fpath in ['services/theme_probe.py','routes/prep.py','models.py']:
        n = len(open(fpath,encoding='utf-8').readlines())
        out.write("%s: %d lines\n" % (fpath, n))

    # --- KEY FINDING: probe integer level mechanics ---
    out.write("\n=== KEY FINDING: PROBE USES INTEGER DELTA, NOT MU/SIGMA ===\n")
    out.write("theme_probe.py line 39: CORRECT_DELTA = +1\n")
    out.write("theme_probe.py line 40: PARTIAL_DELTA = 0\n")
    out.write("theme_probe.py line 41: WRONG_DELTA = -2\n")
    out.write("theme_probe.py line 36: MIN_LEVEL = 1\n")
    out.write("theme_probe.py line 37: MAX_LEVEL = 5\n")
    out.write("theme_probe.py line 35: ROUTE_CEILING = 5\n")
    out.write("theme_probe.py line 424: new_level = max(MIN_LEVEL, min(min(MAX_LEVEL, ROUTE_CEILING), new_level))\n")
    out.write("theme_probe.py line 444: final_mu = float(probe['current_level'])\n")
    out.write("\nWith start_level=3, 5 correct answers:\n")
    out.write("  step1: 3+1=4\n  step2: 4+1=5\n  step3: 5+1=6->clamp5\n  step4: 5+1=6->clamp5\n  step5: 5+1=6->clamp5\n")
    out.write("  final_mu = 5.0\n")
    out.write("\nThe mu/sigma formula exists in level_engine.py (line 209-216)\n")
    out.write("but is NOT called by the probe. The probe uses its own integer system.\n")

print("DONE: written to", out_path)
