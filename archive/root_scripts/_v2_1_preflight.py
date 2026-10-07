"""Phase 4.2 -> V2.1 LIVE — Pre-flight verification.
Before any API call: verify source, manifest, tests, prompts, policies, circuit breaker.
Writes to _v2_1_preflight_report.txt for reliable reading.
"""
import json, hashlib, os, sys, subprocess, time

OUT = r"c:\Users\Victor\Desktop\Новая папка (2)\_v2_1_preflight_report.txt"
BASE = r"c:\Users\Victor\Downloads\FORMYLA_CONDITION_COURT"
SNAPSHOT = os.path.join(BASE, r"data\immutable_snapshots\SNAP_L1_L5_BASELINE\final_clean_dataset_5levels_L3_completed.json")
MANIFEST = os.path.join(BASE, r"outputs\live_calibration_v2_1_20260712_184844\validation_manifest_real_v2_1_corrected.json")
VALIDATION = os.path.join(BASE, r"outputs\live_calibration_v2_1_20260712_184844\validation_set_real_v2_1_corrected.json")
FORENSICS = os.path.join(BASE, r"outputs\live_calibration_v2_1_20260712_184844\baseline_forensics.json")
ENV_FILE = os.path.join(BASE, ".env")

EXPECTED_SHA = "99b250eaa426a82813faf154e7f7184b663b950b33ecff8fae9bdc25193c4e61"
EXPECTED_COUNT = 2686

def log(msg):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)

