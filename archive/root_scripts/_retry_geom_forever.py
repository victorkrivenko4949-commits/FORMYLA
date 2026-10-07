# -*- coding: utf-8 -*-
"""Бесконечный ретрай 10 упорных geometry-задач (до полного покрытия).

Перегоняет failed-джобы без лимита проходов, экспортирует готовые SVG,
останавливается когда все 362 готовы или сеть упала (DNS).
"""
import io, sys, os, json, glob, sqlite3, datetime, time, socket
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DB = 'instance/formyla.db'
OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')
LOG = '_retry_geom_forever.log'
CHECK_SEC = 20
os.makedirs(SVG, exist_ok=True)


def log(msg):
    line = '[%s] %s' % (datetime.datetime.now().strftime('%H:%M:%S'), msg)
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def dns_ok():
    try:
        socket.gethostbyname('api.deepseek.com')
        return True
    except Exception:
        return False


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
        # любой job со svg (done или failed — base svg сохраняется)
        row = c.execute("SELECT svg_path FROM figure_build_jobs WHERE problem_text=? AND svg_path IS NOT NULL AND svg_path != '' ORDER BY id DESC LIMIT 1", (cond,)).fetchone()
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


def main():
    sf = load_sf()
    c = sqlite3.connect(DB, timeout=30)
    c.execute('PRAGMA busy_timeout=30000')
    now_str = lambda: datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S.%f')
    log('forever retry start: %d missing initially' % len(missing(sf)))

    passes = {}
    while True:
        if not dns_ok():
            log('DNS down — пауза 60s')
            time.sleep(60)
            continue

        miss = missing(sf)
        exported = export_done(c, sf)
        if exported:
            log('exported %d base SVGs' % exported)

        miss = missing(sf)
        if not miss:
            log('ALL 362 DONE!')
            break

        # перегоняем failed
        reenq = 0
        for r in miss:
            tid = str(r.get('task_id'))
            cond = (r.get('condition') or '').strip()
            sol = (r.get('solution') or '').strip() or None
            row = c.execute("SELECT status FROM figure_build_jobs WHERE problem_text=? ORDER BY id DESC LIMIT 1", (cond,)).fetchone()
            if row and row[0] != 'failed':
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
            passes[tid] = passes.get(tid, 0) + 1
            reenq += 1
        c.commit()
        if reenq:
            sample_ids = [str(r.get('task_id')) for r in missing(sf)[:3]]
            log('re-enqueued %d failed (%s)' % (reenq, ', '.join(sample_ids)))

        miss = missing(sf)
        active = c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status NOT IN ('done','failed')").fetchone()[0]
        log('status: missing=%d active=%d' % (len(miss), active))
        time.sleep(CHECK_SEC)

    c.close()
    log('forever retry exit')


if __name__ == '__main__':
    main()
