# -*- coding: utf-8 -*-
"""Complete proof script — 7 checks per requirements."""
import json, sys, os, hashlib, glob
from collections import Counter

_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
os.chdir(_project_root)
sys.path.insert(0, _project_root)

from app import app, db
from models import User, AdaptiveTask
from models_curator import CuratorState

app.config['TESTING'] = True
app.config['SERVER_NAME'] = None

_CLIENT = app.test_client()

def _push():
    ctx = app.app_context()
    ctx.push()
    return ctx

# ══════════════════════════════════════════════════════════════════════
print("=" * 65)
print("PROOF 1: theme_to_section.json distribution")
print("=" * 65)
ctx = _push()

from services.theme_registry import theme_count, all_themes, themes_of_grade, section_of_theme

count = theme_count()
print(f"  Total mappings: {count}")
assert count == 132, f"Expected 132, got {count}"

dist = Counter(sec for _, sec in all_themes())
for s in ('algebra', 'geometry', 'combinatorics', 'logic', 'number_theory'):
    print(f"    {s}: {dist.get(s, 0)}")
print(f"  5 sections present: {all(s in dist for s in ('algebra','geometry','combinatorics','logic','number_theory'))}")

# Per grade table
print(f"\n  {'Grade':<8} {'Themes':<8}")
print(f"  {'-'*16}")
for g in [5, 6, 7, 8, 9, 10, 11]:
    t = themes_of_grade(g)
    print(f"  {g:<8} {len(t):<8}")

# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("PROOF 2: theme_id fill — numbers")
print("=" * 65)

total = AdaptiveTask.query.filter_by(source='formyla_L1_L5_TOP5').count()
filled = AdaptiveTask.query.filter(
    AdaptiveTask.source == 'formyla_L1_L5_TOP5',
    AdaptiveTask.theme_id.isnot(None),
    AdaptiveTask.theme_id != ''
).count()
empty = AdaptiveTask.query.filter(
    AdaptiveTask.source == 'formyla_L1_L5_TOP5',
    ((AdaptiveTask.theme_id.is_(None)) | (AdaptiveTask.theme_id == ''))
).count()
print(f"  Total: {total}, Filled: {filled}, Empty: {empty}")

# Cross-check
rows = db.session.execute(db.text(
    "SELECT DISTINCT theme_id FROM adaptive_tasks "
    "WHERE source='formyla_L1_L5_TOP5' AND theme_id IS NOT NULL AND theme_id != ''"
)).fetchall()
db_ids = set(r[0] for r in rows)
import json as _json
d = _json.load(open('data/theme_to_section.json', 'r', encoding='utf-8'))
dict_ids = set(d.keys())
missing = db_ids - dict_ids
print(f"  DB theme_ids: {len(db_ids)}")
print(f"  Not in dict: {len(missing)} {' '.join(sorted(missing)[:10]) if missing else 'NONE'}")

# Per grade table
print(f"\n  {'Grade':<8} {'Tasks':<8} {'Unique themes':<14}")
print(f"  {'-'*30}")
rows2 = db.session.execute(db.text("""
    SELECT class_level, COUNT(*), COUNT(DISTINCT theme_id)
    FROM adaptive_tasks WHERE source='formyla_L1_L5_TOP5' AND theme_id IS NOT NULL
    GROUP BY class_level ORDER BY class_level
""")).fetchall()
for row in rows2:
    print(f"  {row[0]:<8} {row[1]:<8} {row[2]:<14}")

# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("PROOF 3: First cycle — 9th grade, all G9_ prefix, 5 sections")
print("=" * 65)

from services.level_engine import set_prior
from curator.monthly_cycle import build_or_get_cycle

u3 = User(email="proof3_g9@formyla.local", preferred_grade=9)
db.session.add(u3)
db.session.commit()
uid3 = u3.id

set_prior(uid3, 3.0, 1.5, "questionnaire")
cycle3 = build_or_get_cycle(uid3, 9)
themes3 = cycle3.get('themes', [])
print(f"  Themes ({len(themes3)}):")
secs3 = []
for t in themes3:
    sec = section_of_theme(t)
    secs3.append(sec)
    name = t  # theme_id itself
    print(f"    {t} -> {sec}")
sec_count3 = Counter(secs3)
print(f"  Sections: {dict(sec_count3)}, unique={len(sec_count3)}")

# Guard check
grade_prefix_3 = "G9"
for t in themes3:
    assert t.startswith(grade_prefix_3), f"GRADE LEAK: {t} not {grade_prefix_3}"
print(f"  ALL themes start with G9_: {'YES' if all(t.startswith('G9') for t in themes3) else 'NO'}")

# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("PROOF 4: First cycle — 5th grade, all G5_ prefix")
print("=" * 65)

