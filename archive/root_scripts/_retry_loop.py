# -*- coding: utf-8 -*-
"""Фоновый ретрай-цикл: перегоняет неудачные geometry-задачи до полного покрытия.

Работает пока есть недостающие SVG. Максимум MAX_PASSES проходов на задачу.
Экспортирует готовые SVG, пересобирает архив по завершении.
"""
import io, sys, os, json, glob, sqlite3, datetime, time, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DB = 'instance/formyla.db'
OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')
DELIV = '_deliverables'
GEO_ZIP = os.path.join(DELIV, 'geometry_7_11_drawings.zip')
LOG = '_retry_loop.log'
CHECK_SEC = 20
MAX_PASSES = 4
os.makedirs(SVG, exist_ok=True)
os.makedirs(DELIV, exist_ok=True)


def log(msg):
    line = '[%s] %s' % (datetime.datetime.now().strftime('%H:%M:%S'), msg)
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def load_sf():
    return [json.loads(l) for l in open(os.path.join(OUT, 'sample_full.jsonl'), encoding='utf-8') if l.strip()]


def svg_bases():
    return set(os.path.basename(f).replace('.svg', '') for f in glob.glob(os.path.join(SVG, '*.svg')))


def missing(sf):
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


def export_done(c, sf):
    svg = svg_bases()
    saved = 0
    for r in sf:
        tid = str(r.get('task_id'))
        grade = r.get('grade')
        if f"{tid}_{grade}" in svg:
            continue
        cond = (r.get('condition') or '').strip()
        row = c.execute("SELECT svg_path FROM figure_build_jobs WHERE problem_text=? AND status='done' "
                        "ORDER BY id DESC LIMIT 1", (cond,)).fetchone()
        if not row or not row[0]:
            continue
        content = row[0]
        if not content.lstrip().startswith('<?xml'):
            try:
                content = open(content, encoding='utf-8').read()
            except OSError:
                content = None
        if content:
            with open(os.path.join(SVG, '%s_%s.svg' % (tid, grade)), 'w', encoding='utf-8') as f:
                f.write(content)
            saved += 1
    return saved


def rebuild_zip(sf):
    svg = {os.path.basename(f): f for f in glob.glob(os.path.join(SVG, '*.svg'))}
    found = 0
    missing_ids = []
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
                    missing_ids.append(tid)
    return found, missing_ids


def main():
    sf = load_sf()
    passes = {}
    c = sqlite3.connect(DB, timeout=30)
    c.execute('PRAGMA busy_timeout=30000')
    log('retry loop start, geometry total=%d' % len(sf))
    now_str = lambda: datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S.%f')

    idle_cycles = 0
    while True:
        miss = missing(sf)
        exported = export_done(c, sf)
        if exported:
            log('exported %d new SVG' % exported)

        # re-enqueue failed jobs (respect MAX_PASSES)
        reenq = 0
        for r in miss:
            tid = str(r.get('task_id'))
            cond = (r.get('condition') or '').strip()
            sol = (r.get('solution') or '').strip() or None
            row = c.execute("SELECT status FROM figure_build_jobs WHERE problem_text=? ORDER BY id DESC LIMIT 1",
                            (cond,)).fetchone()
            if row and row[0] != 'failed':
                continue
            p = passes.get(tid, 0)
            if p >= MAX_PASSES:
                continue
            active = c.execute(
                "SELECT COUNT(*) FROM figure_build_jobs WHERE problem_text=? AND status IN "
                "('queued','base_thinking','base_drawing','thinking','drawing','auditing',"
                "'aux_thinking','aux_drawing','coverage_check','visual_check','solving',"
                "'answer_verify','aux_compile','aux_usefulness','aux_template_match')", (cond,)).fetchone()[0]
            if active:
                continue
            c.execute(
                "INSERT INTO figure_build_jobs "
                "(user_id, problem_text, solution_text, generation_mode, status, model_name, priority, "
                " has_aux, credit_charged, created_at, updated_at) "
                "VALUES (?, ?, ?, 'condition_solution', 'queued', 'deepseek-v4-pro', -1, 0, 0, ?, ?)",
                (1301, cond, sol, now_str(), now_str()))
            passes[tid] = p + 1
            reenq += 1
            log('re-enqueue %s (pass %d/%d)' % (tid, p + 1, MAX_PASSES))
        c.commit()
        if reenq:
            log('re-enqueued %d' % reenq)

        miss = missing(sf)
        if not miss:
            log('ALL 362 GEOMETRY DONE. rebuilding zip...')
            found, _ = rebuild_zip(sf)
            log('zip rebuilt: %d files' % found)
            break

        # detect stuck: nothing active and nothing done for long -> stop
        active = c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status NOT IN ('done','failed')").fetchone()[0]
        if active == 0:
            idle_cycles += 1
        else:
            idle_cycles = 0
        if idle_cycles > 30:  # ~10 min of nothing
            log('no active jobs for 10 min, stopping retry loop (stuck on geometric/external)')
            break

        log('status: missing=%d active=%d' % (len(miss), active))
        time.sleep(CHECK_SEC)

    # final export + zip
    export_done(c, sf)
    found, miss_ids = rebuild_zip(sf)
    log('final zip: %d files, still missing=%d -> %s' % (found, len(miss_ids), miss_ids[:10]))
    c.close()
    log('retry loop exit')


if __name__ == '__main__':
    main()
