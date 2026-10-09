# -*- coding: utf-8 -*-
"""Фоновый автопилот: мониторит wave4-retry и 23 geometry-задачи,
ретранслирует неудачные geometry-задачи, экспортирует готовые SVG,
пересобирает архив geometry_7_11_drawings.zip, когда все 362 готовы.

Логирует каждые CHECK_SEC секунд в _autopilot.log и _monitor.txt.
"""
import io, sys, os, json, glob, sqlite3, time, datetime, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DB = 'instance/formyla.db'
OUT = 'scripts/batch/out'
SVG_DIR = os.path.join(OUT, 'svg_ready')
DELIV = '_deliverables'
GEO_ZIP = os.path.join(DELIV, 'geometry_7_11_drawings.zip')
LOG = '_autopilot.log'
CHECK_SEC = 60
RETRY_MAX = 2  # число ретраев на задачу
RETRY_STATE = '_geometry_retry_state.json'

os.makedirs(SVG_DIR, exist_ok=True)
os.makedirs(DELIV, exist_ok=True)


def log(msg):
    line = '[%s] %s' % (datetime.datetime.now().strftime('%H:%M:%S'), msg)
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def load_retry_state():
    if os.path.exists(RETRY_STATE):
        try:
            return json.load(open(RETRY_STATE, encoding='utf-8'))
        except Exception:
            pass
    return {}


def save_retry_state(st):
    json.dump(st, open(RETRY_STATE, 'w', encoding='utf-8'), ensure_ascii=False)


def load_sample_full():
    return [json.loads(l) for l in open(os.path.join(OUT, 'sample_full.jsonl'), encoding='utf-8') if l.strip()]


def svg_bases():
    return set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG_DIR, '*.svg')))


def missing_geometry(sf):
    svg = svg_bases()
    out = []
    for r in sf:
        tid = str(r.get('task_id'))
        if f"{tid}_{r.get('grade')}" in svg:
            continue
        if any(b == tid or b.startswith(tid + '_') for b in svg):
            continue
        out.append(r)
    return out


def enqueue(retry_state, c, r, attempt):
    cond = (r.get('condition') or '').strip()
    sol = (r.get('solution') or '').strip() or None
    n = c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE problem_text=? AND status IN "
                  "('queued','base_thinking','base_drawing','thinking','drawing','auditing',"
                  "'aux_thinking','aux_drawing','coverage_check','visual_check','solving',"
                  "'answer_verify','aux_compile','aux_usefulness','aux_template_match')", (cond,)).fetchone()[0]
    if n:
        return False
    now = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S.%f')
    # priority=-1: служебные batch-задачи не должны обгонять живых пользователей
    # (иначе геометрический автопилот забивает очередь и реальный пользователь
    # бесконечно висит в статусе «В очереди»).
    c.execute(
        "INSERT INTO figure_build_jobs "
        "(user_id, problem_text, solution_text, generation_mode, status, model_name, priority, "
        " has_aux, credit_charged, created_at, updated_at) "
        "VALUES (?, ?, ?, 'condition_solution', 'queued', 'deepseek-v4-pro', -1, 0, 0, ?, ?)",
        (1301, cond, sol, now, now))
    retry_state[str(r.get('task_id'))] = attempt
    return True


def wave4_counts():
    d = os.path.join(OUT, 'wave4_retry_out')
    res = os.path.join(d, 'results.jsonl')
    total = 334
    if not os.path.exists(res):
        return total, 0, 0, 0
    rows = [json.loads(l) for l in open(res, encoding='utf-8') if l.strip()]
    done = sum(1 for r in rows if r.get('status') == 'done')
    failed = sum(1 for r in rows if r.get('status') == 'failed')
    timeout = sum(1 for r in rows if r.get('status') == 'timeout')
    return total, done, failed, timeout


