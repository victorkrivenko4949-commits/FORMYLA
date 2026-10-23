# -*- coding: utf-8 -*-
"""Прикрепить готовые чертежи (figure_json + SVG) к задачам.

Два режима:
  --target srez   : обновить FORMYLA_SREZ.jsonl (добавить figure_json/answer_svg)
  --target daily  : обновить daily_task_items в БД (figure_json, figure_status, кэш SVG)

Источник чертежей: scripts/batch/out/svg_ready/*.svg + маппинг в results.jsonl
или через БД figure_build_jobs (base_plan_json = figure_json).

Сопоставление по task_id или по нормализованному тексту условия.
"""
import io, sys, os, glob, json, sqlite3, hashlib, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_OUT = os.path.join(_SCRIPT_DIR, 'out')
_CACHE_DIR = os.path.join(_SCRIPT_DIR, '..', '..', 'static', 'figures', 'cache')


def _norm(s: str) -> str:
    s = re.sub(r'\s+', ' ', (s or '')).lower().strip()
    return s


def figure_hash(figure_json) -> str:
    if isinstance(figure_json, dict):
        canonical = json.dumps(figure_json, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    else:
        try:
            canonical = json.dumps(json.loads(figure_json), sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        except Exception:
            canonical = str(figure_json)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def load_ready_figures():
    """Вернуть dict: norm_condition -> (figure_json, svg_content)."""
    # Читаем из БД figure_build_jobs (base_plan_json + svg_path) для user 1301 done.
    c = sqlite3.connect('instance/formyla.db')
    out = {}
    for jid, problem, base_plan, svg_path in c.execute(
        "SELECT id, problem_text, base_plan_json, svg_path FROM figure_build_jobs "
        "WHERE user_id=1301 AND status='done' AND base_plan_json IS NOT NULL"
    ).fetchall():
        if not base_plan or not svg_path:
            continue
        norm = _norm(problem)
        # svg_path хранит inline SVG (по результатам прогона)
        svg = svg_path
        out[norm] = (base_plan, svg)
    return out


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--target', required=True, choices=['srez', 'daily'])
    args = p.parse_args()

    ready = load_ready_figures()
    print(f"Готовых чертежей в БД: {len(ready)}")

    if args.target == 'srez':
        _attach_srez(ready)
    else:
        _attach_daily(ready)


def _attach_srez(ready):
    src = 'FORMYLA_SREZ.jsonl'
    rows = [json.loads(l) for l in open(src, encoding='utf-8')]
    matched = 0
    for r in rows:
        norm = _norm(r.get('statement'))
        if norm in ready:
            base_plan, svg = ready[norm]
            r['figure_json'] = base_plan
            h = figure_hash(base_plan)
            r['figure_svg_hash'] = h
            # сохранить SVG в кэш
            os.makedirs(_CACHE_DIR, exist_ok=True)
            with open(os.path.join(_CACHE_DIR, f'{h}.svg'), 'w', encoding='utf-8') as f:
                f.write(svg)
            matched += 1
    with open(src, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(f"[srez] прикреплено чертежей: {matched}/{len(rows)}")


def _attach_daily(ready):
    from app import app
    from models import db, FigureBuildJob
    from daily_tasks.models import DailyTaskItem
    with app.app_context():
        items = DailyTaskItem.query.filter_by(figure_status='no_description').all()
        matched = 0
        for it in items:
            norm = _norm(it.task_text)
            if norm in ready:
                base_plan, svg = ready[norm]
                it.figure_json = base_plan
                h = figure_hash(base_plan)
                os.makedirs(_CACHE_DIR, exist_ok=True)
                with open(os.path.join(_CACHE_DIR, f'{h}.svg'), 'w', encoding='utf-8') as f:
                    f.write(svg)
                it.figure_status = 'figure_built'
                matched += 1
        db.session.commit()
        print(f"[daily] прикреплено чертежей: {matched}/{len(items)}")


if __name__ == '__main__':
    main()
