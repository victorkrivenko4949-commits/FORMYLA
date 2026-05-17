import sys, os, json, glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app
from models import db
from models_olympiad import OlympiadTask, Probnik

DOWNLOADS = os.path.join(os.path.expanduser('~'), 'Downloads')
PH = 'TODO'

STAGE_MAP = [
    ('stage-1', 'E1.1', '1.1'),
    ('stage-1', 'E1.2', '1.3'),
    ('stage-1', 'E1.3', '1.8'),
    ('stage-1', 'E1.4', '2.3'),
    ('stage-1', 'E1.5', '1.17'),
    ('stage-2', 'E2.1', '1.6'),
    ('stage-2', 'E2.2', '2.2'),
    ('stage-2', 'E2.3', '3.6'),
    ('stage-2', 'E2.4', '2.7'),
    ('stage-2', 'E2.5', '5.7'),
    ('stage-3', 'E3.1', '1.16'),
    ('stage-3', 'E3.2', '4.7'),
    ('stage-3', 'E3.3', '2.9'),
    ('stage-3', 'E3.4', '5.4'),
    ('stage-3', 'E3.5', '9.17'),
    ('stage-4', 'E4.1', '3.4'),
    ('stage-4', 'E4.2', '8.3'),
    ('stage-4', 'E4.3', '2.6'),
    ('stage-4', 'E4.4', '5.8'),
    ('stage-4', 'E4.5', '7.14'),
    ('stage-5', 'E5.1', '3.10'),
    ('stage-5', 'E5.2', '8.17'),
    ('stage-5', 'E5.3', '7.16'),
    ('stage-5', 'E5.4', '9.20'),
]


def cyr(s):
    return s.replace('E', '\u042d')


def pick_src():
    if len(sys.argv) > 1 and sys.argv[1]:
        return sys.argv[1]
    pattern = os.path.join(DOWNLOADS, 'vsosh_9_2027_tasks_batches_*.json')
    matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not matches:
        print('ERROR: no batch file found in', DOWNLOADS)
        sys.exit(1)
    return matches[0]


FIELDS = (
    'condition_md', 'idea_md', 'solution_md', 'answer', 'source_prototype',
    'estimated_minutes', 'difficulty', 'method_primary', 'method_secondary',
    'max_score',
)


def update_one(row, src):
    changed = []
    for k in FIELDS:
        if k in src and src[k] is not None:
            old = getattr(row, k)
            if old != src[k]:
                setattr(row, k, src[k])
                changed.append(k)
    return changed


def topic_for(num):
    return 'vsosh-9-2027-topic-' + num.split('.')[0]


def apply_batch(path):
    print('Source batch:', path)
    with open(path, 'r', encoding='utf-8') as fh:
        data = json.load(fh)
    print('items in file:', len(data))

    updated = 0
    skipped = 0
    missing = 0
    skipped_numbers = []

    with app.app_context():
        by_key = dict()
        for row in OlympiadTask.query.all():
            probnik = db.session.get(Probnik, row.probnik_id)
            by_key[(probnik.code, row.number)] = row

        for raw in data:
            status = raw.get('status')
            number = raw.get('number')
            code = raw.get('probnik_code')
            cond = raw.get('condition_md')
            is_empty = (status == 'needs_content') or (cond in (None, '')) or (
                isinstance(cond, str) and cond.startswith(PH)
            )
            if is_empty:
                skipped += 1
                skipped_numbers.append(code + '/' + number)
                continue
            row = by_key.get((code, number))
            if row is None:
                missing += 1
                continue
            ch = update_one(row, raw)
            if ch:
                updated += 1

        copied = 0
        stage_skipped = 0
        stage_skip_numbers = []
        for stage_key, stage_num, src_num in STAGE_MAP:
            src = by_key.get((topic_for(src_num), src_num))
            tgt_key = ('vsosh-9-2027-' + stage_key, cyr(stage_num))
            tgt = by_key.get(tgt_key)
            if src is None or tgt is None:
                continue
            sc = src.condition_md or ''
            if sc.startswith(PH) or not sc:
                stage_skipped += 1
                stage_skip_numbers.append(stage_num + '<-' + src_num)
                continue
            for k in (
                'condition_md', 'idea_md', 'solution_md', 'answer',
                'source_prototype', 'estimated_minutes', 'difficulty',
                'method_primary', 'method_secondary',
            ):
                v = getattr(src, k)
                if v is not None:
                    setattr(tgt, k, v)
            copied += 1

        db.session.commit()

        all_rows = OlympiadTask.query.all()
        ready_rows = []
        todo_rows = []
        for r in all_rows:
            c = r.condition_md or ''
            if c and not c.startswith(PH):
                ready_rows.append(r)
            else:
                todo_rows.append(r)
        todo_numbers = []
        for r in todo_rows:
            probnik = db.session.get(Probnik, r.probnik_id)
            todo_numbers.append(probnik.code + '/' + r.number)

    print()
    print('Updated thematic rows: ', updated)
    print('Skipped in batch (needs_content): ', skipped)
    print('Missing in DB (not in skeleton): ', missing)
    print('Copied to stage: ', copied)
    print('Stage skipped (source still empty): ', stage_skipped)
    if stage_skip_numbers:
        print('  ', ', '.join(stage_skip_numbers))
    print()
    print('FINAL TOTAL:')
    print('  ready: ', len(ready_rows), '/', len(all_rows))
    print('  todo : ', len(todo_rows), '/', len(all_rows))
    if todo_numbers:
        print()
        print('Tasks awaiting content:')
        for n in todo_numbers:
            print('  -', n)


if __name__ == '__main__':
    apply_batch(pick_src())