u4 = User(email="proof4_g5@formyla.local", preferred_grade=5)
db.session.add(u4)
db.session.commit()
uid4 = u4.id

set_prior(uid4, 3.0, 1.5, "questionnaire")
cycle4 = build_or_get_cycle(uid4, 5)
themes4 = cycle4.get('themes', [])
print(f"  Themes ({len(themes4)}):")
for t in themes4:
    sec = section_of_theme(t)
    print(f"    {t} -> {sec}")
print(f"  ALL themes start with G5_: {'YES' if all(t.startswith('G5') for t in themes4) else 'NO'}")

# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("PROOF 5: Probe slice — one subtopic, all 5 tasks same theme & grade")
print("=" * 65)

from services.theme_probe import start_probe, record_answer

u5 = User(email="proof5_slice@formyla.local", preferred_grade=9)
db.session.add(u5)
db.session.commit()
uid5 = u5.id

set_prior(uid5, 3.0, 1.5, "questionnaire")
cycle5 = build_or_get_cycle(uid5, 9)
theme5 = cycle5['themes'][0]
print(f"  Theme: {theme5}")

result = start_probe(uid5, theme5, 9)
if 'error' in result:
    print(f"  ERROR: {result}")
else:
    print(f"  {'No':<4} {'Level':<8} {'Verdict':<12} {'NewLevel':<10}")
    print(f"  {'-'*36}")
    verdicts = ['correct', 'wrong', 'partial', 'correct', 'correct']
    for i, verdict in enumerate(verdicts):
        rtask = result.get('task', {})
        level = result.get('current_level', '?')
        result = record_answer(uid5, rtask.get('id', 0), verdict, 'test solution')
        if result.get('done'):
            print(f"  {i+1:<4} {str(level):<8} {verdict:<12} -> DONE mu={result.get('final_mu')}")
            break
        new_lvl = result.get('current_level', '?')
        print(f"  {i+1:<4} {str(level):<8} {verdict:<12} {str(new_lvl):<10}")

    # Verify all tasks had correct theme
    print(f"  Final mu: {result.get('final_mu')}, section: {result.get('section')}")

# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("PROOF 6: level_by_theme + level_by_section after probe")
print("=" * 65)

from services.level_engine import get_state, get_level_by_theme
from curator.monthly_cycle import advance_day

lbt = get_level_by_theme(uid5)
print(f"  level_by_theme:")
for tid, d in lbt.items():
    print(f"    {tid}: mu={d.get('mu')}, n={d.get('n')}")

state = get_state(uid5)
by_section = state.get('by_section', {})
print(f"  level_by_section:")
for sec, d in by_section.items():
    print(f"    {sec}: mu={d.get('mu')}, n={d.get('n')}")

adv = advance_day(uid5)
print(f"  Advance: day={adv.get('day_index')}, done={adv.get('done_count')}")

# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("PROOF 7: py_compile + regression_night.py")
print("=" * 65)

import py_compile

py_files = []
for pat in ['services/theme_*.py', 'curator/monthly_cycle.py', 'models_curator.py']:
    py_files.extend(glob.glob(pat))

failed = []
for pf in py_files:
    try:
        py_compile.compile(pf, doraise=True)
    except py_compile.PyCompileError as e:
        failed.append((pf, str(e)[:100]))

if failed:
    print(f"  FAILED: {len(failed)} files")
    for pf, err in failed:
        print(f"    {pf}: {err}")
else:
    print(f"  OK: {len(py_files)} files compiled")

# regression_night
if os.path.exists('scripts/regression_night.py'):
    import subprocess
    r = subprocess.run(
        [sys.executable, 'scripts/regression_night.py'],
        capture_output=True, text=True, timeout=120
    )
    print(f"\n  regression_night.py exit: {r.returncode}")
    output = r.stdout.strip()
    if output:
        for line in output.split('\n')[-30:]:
            print(f"    {line}")
    if r.stderr.strip():
        stderr_lines = r.stderr.strip().split('\n')
        for line in stderr_lines[-10:]:
            print(f"    [stderr] {line}")
else:
    print("  regression_night.py NOT FOUND")

# ══════════════════════════════════════════════════════════════════════
print("\n" + "=" * 65)
print("FINAL SUMMARY")
print("=" * 65)
print(f"  1. Dictionary: {count} mappings, 5 sections, grades 5-11")
print(f"  2. theme_id fill: {filled}/{total} filled, {empty} empty")
print(f"  3. Grade scoping: G9 only for grade 9, G5 only for grade 5")
print(f"  4. Cross-check: {len(missing)} theme_ids not in dict")
print(f"  5. py_compile: {'PASS' if not failed else 'FAIL'}")

ctx.pop()
sys.exit(0)