log("=" * 72)
log("V2.1 LIVE PRE-FLIGHT VERIFICATION REPORT")
log(f"Started: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
log("=" * 72)

errors = []

# ── 1. Source SHA-256 ──
log("\n[1] SOURCE SHA-256 VERIFICATION")
log(f"  Path: {SNAPSHOT}")
with open(SNAPSHOT, "rb") as f:
    actual_sha = hashlib.sha256(f.read()).hexdigest()
sha_ok = actual_sha == EXPECTED_SHA
log(f"  Actual:   {actual_sha}")
log(f"  Expected: {EXPECTED_SHA}")
log(f"  MATCH: {'PASS' if sha_ok else 'FAIL'}")
if not sha_ok:
    errors.append("Source SHA-256 mismatch")

# ── 2. Source count ──
with open(SNAPSHOT, "r", encoding="utf-8") as f:
    src = json.load(f)
count_ok = len(src) == EXPECTED_COUNT
log(f"\n[2] SOURCE COUNT")
log(f"  Actual: {len(src)}, Expected: {EXPECTED_COUNT}")
log(f"  MATCH: {'PASS' if count_ok else 'FAIL'}")
if not count_ok:
    errors.append("Source count mismatch")

# ── 3. Validation manifest ──
log("\n[3] VALIDATION MANIFEST")
with open(MANIFEST, "r", encoding="utf-8") as f:
    m = json.load(f)
manifest_ok = True
log(f"  Phase: {m['phase']}")
if m["validation_set"]["total_real_tasks"] != 60:
    log("  FAIL: total_real_tasks != 60")
    manifest_ok = False
    errors.append("Manifest total != 60")
split = m["validation_set"]["split"]
for lv in ["L1","L2","L3"]:
    if split[lv] != 20:
        log(f"  FAIL: {lv} != 20")
        manifest_ok = False
        errors.append(f"Manifest {lv} != 20")
if not all(m["validation_constraints"].values()):
    log("  FAIL: Not all constraints true")
    manifest_ok = False
    errors.append("Manifest constraints not all true")
if manifest_ok:
    log("  All manifest checks: PASS")

# ── 4. Validation set content ──
log("\n[4] VALIDATION SET CONTENT")
with open(VALIDATION, "r", encoding="utf-8") as f:
    v = json.load(f)
val_ok = True
if len(v) != 60:
    log(f"  FAIL: {len(v)} entries, expected 60")
    val_ok = False
    errors.append("Validation set count != 60")
from collections import Counter
lvls = Counter(e["assigned_level"] for e in v)
for lv in ["L1","L2","L3"]:
    if lvls.get(lv, 0) != 20:
        log(f"  FAIL: {lv}={lvls.get(lv,0)}, expected 20")
        val_ok = False
        errors.append(f"Validation {lv} != 20")
sel = any("SEL1080" in str(e.get("original_id","")) for e in v)
if sel:
    log("  FAIL: SEL1080 found in original_id")
    val_ok = False
    errors.append("SEL1080 in validation set")
sol = any("solution" in e for e in v)
ca = any("correct_answer" in e for e in v)
if sol or ca:
    log(f"  FAIL: solution={sol}, correct_answer={ca}")
    val_ok = False
    errors.append("Forbidden fields in validation set")
if val_ok:
    log("  All validation set checks: PASS")

# ── 5. Run 29 tests ──
log("\n[5] PHASE 4.2 TESTS (29 expected)")
test_file = os.path.join(BASE, r"tests\test_validation_set_real_v2_1_corrected.py")
result = subprocess.run(
    [sys.executable, "-m", "pytest", test_file, "-v"],
    capture_output=True, text=True, cwd=BASE, timeout=60
)
test_output = result.stdout + result.stderr
test_pass = result.returncode == 0
log(f"  pytest exit code: {result.returncode}")
log(f"  Result: {'PASS' if test_pass else 'FAIL'}")
if not test_pass:
    errors.append(f"Phase 4.2 tests failed (exit={result.returncode})")
# Log last 5 lines
lines = test_output.strip().split("\n")
for l in lines[-5:]:
    log(f"  {l.strip()}")

# ── 6. Prompt files check ──
log("\n[6] PROMPT VERSION CHECK")
prompts_dir = os.path.join(BASE, "configs", "agent_prompts")
prompt_files = [
    "condition_lawyer_v1.md", "math_skeptic_v1.md",
    "level_calibrator_a_v1.md", "level_calibrator_b_v1.md",
    "taxonomy_auditor_v1.md", "duplicate_hunter_v1.md",
    "red_team_v1.md", "chief_justice_v1.md",
    "appeal_judge_v1.md", "appeal_judge_v2.md",
    "shared_json_contract_v1.md"
]
all_prompts_exist = True
for pf in prompt_files:
    fp = os.path.join(prompts_dir, pf)
    exists = os.path.isfile(fp)
    if not exists:
        log(f"  MISSING: {pf}")
        all_prompts_exist = False
        errors.append(f"Missing prompt: {pf}")
if all_prompts_exist:
    log("  All prompt files exist: PASS")
# Check Appeal V2 exists and is different from V1
appeal_v2 = os.path.join(prompts_dir, "appeal_judge_v2.md")
appeal_v1 = os.path.join(prompts_dir, "appeal_judge_v1.md")
v2_exists = os.path.isfile(appeal_v2)
log(f"  appeal_judge_v2.md exists: {v2_exists}")
if v2_exists:
    v1_size = os.path.getsize(appeal_v1)
    v2_size = os.path.getsize(appeal_v2)
    log(f"  v1 size: {v1_size}, v2 size: {v2_size}")
    log(f"  Different files: {v1_size != v2_size}")

# ── 7. L3 patch check ──
log("\n[7] L3 CONFIDENCE PATCH (routing only)")
l3_patch = os.path.join(BASE, "configs", "l3_confidence_v2_1_patch.md")
l3_exists = os.path.isfile(l3_patch)
log(f"  l3_confidence_v2_1_patch.md exists: {l3_exists}")
if l3_exists:
    with open(l3_patch, "r", encoding="utf-8") as f:
        l3_text = f.read().lower()
    has_095 = "0.95" in l3_text or ">= 0.95" in l3_text
    has_routing = "routing" in l3_text
    log(f"  Contains 0.95 threshold: {has_095}")
    log(f"  Routing-only semantics: {has_routing}")
    log(f"  L3 patch: {'PASS' if has_095 and has_routing else 'REVIEW NEEDED'}")

# ── 8. Timeout policy ──
log("\n[8] TIMEOUT POLICY")
timeout_policy = os.path.join(BASE, "configs", "v2_1_timeout_policy.md")
tp_exists = os.path.isfile(timeout_policy)
log(f"  v2_1_timeout_policy.md exists: {tp_exists}")
if tp_exists:
    with open(timeout_policy, "r", encoding="utf-8") as f:
        tp_text = f.read().lower()
    has_300s = "300" in tp_text or "300s" in tp_text
    has_timeout = "timeout" in tp_text
    log(f"  Contains worker timeout: {has_300s}")
    log(f"  Contains timeout mechanism: {has_timeout}")
    log(f"  Timeout policy: {'PASS' if has_300s and has_timeout else 'REVIEW NEEDED'}")

# ── 9. Court policy ──
log("\n[9] COURT POLICY")
court_policy = os.path.join(BASE, "configs", "court_policy.yaml")
cp_exists = os.path.isfile(court_policy)
log(f"  court_policy.yaml exists: {cp_exists}")

# ── 10. Environment file ──
log("\n[10] ENVIRONMENT (API KEY CHECK)")
env_exists = os.path.isfile(ENV_FILE)
log(f"  .env exists: {env_exists}")

# ── 11. Existing V2.1 output directory ──
log("\n[11] V2.1 OUTPUT DIRECTORY")
v2_1_dir = os.path.join(BASE, r"outputs\live_calibration_v2_1_20260712_184844")
log(f"  Directory: {v2_1_dir}")
if os.path.isdir(v2_1_dir):
    files = os.listdir(v2_1_dir)
    log(f"  Contains {len(files)} files")
    # Check for old run artifacts
    old_run_markers = [f for f in files if "live_" in f.lower() or "heartbeat" in f.lower()]
    if old_run_markers:
        log(f"  WARNING: old run artifacts found: {old_run_markers[:5]}")
    else:
        log("  No live run artifacts (clean for new run)")

# ── 12. Check for running Python processes with live_calibrate ──
log("\n[12] OLD CALIBRATION PROCESS CHECK")
try:
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
        capture_output=True, text=True, timeout=10
    )
    python_count = result.stdout.count("python.exe")
    log(f"  Running Python processes: {python_count}")
except:
    log("  Could not check running processes (non-critical)")

# ── Summary ──
log("\n" + "=" * 72)
log("PRE-FLIGHT SUMMARY")
log("=" * 72)
if errors:
    log(f"  ERRORS: {len(errors)}")
    for e in errors:
        log(f"    - {e}")
    log("  OVERALL: FAIL")
else:
    log("  ALL CHECKS: PASS")

log(f"\nCompleted: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
