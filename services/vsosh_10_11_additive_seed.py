# -*- coding: utf-8 -*-
import json, logging, os
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

_DIFF_NUM_TO_COLOR = {1: 'green', 2: 'yellow', 3: 'orange', 4: 'red'}
_VALID_DIFF_COLORS = {'green', 'yellow', 'orange', 'red'}
_SECTION_BY_LETTER = {
    'A': 'Алгебра',
    'B': 'Базовая школа',
    'C': 'Геометрия',
    'D': 'Делимость и числа',
    'E': 'Комбинаторика',
    'F': 'Логика и игры',
    'G': 'Геометрия II',
    'H': 'Прочее',
}
DATA_PATH_RELATIVE = ('data', 'olympiads', 'vsosh_10_11_full.json')
COMPETITION = 'ВсОШ'
SEASON_YEAR = 2027
FLAG_ENV = 'VSOSH10_2027_FORCE_IMPORT'

def _data_path(app):
    root = Path(app.root_path) if hasattr(app, 'root_path') else Path.cwd()
    return root.joinpath(*DATA_PATH_RELATIVE)

def _enabled():
    return os.environ.get(FLAG_ENV, '1').strip().lower() in ('1','true','yes','on')

def run_vsosh_10_11_additive_seed(app, db):
    if not _enabled():
        logger.info('[VSOSH10_11-ADD] disabled by env %s', FLAG_ENV)
        return {'status': 'disabled'}
    try:
        with app.app_context():
            from models_olympiad import Probnik, OlympiadTask, MethodTask
            path = _data_path(app)
            if not path.is_file():
                logger.warning('[VSOSH10_11-ADD] JSON not found: %s', path)
                return {'status': 'error', 'reason': 'json_missing', 'path': str(path)}
            items = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(items, list):
                return {'status': 'error', 'reason': 'bad_format'}
            existing = (Probnik.query
                        .filter(Probnik.competition==COMPETITION,
                                Probnik.season_year==SEASON_YEAR,
                                Probnik.grade.in_((10, 11)))
                        .count())
            target_codes = sorted({t.get('probnik_code') for t in items if t.get('probnik_code')})
            if existing >= len(target_codes):
                logger.info('[VSOSH10_11-ADD] DB already has %d probniks (target %d) - skip', existing, len(target_codes))
                return {'status': 'skipped', 'reason': 'already_present', 'count': existing}
            by_code = defaultdict(list)
            for t in items:
                code = t.get('probnik_code')
                if not code:
                    continue
                grade = int(t.get('grade') or 0)
                if grade not in (10, 11):
                    continue
                by_code[code].append(t)
            sorted_codes = sorted(by_code.keys())
            grade_counter = defaultdict(int)
            stats = {'probniks_created': 0, 'probniks_existed': 0,
                     'oly_tasks_created': 0, 'oly_tasks_existed': 0,
                     'method_tasks_created': 0}
            for code in sorted_codes:
                tasks = by_code[code]
                first = tasks[0]
                grade = int(first.get('grade'))
                method_code = first.get('method_code') or code.rsplit('-', 1)[-1]
                method_name = first.get('method_name') or method_code
                section = first.get('section') or _SECTION_BY_LETTER.get((method_code[:1] or '').upper(), 'Prochee')
                p = Probnik.query.filter_by(code=code).first()
                if p is None:
                    grade_counter[grade] += 1
                    p = Probnik(code=code, type='topic', number=grade_counter[grade],
                                title='Метод ' + method_code + ': ' + method_name,
                                description=section + ' — метод ' + method_code,
                                competition=COMPETITION, grade=grade, season_year=SEASON_YEAR,
                                sort_order=grade_counter[grade], is_published=True)
                    db.session.add(p); db.session.flush()
                    stats['probniks_created'] += 1
                else:
                    stats['probniks_existed'] += 1
                existing_tasks = {ot.number for ot in OlympiadTask.query.filter_by(probnik_id=p.id).all()}
                for t in tasks:
                    num = str(t.get('number') or '')
                    if not num:
                        continue
                    if num in existing_tasks:
                        stats['oly_tasks_existed'] += 1
                        continue
                    diff_num = t.get('difficulty')
                    diff_color = _DIFF_NUM_TO_COLOR.get(int(diff_num) if diff_num else 0)
                    if diff_color not in _VALID_DIFF_COLORS:
                        diff_color = None
                    db.session.add(OlympiadTask(probnik_id=p.id, number=num,
                                                sort_order=int(t.get('sort_order', 0) or 0),
                                                difficulty=diff_color,
                                                method_primary=method_code, method_secondary=None,
                                                condition_md=t.get('text') or '',
                                                idea_md=t.get('idea') or '',
                                                solution_md=t.get('solution') or '',
                                                answer=(t.get('answer') or '')[:500],
                                                source_prototype=None,
                                                estimated_minutes=t.get('estimated_minutes'),
                                                max_score=7))
                    stats['oly_tasks_created'] += 1
                    json_id = t.get('id') or stats['method_tasks_created'] + 1
                    mt_id = (str(grade) + '-' + method_code + '-' + str(json_id))[:20]
                    if MethodTask.query.get(mt_id) is None:
                        db.session.add(MethodTask(id=mt_id, grade=grade, olympiad=COMPETITION,
                                                  subject='math', year=SEASON_YEAR,
                                                  num=int(t.get('sort_order', 0) or 0) or None,
                                                  stage=t.get('stage'),
                                                  method_code=method_code, method_name=method_name,
                                                  section=section,
                                                  difficulty=int(diff_num) if diff_num else None,
                                                  difficulty_label=t.get('difficulty_label'),
                                                  difficulty_color=t.get('difficulty_color'),
                                                  text=t.get('text') or '',
                                                  answer=t.get('answer'),
                                                  solution_idea=t.get('idea'),
                                                  task_type=None))
                        stats['method_tasks_created'] += 1
            db.session.commit()
            logger.info('[VSOSH10_11-ADD] OK: %s', stats)
            return {'status': 'ok', **stats}
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.exception('[VSOSH10_11-ADD] FATAL: %s', e)
        return {'status': 'error', 'reason': str(e)}
