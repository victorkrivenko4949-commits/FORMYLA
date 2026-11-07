# -*- coding: utf-8 -*-
"""Назначенный пробник — шаблон «выдать ученику вариант олимпиады на день».

PROBNIK_ASSIGN_V1 (07.11.2026, владелец). Как пользоваться в будущем:

* админка /probnik-assign/admin — выбрать ученика, дату, олимпиаду, этап,
  длительность и (по желанию) свой текст вступления; вариант подбирается
  под класс ученика автоматически (свежий год, полный комплект с
  решениями, без задач «требует проверки»);
* или из кода: ``assign(user_id, date, slug='rosatom', stage='final')``;
* разовые назначения при деплое — список SEED ниже (идемпотентно).

Поток ученика: в задачах дня на эту дату вместо занятия/выходного —
карточка с текстом вступления, «Старт» (таймер) и «Сменить пробник»
(до старта). На странице работы: условия (LaTeX, чертежи), к каждой
задаче — фото из тетради (распознаётся сразу) и поле для текста, краткий
ответ не нужен. «Сдать» или конец таймера → ИИ проверяет каждую задачу
по шкале 0–7 (DeepSeek v4-pro с рассуждением), сумма баллов → куратор
(тоже v4-pro с рассуждением) разбирает работу, пишет ученику в чат план
обучения и при явной необходимости меняет уровень задач дня; ученику
приходит push и баннер-уведомление на сайте.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger('formyla.probnik_assign')

MODEL = 'deepseek-v4-pro'
TASK_MAX = 7                       # шкала платформы 0–7 за задачу (как ВсОШ)
DEFAULT_DURATION_MIN = 180
GRADE_TIMEOUT_SEC = 300            # проверка одной задачи с рассуждением
REVIEW_TIMEOUT_SEC = 300
MAX_PHOTOS_PER_TASK = 6
TEXT_LIMIT = 8000

# Родительный падеж для текста «выдали вам пробник …»
OLYMPIAD_GENITIVE = {
    'rosatom': 'Росатома',
    'vsosh': 'ВсОШ',
    'phystech': 'Физтеха',
    'lomonosov': 'Ломоносова',
}

STAGE_LABELS = {
    'final': 'заключительный этап',
    'qual': 'отборочный этап',
    'dist': 'дистанционный тур',
    'school': 'школьный этап',
    'municipal': 'муниципальный этап',
    'regional': 'региональный этап',
}

DEFAULT_INTRO = (
    'По вашей просьбе выдали вам пробник {olympiad} — {stage}. '
    'Вам желательно прикреплять фото из тетрадки с решением — ИИ его разберёт. '
    'У вас доступно {hours}. Нажмите «Старт» — таймер запустится. '
    'Оценим текущее состояние и на базе результата сделаем точный процесс обучения.'
)

# Разовые назначения при деплое (идемпотентно по (ученик, дата)).
# who: {'id': N} | {'nickname': '...'} | {'email': '...'} |
#      {'find_name': 'роман'} — единственный Premium-ученик с таким именем.
# mirror: взять тот же вариант, что у другой записи SEED (по 'key').
SEED: List[Dict[str, Any]] = [
    {'key': 'roman', 'who': {'find_name': ['роман', 'roman']}, 'date': '2026-11-09',
     'slug': 'rosatom', 'stage': 'final'},
    # Лаврик — в субботу то же, что у Романа в понедельник (проверка)
    {'key': 'lavrik', 'who': {'id': 5}, 'date': '2026-11-07',
     'slug': 'rosatom', 'stage': 'final', 'mirror': 'roman'},
]

_NUM_RE = re.compile(r'^\s*(\S+)')
_VAR_RE = re.compile(r'\(вар\.\s*([^)]+)\)')
_TAG_RE = re.compile(r'\[([^\]]+)\]')

_running_lock = threading.Lock()
_running: set = set()   # id назначений, которые сейчас проверяются (в этом процессе)


# ─── Варианты из каталога ─────────────────────────────────────────────────

def _stage_of(round_name: str) -> Optional[str]:
    r = str(round_name or '').lower()
    for key, st in (('заключ', 'final'), ('финал', 'final'), ('отбороч', 'qual'),
                    ('дистанц', 'dist'), ('школьн', 'school'),
                    ('муниципальн', 'municipal'), ('региональн', 'regional')):
        if key in r:
            return st
    return None


def _nat(s: str) -> Tuple:
    return tuple(int(p) if p.isdigit() else p for p in re.split(r'(\d+)', s or ''))


def _fig_url(path: str) -> str:
    return f'/static/olymp_figures/{path}'


def candidate_variants(slug: str, grade: Optional[int],
                       stage: Optional[str] = 'final') -> List[Dict[str, Any]]:
    """Полные комплекты (год, этап, класс, вариант) по порядку выдачи.

    Комплект — задачи с одинаковыми (год, этап, класс, вариант, теги
    комплекта/выезда). Берём только полные: ≥3 задач, номера без дублей,
    у каждой есть условие и решение, нет статуса «требует проверки».
    Порядок: свежий год → старый; при равенстве — где все решения
    официальные; затем по номеру варианта.
    """
    from services.real_probnik import _load_catalog
    tasks = _load_catalog(slug) or []
    groups: Dict[Tuple, List[Dict[str, Any]]] = {}
    for t in tasks:
        if not isinstance(t, dict):
            continue
        try:
            g = int(t.get('grade'))
            y = int(t.get('year'))
        except (TypeError, ValueError):
            continue
        if grade is not None and g != int(grade):
            continue
        if stage and _stage_of(t.get('round')) != stage:
            continue
        num = str(t.get('num') or '')
        m = _NUM_RE.match(num)
        if not m:
            continue
        var = _VAR_RE.search(num)
        tags = tuple(_TAG_RE.findall(num))
        key = (y, str(t.get('round')), g, var.group(1).strip() if var else '', tags)
        groups.setdefault(key, []).append(t)

    out = []
    for key, vt in groups.items():
        y, rnd, g, var, tags = key
        bases = [_NUM_RE.match(str(t['num'])).group(1) for t in vt]
        if len(vt) < 3 or len(set(bases)) != len(bases):
            continue
        if any(not (t.get('text') or '').strip() or not (t.get('solution') or '').strip()
               for t in vt):
            continue
        if any(t.get('status') == 'needs_review' for t in vt):
            continue
        snap = []
        for base, t in sorted(zip(bases, vt), key=lambda p: _nat(p[0])):
            snap.append({
                'num': base,
                'uid': t.get('uid'),
                'text': (t.get('text') or '').strip(),
                'solution': (t.get('solution') or '').strip(),
                'answer': (t.get('answer') or '').strip(),
                'fig_statement': [_fig_url(f) for f in (t.get('fig_statement') or [])],
                'fig_solution': [_fig_url(f) for f in (t.get('fig_solution') or [])],
            })
        label = []
        if var:
            label.append(f'вариант {var}')
        label += [x for x in tags]
        vkey = f'{slug}|{y}|{rnd}|{g}|{var}|{"/".join(tags)}'
        out.append({
            'key': vkey[:200],
            'year': y, 'round': rnd, 'grade': g, 'variant': var, 'tags': list(tags),
            'all_official': all(t.get('status') == 'official_found' for t in vt),
            'label': ', '.join(label),
            'tasks': snap,
        })
    out.sort(key=lambda v: (-v['year'], not v['all_official'], _nat(v['variant']),
                            v['tags']))
    return out


def _olympiad_name(slug: str) -> str:
    try:
        from services.real_probnik import _competition_name
        return _competition_name(slug)
    except Exception:  # noqa: BLE001
        return slug


def _variant_title(slug: str, v: Dict[str, Any]) -> str:
    # учебный год: «2023/24» (каталог хранит год начала сезона)
    season = f"{v['year']}/{str(v['year'] + 1)[-2:]}"
    t = f"{_olympiad_name(slug)}, {v['round'].lower()} {season}, {v['grade']} класс"
    if v.get('label'):
        t += f" ({v['label']})"
    return t[:300]


def hours_text(minutes: int) -> str:
    h, m = divmod(int(minutes or 0), 60)
    def _h(n):
        if n % 10 == 1 and n % 100 != 11:
            return f'{n} час'
        if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
            return f'{n} часа'
        return f'{n} часов'
    if h and m:
        return f'{_h(h)} {m} минут'
    if h:
        return _h(h)
    return f'{m} минут'


def intro_for(a) -> str:
    tpl = a.intro_text or DEFAULT_INTRO
    try:
        return tpl.format(
            olympiad=OLYMPIAD_GENITIVE.get(a.olympiad_slug) or f'«{a.olympiad_name or a.olympiad_slug}»',
            stage=STAGE_LABELS.get(a.stage or '', a.stage or ''),
            hours=hours_text(a.duration_minutes),
            title=a.title,
        )
    except (KeyError, IndexError, ValueError):
        return tpl


# ─── Назначение / смена ───────────────────────────────────────────────────

def _models():
    from models import db
    from models_probnik_assign import (ProbnikAssignment, ProbnikAssignmentAnswer,
                                       ProbnikAssignmentPhoto)
    return db, ProbnikAssignment, ProbnikAssignmentAnswer, ProbnikAssignmentPhoto


def user_grade(user_id: int) -> Optional[int]:
    try:
        from curator.session_plan import _user_grade
        g = _user_grade(user_id)
        if g:
            return int(g)
    except Exception:  # noqa: BLE001
        pass
    try:
        from models_curator import CuratorState
        from services.intake_service import _prep_state_dict
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        intake = (_prep_state_dict(cs) or {}).get('intake') or {} if cs else {}
        if intake.get('class_level'):
            return int(intake['class_level'])
    except Exception:  # noqa: BLE001
        pass
    return None


def _grade_with_variants(slug: str, grade: Optional[int], stage: str) -> Tuple[Optional[int], List]:
    """Класс ученика; если для него вариантов нет — ближайший класс, где есть."""
    if grade:
        vs = candidate_variants(slug, grade, stage)
        if vs:
            return grade, vs
    for g in sorted(range(5, 12), key=lambda x: (abs(x - (grade or 9)), -x)):
        vs = candidate_variants(slug, g, stage)
        if vs:
            return g, vs
    return grade, []


def assign(user_id: int, on_date: date, slug: str = 'rosatom', stage: str = 'final',
           duration_minutes: int = DEFAULT_DURATION_MIN, intro_text: Optional[str] = None,
           grade: Optional[int] = None, variant_key: Optional[str] = None,
           created_by: Optional[int] = None):
    """Назначить пробник на дату (идемпотентно: вернёт существующий)."""
    db, PA, _, _ = _models()
    existing = PA.query.filter_by(user_id=user_id, assigned_date=on_date).first()
    if existing is not None:
        return existing
    g, variants = _grade_with_variants(slug, grade or user_grade(user_id), stage)
    if not variants:
        raise ValueError(f'нет полных вариантов {slug}/{stage}')
    v = next((x for x in variants if x['key'] == variant_key), None) or variants[0]
    a = PA(
        user_id=user_id, assigned_date=on_date, olympiad_slug=slug,
        olympiad_name=_olympiad_name(slug), stage=stage, grade=g,
        variant_key=v['key'], title=_variant_title(slug, v),
        tasks_json=json.dumps(v['tasks'], ensure_ascii=False),
        used_variants_json=json.dumps([v['key']], ensure_ascii=False),
        duration_minutes=int(duration_minutes or DEFAULT_DURATION_MIN),
        intro_text=intro_text or None, created_by=created_by,
    )
    db.session.add(a)
    db.session.commit()
    logger.info('[probnik_assign] user=%s date=%s %s', user_id, on_date, a.title)
    return a


def swap_variant(a) -> bool:
    """«Сменить пробник»: следующий полный вариант того же класса (до старта)."""
    db, *_ = _models()
    if a.status != 'assigned':
        return False
    variants = candidate_variants(a.olympiad_slug, a.grade, a.stage)
    if len(variants) < 2:
        return False
    used = json.loads(a.used_variants_json or '[]')
    nxt = next((v for v in variants if v['key'] not in used), None)
    if nxt is None:            # все перебраны — по кругу, но не текущий
        used = [a.variant_key]
        nxt = next(v for v in variants if v['key'] != a.variant_key)
    a.variant_key = nxt['key']
    a.title = _variant_title(a.olympiad_slug, nxt)
    a.tasks_json = json.dumps(nxt['tasks'], ensure_ascii=False)
    a.used_variants_json = json.dumps(used + [nxt['key']], ensure_ascii=False)
    a.swaps = (a.swaps or 0) + 1
    db.session.commit()
    return True


def for_date(user_id: int, on_date: date):
    try:
        db, PA, *_ = _models()
        return PA.query.filter_by(user_id=user_id, assigned_date=on_date).first()
    except Exception:  # noqa: BLE001
        logger.exception('[probnik_assign] lookup failed')
        try:
            from models import db as _db
            _db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def tasks_of(a) -> List[Dict[str, Any]]:
    try:
        return json.loads(a.tasks_json or '[]')
    except ValueError:
        return []


# ─── Таймер ───────────────────────────────────────────────────────────────

def start(a) -> None:
    db, *_ = _models()
    if a.status != 'assigned':
        return
    now = datetime.utcnow()
    a.status = 'started'
    a.started_at = now
    a.deadline_at = now + timedelta(minutes=int(a.duration_minutes or DEFAULT_DURATION_MIN))
    db.session.commit()


def seconds_left(a) -> Optional[int]:
    if a.status != 'started' or not a.deadline_at:
        return None
    return max(0, int((a.deadline_at - datetime.utcnow()).total_seconds()))


def refresh(a, app=None):
    """Ленивые переходы: время вышло → автосдача; зависшая проверка → заново."""
    if a.status == 'started' and a.deadline_at and datetime.utcnow() >= a.deadline_at + timedelta(seconds=30):
        submit(a, auto=True, app=app)
    elif a.status == 'grading' and a.submitted_at and \
            datetime.utcnow() - a.submitted_at > timedelta(minutes=20) and a.id not in _running:
        _launch_grading(a.id, app)
    return a


# ─── Работа ученика: текст и фото ─────────────────────────────────────────

def can_edit(a) -> bool:
    return a.status == 'started' and (seconds_left(a) or 0) > 0


def save_text(a, idx: int, text: str) -> None:
    db, _, PAA, _ = _models()
    row = PAA.query.filter_by(assignment_id=a.id, task_idx=idx).first()
    if row is None:
        row = PAA(assignment_id=a.id, task_idx=idx)
        db.session.add(row)
    row.text = (text or '')[:TEXT_LIMIT]
    row.updated_at = datetime.utcnow()
    db.session.commit()


def add_photo(a, idx: int, photo_bytes: bytes, content_type: str, filename: str, app=None):
    """Сохранить фото и запустить распознавание в фоне. → строка фото."""
    import base64
    db, _, _, PAP = _models()
    from services.photo_upload import prepare_photo
    photo_bytes, content_type = prepare_photo(photo_bytes, content_type, filename or '')
    if PAP.query.filter_by(assignment_id=a.id, task_idx=idx).count() >= MAX_PHOTOS_PER_TASK:
        raise ValueError(f'К одной задаче — не больше {MAX_PHOTOS_PER_TASK} фото.')
    url = None
    try:
        from services.storage import upload_photo
        url, _ = upload_photo(photo_bytes, a.user_id, content_type)
    except Exception as e:  # noqa: BLE001 — хранилища может не быть: распознаём всё равно
        logger.warning('[probnik_assign] storage unavailable: %s', e)
    row = PAP(assignment_id=a.id, task_idx=idx, url=url, ocr_status='pending')
    db.session.add(row)
    db.session.commit()
    task_text = (tasks_of(a)[idx] or {}).get('text', '') if idx < len(tasks_of(a)) else ''
    b64 = base64.b64encode(photo_bytes).decode('ascii')
    _bg(app, _ocr_job, row.id, b64, task_text)
    return row


def _ocr_job(photo_id: int, b64: str, task_text: str) -> None:
    db, _, _, PAP = _models()
    text, ok = '', False
    try:
        from services.solution_ocr import ocr_solution_images
        meta = ocr_solution_images([b64], task_text)
        text = (meta.get('text') or '').strip()
        ok = bool(text)
    except Exception:  # noqa: BLE001
        logger.exception('[probnik_assign] ocr failed photo=%s', photo_id)
    row = db.session.get(PAP, photo_id)
    if row is not None:
        row.ocr_status = 'ok' if ok else 'failed'
        row.ocr_text = text or None
        db.session.commit()


def _bg(app, fn, *args) -> None:
    """Запуск в фоне с контекстом приложения (gunicorn gthread — потоки ок)."""
    if app is None:
        from flask import current_app
        app = current_app._get_current_object()

    def _run():
        with app.app_context():
            try:
                fn(*args)
            except Exception:  # noqa: BLE001
                logger.exception('[probnik_assign] background job failed')
                try:
                    from models import db
                    db.session.rollback()
                except Exception:  # noqa: BLE001
                    pass
    threading.Thread(target=_run, daemon=True).start()


def work_state(a) -> List[Dict[str, Any]]:
    """Задачи + работа ученика + итоги проверки (для страницы и JSON)."""
    db, _, PAA, PAP = _models()
    answers = {r.task_idx: r for r in PAA.query.filter_by(assignment_id=a.id).all()}
    photos: Dict[int, list] = {}
    stale = datetime.utcnow() - timedelta(minutes=5)
    for p in PAP.query.filter_by(assignment_id=a.id).order_by(PAP.id).all():
        if p.ocr_status == 'pending' and p.created_at and p.created_at < stale:
            p.ocr_status = 'failed'      # фоновое распознавание потерялось (рестарт)
            db.session.commit()
        photos.setdefault(p.task_idx, []).append({
            'id': p.id, 'url': p.url, 'ocr_status': p.ocr_status,
            'ocr_text': p.ocr_text or '',
        })
    out = []
    for i, t in enumerate(tasks_of(a)):
        ans = answers.get(i)
        out.append({
            'idx': i, **t,
            'student_text': (ans.text if ans else '') or '',
            'photos': photos.get(i, []),
            'score': ans.score if ans else None,
            'max_score': (ans.max_score if ans and ans.max_score else TASK_MAX),
            'verdict': ans.verdict if ans else None,
            'feedback': ans.feedback if ans else None,
        })
    return out


# ─── Сдача и проверка ─────────────────────────────────────────────────────

def submit(a, auto: bool = False, app=None) -> None:
    db, *_ = _models()
    if a.status != 'started':
        return
    a.status = 'grading'
    a.submitted_at = datetime.utcnow()
    a.auto_submitted = bool(auto)
    db.session.commit()
    _launch_grading(a.id, app)


def _launch_grading(assignment_id: int, app=None) -> None:
    with _running_lock:
        if assignment_id in _running:
            return
        _running.add(assignment_id)

    def _job(aid):
        try:
            grade_and_review(aid)
        finally:
            with _running_lock:
                _running.discard(aid)
    _bg(app, _job, assignment_id)


def _llm(messages: List[Dict[str, str]], thinking: bool, max_tokens: int,
         timeout: int) -> str:
    from daily_tasks.pipeline.deepseek_client import DeepSeekClient

    async def _run() -> str:
        async with DeepSeekClient() as client:
            client._model = MODEL
            text, _usage = await client.chat(MODEL, messages, temperature=0.2,
                                             max_tokens=max_tokens, thinking=thinking)
            return text or ''
    return asyncio.run(asyncio.wait_for(_run(), timeout=timeout))


GRADER_SYSTEM = (
    'Ты — член жюри олимпиады школьников по математике. Проверяешь работу ученика '
    'по одной задаче и ставишь балл по шкале 0–7 (как на ВсОШ):\n'
    '7 — полное верное обоснованное решение; 5–6 — верное решение с недочётами; '
    '3–4 — существенное продвижение, но решение не доведено или есть пробел в обосновании; '
    '1–2 — отдельные верные идеи или верный ответ без обоснования; 0 — нет продвижения, '
    'решение неверно или работы нет.\n'
    'Сверяйся с эталонным решением, но засчитывай и другие верные способы. '
    'Работа ученика распознана с фото тетради — не снижай балл за очевидные ошибки '
    'распознавания (перепутанные символы, оборванные строки), оценивай смысл.\n'
    'Ответь СТРОГО одним JSON-объектом без markdown:\n'
    '{"score": целое 0..7, "verdict": "full"|"partial"|"wrong", '
    '"feedback": "3–6 предложений ученику на «ты»: что верно, где ошибка или пробел, '
    'какой ключевой шаг был нужен; формулы в \\\\( ... \\\\)", '
    '"gaps": ["навык или тема, которых не хватило (коротко)", ...]}'
)


def _student_work(text: str, photos: List[Dict[str, Any]]) -> str:
    parts = []
    if (text or '').strip():
        parts.append('[Текст ученика]\n' + text.strip())
    for k, p in enumerate(photos, 1):
        if p.get('ocr_text'):
            parts.append(f'[Фото {k}, распознано]\n' + p['ocr_text'])
    return '\n\n'.join(parts)


def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
    raw = (raw or '').strip()
    raw = re.sub(r'^```(?:json)?|```$', '', raw).strip()
    m = re.search(r'\{[\s\S]*\}', raw)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        try:   # частая ошибка модели: одиночные обратные слэши LaTeX
            return json.loads(re.sub(r'(?<!\\)\\(?![\\"/bfnrtu])', r'\\\\', m.group(0)))
        except ValueError:
            return None


def grade_task(task: Dict[str, Any], work: str) -> Dict[str, Any]:
    """Балл 0–7 и разбор по одной задаче. Пустая работа — 0 без вызова ИИ."""
    if not work.strip():
        return {'score': 0, 'verdict': 'empty', 'gaps': [],
                'feedback': 'Решение не прислано — задача оценена в 0 баллов.'}
    user = (f"Условие задачи:\n{task.get('text', '')}\n\n"
            f"Эталонное решение:\n{task.get('solution', '')}\n\n"
            f"Эталонный ответ: {task.get('answer') or '—'}\n\n"
            f"Работа ученика:\n{work[:12000]}")
    last_err = None
    for _attempt in range(2):
        try:
            raw = _llm([{'role': 'system', 'content': GRADER_SYSTEM},
                        {'role': 'user', 'content': user}],
                       thinking=True, max_tokens=6000, timeout=GRADE_TIMEOUT_SEC)
            data = _parse_json(raw)
            if data is None:
                raise ValueError('no json')
            score = max(0, min(TASK_MAX, int(round(float(data.get('score', 0))))))
            verdict = data.get('verdict') if data.get('verdict') in ('full', 'partial', 'wrong') else (
                'full' if score == TASK_MAX else 'partial' if score else 'wrong')
            gaps = [str(g)[:120] for g in (data.get('gaps') or []) if g][:5]
            return {'score': score, 'verdict': verdict, 'gaps': gaps,
                    'feedback': str(data.get('feedback') or '').strip()[:4000]}
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning('[probnik_assign] grade attempt failed: %r', e)
    return {'score': None, 'verdict': None, 'gaps': [], 'error': repr(last_err),
            'feedback': 'Автопроверка этой задачи не удалась — куратор проверит её вручную.'}


REVIEW_SYSTEM = (
    'Ты — куратор платформы FORMYLA, эксперт по олимпиадам по математике. Твой ученик '
    'только что написал пробник — реальный вариант олимпиады прошлых лет, работу '
    'проверило жюри (баллы 0–7 за задачу). Напиши ученику сообщение-разбор на «ты», '
    'тепло и по-деловому, без канцелярита, 220–380 слов, обычным текстом (можно '
    'короткие списки через «—», формулы в \\( ... \\)). Структура:\n'
    '1) Итог: сумма баллов и одной строкой по каждой задаче.\n'
    '2) Что получилось — конкретно.\n'
    '3) Главные пробелы — 2–4 конкретных темы/навыка (из разбора задач, не выдумывай).\n'
    '4) План обучения на ближайшие 2 недели: что делаем на занятиях (темы, методы, '
    'типы задач), в каком порядке и зачем; ориентир — следующий пробник через 2 недели.\n'
    '5) Конкретный первый шаг на завтра.\n'
    'Не обещай лёгких побед, не стыди. Опирайся только на данные ниже.\n'
    'Если результат явно выше уровня задач дня ученика (≥75% баллов) — последней '
    'отдельной строкой добавь [[ACTION {"type": "raise_level"}]]; если явно ниже '
    '(≤15% баллов при непустой работе) — [[ACTION {"type": "lower_level"}]]; иначе '
    'ничего не добавляй.'
)


def _review_fallback(a, rows) -> str:
    lines = [f'Посмотрел твой пробник: {a.total_score} из {a.max_score} баллов.']
    for r in rows:
        s = '—' if r['score'] is None else f"{r['score']}/{TASK_MAX}"
        lines.append(f"— задача {r['num']}: {s}")
    gaps = sorted({g for r in rows for g in (r.get('gaps') or [])})
    if gaps:
        lines.append('Над чем работаем в ближайшие две недели: ' + '; '.join(gaps[:4]) + '.')
    lines.append('Разбор каждой задачи — на странице пробника. Завтра начнём с первой темы из списка.')
    return '\n'.join(lines)


def grade_and_review(assignment_id: int) -> None:
    """Проверка всех задач → сумма → разбор куратора → уведомление ученику."""
    db, PA, PAA, _ = _models()
    a = db.session.get(PA, assignment_id)
    if a is None or a.status not in ('grading', 'failed'):
        return
    state = work_state(a)
    works = [(t, _student_work(t['student_text'], t['photos'])) for t in state]
    with ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(lambda tw: grade_task(tw[0], tw[1]), works))

    rows = []
    for (t, _w), r in zip(works, results):
        ans = PAA.query.filter_by(assignment_id=a.id, task_idx=t['idx']).first()
        if ans is None:
            ans = PAA(assignment_id=a.id, task_idx=t['idx'])
            db.session.add(ans)
        ans.score = r['score']
        ans.max_score = TASK_MAX
        ans.verdict = r['verdict']
        ans.feedback = r['feedback']
        ans.updated_at = datetime.utcnow()
        rows.append({'num': t['num'], **r})
    a.total_score = sum(r['score'] or 0 for r in rows)
    a.max_score = TASK_MAX * len(rows)
    a.graded_at = datetime.utcnow()
    failed = [r for r in rows if r['score'] is None]
    a.grading_error = (f'не проверено задач: {len(failed)}' if failed else None)
    db.session.commit()

    review = _curator_review(a, rows)
    a.curator_review = review
    a.status = 'reviewed'
    a.reviewed_at = datetime.utcnow()
    db.session.commit()
    _notify(a, review)


def _curator_review(a, rows) -> str:
    facts = [f'Пробник: {a.title}. Класс ученика: {a.grade}.',
             f'Итог: {a.total_score} из {a.max_score} баллов'
             + (' (сдан автоматически — закончилось время)' if a.auto_submitted else '') + '.']
    for r in rows:
        s = 'не проверено' if r['score'] is None else f"{r['score']}/{TASK_MAX}"
        facts.append(f"Задача {r['num']}: {s}. Разбор жюри: {r['feedback']} "
                     f"Пробелы: {', '.join(r.get('gaps') or []) or '—'}.")
    try:
        from services.curator_chat import build_context, _context_block
        facts.append(_context_block(build_context(a.user_id)))
    except Exception as e:  # noqa: BLE001
        logger.warning('[probnik_assign] curator ctx failed: %r', e)
    text = ''
    try:
        text = _llm([{'role': 'system', 'content': REVIEW_SYSTEM},
                     {'role': 'user', 'content': '\n'.join(facts)}],
                    thinking=True, max_tokens=6000, timeout=REVIEW_TIMEOUT_SEC).strip()
    except Exception as e:  # noqa: BLE001
        logger.warning('[probnik_assign] review failed: %r', e)
    if not text:
        return _review_fallback(a, rows)
    # действия куратора: только уровень задач дня (решение по объективному баллу)
    actions = []
    for m in re.finditer(r'\[\[\s*ACTION\s*(\{.*?\})\s*\]\]', text, re.S):
        try:
            act = json.loads(m.group(1))
            if act.get('type') in ('raise_level', 'lower_level'):
                actions.append(act)
        except ValueError:
            pass
    text = re.sub(r'\[\[\s*ACTION\s*\{.*?\}\s*\]\]', '', text, flags=re.S).strip()
    if actions:
        try:
            from services.curator_actions import run_actions
            notes = [r.get('message') for r in run_actions(a.user_id, actions[:1])]
            text += '\n\n' + '\n'.join(n for n in notes if n)
        except Exception as e:  # noqa: BLE001
            logger.info('[probnik_assign] curator actions unavailable: %r', e)
    return text


def _notify(a, review: str) -> None:
    """Сообщение куратора в чат + push. Баннер на сайте — по review_seen_at."""
    db, *_ = _models()
    try:
        from services.curator_chat import add_message
        add_message(a.user_id, 'curator',
                    f'Разбор пробника «{a.title}»\n\n{review}',
                    meta={'type': 'probnik_review', 'assignment_id': a.id})
        db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()
        logger.exception('[probnik_assign] chat message failed')
    try:
        from curator.push_service import send_curator_push
        send_curator_push(a.user_id, 'Куратор разобрал твой пробник',
                          f'{a.total_score} из {a.max_score} баллов. Открой разбор и план обучения.',
                          url=f'/probnik-assign/{a.id}')
    except Exception:  # noqa: BLE001
        logger.exception('[probnik_assign] push failed')


def unseen_review(user_id: int):
    """Разобранный куратором пробник, который ученик ещё не открыл (для баннера)."""
    try:
        _, PA, *_ = _models()
        return (PA.query.filter(PA.user_id == user_id, PA.status == 'reviewed',
                                PA.review_seen_at.is_(None))
                .order_by(PA.reviewed_at.desc()).first())
    except Exception:  # noqa: BLE001
        try:
            from models import db
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def context_lines(user_id: int) -> List[str]:
    """Строки для «Данных ученика» куратора: последние результаты пробников."""
    try:
        _, PA, PAA, _ = _models()
        rows = (PA.query.filter(PA.user_id == user_id, PA.status == 'reviewed')
                .order_by(PA.reviewed_at.desc()).limit(3).all())
        out = []
        for a in rows:
            out.append(f'- пробник {a.assigned_date:%d.%m}: {a.title} — '
                       f'{a.total_score} из {a.max_score} баллов (разбор и план обучения уже отправлены ученику; '
                       f'опирайся на них)')
        return out
    except Exception:  # noqa: BLE001
        return []


# ─── Плановые задачи ──────────────────────────────────────────────────────

def sweep(app=None) -> int:
    """Раз в 5 минут: автосдача по таймеру и перезапуск зависших проверок."""
    _, PA, *_ = _models()
    n = 0
    now = datetime.utcnow()
    for a in PA.query.filter(PA.status.in_(('started', 'grading'))).all():
        before = a.status
        refresh(a, app=app)
        n += int(a.status != before)
    return n


def _resolve_user(who: Dict[str, Any]):
    from models import User
    if who.get('id'):
        return User.query.get(int(who['id']))
    if who.get('nickname'):
        return User.query.filter(User.nickname.ilike(who['nickname'])).first()
    if who.get('email'):
        return User.query.filter(User.email.ilike(who['email'])).first()
    if who.get('find_name'):
        from services.pilot import has_premium_access
        # имя или ник НАЧИНАЕТСЯ с образца («Роман …», «roman…»), не «Романов»
        conds = []
        for p in who['find_name']:
            conds += [User.name.ilike(f'{p} %'), User.name.ilike(p),
                      User.nickname.ilike(f'{p}%')]
        from sqlalchemy import or_
        cands = User.query.filter(or_(*conds)).limit(200).all()
        cands = [u for u in cands if not u.is_admin and has_premium_access(u)]
        if len(cands) == 1:
            return cands[0]
        logger.warning('[probnik_assign] seed %r: найдено %d Premium-учеников — пропуск '
                       '(назначьте в /probnik-assign/admin)', who, len(cands))
    return None


def ensure_seed() -> List[str]:
    """Разовые назначения из SEED (идемпотентно). Прошедшие даты пропускаем."""
    db, PA, *_ = _models()
    done: Dict[str, Any] = {}
    log = []
    for s in SEED:
        try:
            d = date.fromisoformat(s['date'])
            u = _resolve_user(s['who'])
            if u is None:
                log.append(f"{s['key']}: ученик не найден")
                continue
            ex = PA.query.filter_by(user_id=u.id, assigned_date=d).first()
            if ex is not None:
                done[s['key']] = ex
                continue
            if d < date.today():
                continue
            mirror = done.get(s.get('mirror') or '')
            a = assign(u.id, d, slug=s['slug'], stage=s['stage'],
                       grade=(mirror.grade if mirror else None),
                       variant_key=(mirror.variant_key if mirror else None))
            done[s['key']] = a
            log.append(f"{s['key']}: user={u.id} {d} {a.title}")
        except Exception as e:  # noqa: BLE001
            db.session.rollback()
            log.append(f"{s['key']}: ошибка {e!r}")
    return log
