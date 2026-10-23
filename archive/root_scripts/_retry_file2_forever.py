# -*- coding: utf-8 -*-
"""Бесконечный ретрай недостающих file2-задач (до полного покрытия).

Перегоняет failed-джобы, экспортирует готовые SVG, пересобирает архив.
Останавливается когда покрытие 2187/2187 или сеть упала.
"""
import io, sys, os, json, glob, sqlite3, datetime, time, socket, zipfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

DB = 'instance/formyla.db'
OUT = 'scripts/batch/out'
SVG = os.path.join(OUT, 'svg_ready')
DELIV = '_deliverables'
LOG = '_retry_file2_forever.log'
CHECK_SEC = 20
os.makedirs(SVG, exist_ok=True)
os.makedirs(DELIV, exist_ok=True)


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


def load_sample():
    return [json.loads(l) for l in io.open(os.path.join(OUT, 'sample_file2.jsonl'), encoding='utf-8') if l.strip()]


def have_set():
    s = set()
    for f in glob.glob(os.path.join(SVG, 'f2_*.svg')):
        s.add(os.path.basename(f)[:-4].rsplit('_', 1)[0])
    return s


def missing(sample, have):
    return [r for r in sample if str(r.get('task_id')) not in have]


def export_done(c, sample, have):
    saved = 0
    for r in sample:
        tid = str(r.get('task_id'))
        if tid in have:
            continue
        cond = (r.get('condition') or '').strip()
        row = c.execute("SELECT svg_path FROM figure_build_jobs WHERE problem_text=? AND svg_path IS NOT NULL AND svg_path != '' ORDER BY id DESC LIMIT 1", (cond,)).fetchone()
        if not row or not row[0]:
            continue
        content = row[0]
        if not content.lstrip().startswith('<?xml'):
            try:
                content = io.open(content, encoding='utf-8').read()
            except OSError:
                content = None
        if content:
            with io.open(os.path.join(SVG, '%s_%s.svg' % (tid, r.get('grade'))), 'w', encoding='utf-8') as f:
                f.write(content)
            saved += 1
    return saved


def rebuild_zip():
    f2 = glob.glob(os.path.join(SVG, 'f2_*.svg'))
    with zipfile.ZipFile(os.path.join(DELIV, 'file2_all_waves_drawings.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(f2):
            z.write(f, os.path.basename(f))
    return len(f2)


def main():
    sample = load_sample()
    c = sqlite3.connect(DB, timeout=30)
    c.execute('PRAGMA busy_timeout=30000')
    now_str = lambda: datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S.%f')

    have = have_set()
    miss = missing(sample, have)
    log('file2 forever retry start: %d missing' % len(miss))

    passes = {}
    while True:
        if not dns_ok():
            log('DNS down — пауза 60s')
            time.sleep(60)
            continue

        have = have_set()
        miss = missing(sample, have)
        exported = export_done(c, sample, have)
        if exported:
            log('exported %d done SVGs' % exported)
            have = have_set()
            miss = missing(sample, have)

        if not miss:
            log('ALL 2187 DONE! rebuilding zip')
            rebuild_zip()
            break

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
            log('re-enqueued %d failed' % reenq)

        have = have_set()
        miss = missing(sample, have)
        active = c.execute("SELECT COUNT(*) FROM figure_build_jobs WHERE status NOT IN ('done','failed')").fetchone()[0]
        log('status: missing=%d active=%d' % (len(miss), active))

        # пересобрать архив раз в ~5 мин, если есть прогресс
        if reenq == 0 and len(miss) < 256:
            rebuild_zip()

        time.sleep(CHECK_SEC)

    c.close()
    log('file2 forever retry exit')


if __name__ == '__main__':
    main()