def export_geometry_svg(c, sf):
    svg = svg_bases()
    saved = 0
    for r in sf:
        tid = str(r.get('task_id'))
        grade = r.get('grade')
        if f"{tid}_{grade}" in svg:
            continue
        cond = (r.get('condition') or '').strip()
        row = c.execute(
            "SELECT svg_path, status FROM figure_build_jobs WHERE problem_text=? AND status='done' "
            "ORDER BY id DESC LIMIT 1", (cond,)).fetchone()
        if not row:
            continue
        svg_path, _ = row
        if not svg_path:
            continue
        content = None
        if svg_path.lstrip().startswith('<?xml'):
            content = svg_path
        else:
            try:
                content = open(svg_path, encoding='utf-8').read()
            except OSError:
                content = None
        if content:
            fname = '%s_%s.svg' % (tid, grade)
            with open(os.path.join(SVG_DIR, fname), 'w', encoding='utf-8') as f:
                f.write(content)
            saved += 1
    return saved


def rebuild_geometry_zip(sf):
    svg = {os.path.basename(f): f for f in glob.glob(os.path.join(SVG_DIR, '*.svg'))}
    found = 0
    missing = []
    with zipfile.ZipFile(GEO_ZIP, 'w', zipfile.ZIP_DEFLATED) as z:
        for r in sf:
            tid = str(r.get('task_id'))
            grade = r.get('grade')
            cand = '%s_%s.svg' % (tid, grade)
            if cand in svg:
                z.write(svg[cand], cand)
                found += 1
            else:
                m = [f for f in svg if f.startswith(tid + '_')]
                if m:
                    z.write(svg[m[0]], m[0])
                    found += 1
                else:
                    missing.append(tid)
    return found, missing


def main():
    sf = load_sample_full()
    retry_state = load_retry_state()
    log('autopilot start: geometry total=%d' % len(sf))

    c = sqlite3.connect(DB, timeout=30)
    c.execute('PRAGMA busy_timeout=30000')

    last_zip_rebuild = 0
    while True:
        c2 = c
        # 1) wave4
        t4, d4, f4, to4 = wave4_counts()
        remaining4 = t4 - (d4 + f4 + to4)

        # 2) geometry status + retry
        miss = missing_geometry(sf)
        done_now = export_geometry_svg(c2, sf)
        retried = 0
        for r in miss:
            tid = str(r.get('task_id'))
            cond = (r.get('condition') or '').strip()
            row = c2.execute(
                "SELECT status FROM figure_build_jobs WHERE problem_text=? ORDER BY id DESC LIMIT 1",
                (cond,)).fetchone()
            if row and row[0] == 'failed':
                attempt = retry_state.get(tid, 0)
                if attempt < RETRY_MAX:
                    if enqueue(retry_state, c2, r, attempt + 1):
                        retried += 1
                        log('retry geometry %s (attempt %d)' % (tid, attempt + 1))
        c2.commit()
        if retried:
            save_retry_state(retry_state)

        # 3) completeness
        svg = svg_bases()
        have = 0
        for r in sf:
            tid = str(r.get('task_id'))
            if f"{tid}_{r.get('grade')}" in svg or any(b == tid or b.startswith(tid + '_') for b in svg):
                have += 1

        log('wave4 remaining=%d (done=%d failed=%d timeout=%d) | geometry %d/362 missing=%d exported=%d retried=%d'
            % (remaining4, d4, f4, to4, have, len(miss), done_now, retried))

        with open('_monitor.txt', 'w', encoding='utf-8') as f:
            f.write('wave4: total=%d done=%d failed=%d timeout=%d remaining=%d\n'
                    % (t4, d4, f4, to4, remaining4))
            f.write('geometry: %d/362 (missing=%d)\n' % (have, len(miss)))

        # 4) if geometry complete, rebuild zip (rate-limit rebuild to once/3 min)
        if have >= len(sf):
            now = time.time()
            if now - last_zip_rebuild > 180:
                found, miss_ids = rebuild_geometry_zip(sf)
                last_zip_rebuild = now
                log('geometry COMPLETE -> rebuilt zip: %d files' % found)
            if remaining4 <= 0:
                log('ALL DONE. wave4 finished and geometry complete.')
                break
        elif remaining4 <= 0:
            # wave4 done but geometry still missing -> keep retrying geometry only
            if not miss:
                log('wave4 done, geometry has no missing SVGs -> rebuilding zip')
                found, miss_ids = rebuild_geometry_zip(sf)
                log('rebuilt zip: %d files, missing=%s' % (found, miss_ids[:5]))
                break

        time.sleep(CHECK_SEC)

    c.close()
    log('autopilot exit')


if __name__ == '__main__':
    main()
