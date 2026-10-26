# -*- coding: utf-8 -*-
"""
curator/session_plan.py — SESSION_PLAN_V1 (26.10.2026): план занятий 1-из-6.

Ротация занятий в блоке из шести (регламент тарифов Premium):
  занятие 1 — ИЗУЧЕНИЕ МЕТОДА (70% разбор метода + 3 задачи по методу)
  занятия 2-5 — ПРАКТИКА (задачи дня по теме, которую назначил куратор)
  занятие 6 — РЕАЛЬНЫЙ ПРОБНИК (полный вариант прошлых лет выбранной
              олимпиады, длительность по регламенту)

Для «Работяги» (6 занятий/нед) блок = 1 неделя: метод + 4 практики +
пробник каждую неделю. Для «Спокойного» (3 занятия/нед) блок = 2 недели.

Правила (см. ревью 26.10.2026, обновление «план на 6 занятий» того же дня):
  * ПЛАН СДВИГАЕТСЯ КАЖДЫЙ ДЕНЬ: тип занятия определяется слотом по счёту
    СОЗДАННЫХ уроков (завершённых и пропущенных), а не только завершённых;
  * ПРОПУЩЕННОЕ ЗАНЯТИЕ — В ДОЛГ: если день прошёл без завершения,
    занятие помечается 'skipped' и показывается в списке долгов; система
    идёт дальше (следующий день — следующий слот);
  * завершение занятия — серверная транзиция: практика — отвечены все
    задачи сета дня; метод — отвечены все задачи метод-сета; пробник —
    сдан пробник (stage_submit). Повторный вызов не двигает прогресс;
  * синхронизация долгов не зависит от захода на дашборд: её вызывают и
    хуки завершения (maybe_complete_*), и чтение плана (session_info);
  * расписание доступно только пилотным аккаунтам (victor, lavrik);
    остальным всё остаётся как было (функции возвращают inactive);
  * тема практики — та, что назначает куратор (ротация цикла
    monthly_cycle), привязанная к выбранной олимпиаде пользователя.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from models import db

logger = logging.getLogger(__name__)

BLOCK_SIZE = 6
TABLE_NAME = 'curator_lessons'

LESSON_LABELS = {
    'method': 'изучение метода',
    'practice': 'практика',
    'probnik': 'пробник',
}


def ensure_tables() -> None:
    # id: SERIAL для PostgreSQL, AUTOINCREMENT для SQLite (тесты)
    id_col = "SERIAL PRIMARY KEY" if _is_pg() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    db.session.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
            id {id_col},
            user_id INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            lesson_type VARCHAR(16) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'assigned',
            theme VARCHAR(128),
            method_code VARCHAR(64),
            method_name VARCHAR(256),
            probnik_code VARCHAR(64),
            probnik_title VARCHAR(256),
            olympiad_slug VARCHAR(64),
            assigned_date DATE,
            completed_at TIMESTAMP,
            completed_set_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """))
    # защита от дублей при параллельной синхронизации долгов (user_id, seq)
    db.session.execute(text(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {TABLE_NAME}_user_seq "
        f"ON {TABLE_NAME} (user_id, seq)"
    ))
    # старые установки (до 26.10.2026) могут быть без колонки completed_set_id
    try:
        if _is_pg():
            db.session.execute(text(
                f"ALTER TABLE {TABLE_NAME} ADD COLUMN IF NOT EXISTS completed_set_id INTEGER"
            ))
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] completed_set_id migration failed: %r', e)
    db.session.commit()


def _is_pg() -> bool:
    try:
        return 'postgres' in (db.session.get_bind().dialect.name or '')
    except Exception:  # noqa: BLE001
        return False


def _pilot(user_id: int) -> bool:
    try:
        from services.pilot import is_pilot_user
        return bool(is_pilot_user(int(user_id)))
    except Exception:
        return False


# ── Выбор олимпиады и класса пользователя ────────────────────────────────

def _user_olympiad(user_id: int) -> Optional[str]:
    """Slug олимпиады из активного prep-плана (каноническое хранилище выбора)."""
    try:
        row = db.session.execute(text(
            "SELECT op.slug FROM prep_plans pp "
            "JOIN olympiad_prep op ON op.id = pp.olympiad_id "
            "WHERE pp.user_id = :uid AND pp.status = 'active' "
            "ORDER BY pp.id DESC LIMIT 1"
        ), {'uid': user_id}).fetchone()
        return row[0] if row else None
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] olympiad lookup failed: %r', e)
        return None


def _user_grade(user_id: int) -> Optional[int]:
    try:
        from models_curator import CuratorState
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs and cs.grade:
            return int(cs.grade)
    except Exception:
        pass
    try:
        from models import User
        u = User.query.get(user_id)
        if u:
            g = getattr(u, 'preferred_grade', None) or getattr(u, 'class_level', None)
            if g:
                return int(g)
    except Exception:
        pass
    return None


def _theme_for_user(user_id: int) -> Optional[str]:
    """Тема, назначенная куратором (ротация monthly_cycle)."""
    try:
        from curator.monthly_cycle import get_today_info
        return get_today_info(user_id).get('subtopic') or None
    except Exception:
        return None


# ── Подбор метода и пробника ─────────────────────────────────────────────

def _pick_method(user_id: int) -> Dict[str, str]:
    """Метод недели из method_week.catalog (тот же, что в плане куратора)."""
    try:
        from method_week.catalog import method_for_week
        m = method_for_week(user_id)
        if m:
            return {
                'code': m.get('method_code') or '',
                'name': m.get('method_name') or m.get('name_ru') or '',
            }
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] method pick failed: %r', e)
    return {'code': '', 'name': ''}


_OLYMP_COMPETITION = {
    'vsosh': 'ВсОШ',
    'euler': 'Европейская олимпиада «Эйлер»',
    'lomonosov': 'Ломоносов',
}


def _pick_probnik(user_id: int, olympiad_slug: Optional[str],
                  used_codes: set) -> Optional[Dict[str, str]]:
    """Реальный пробник: опубликованный, с задачами, под олимпиаду и класс.

    Требование 26.10.2026 (ревью ротации): пробник без задач — пустая
    страница, занятие-пробник застрянет. Поэтому:
      * берём ТОЛЬКО пробники, у которых есть задачи;
      * ищем точное совпадение по олимпиаде и классу; если нет — пробник
        подходящего класса; если и их нет — любой опубликованный с задачами;
      * если задач нет ни у одного пробника — None (CTA ведёт в список).
    """
    grade = _user_grade(user_id)
    competition = _OLYMP_COMPETITION.get(olympiad_slug or '', '') if olympiad_slug else ''
    try:
        rows = db.session.execute(text(
            "SELECT p.code, p.title, p.competition, p.grade, "
            "count(t.id) AS task_count FROM olympiad_probniks p "
            "LEFT JOIN olympiad_tasks t ON t.probnik_id = p.id "
            "WHERE p.is_published = TRUE "
            "GROUP BY p.id, p.code, p.title, p.competition, p.grade, p.sort_order "
            "HAVING count(t.id) > 0 "
            "ORDER BY p.sort_order NULLS LAST, p.id"
        )).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] probnik query failed: %r', e)
        return None

    def match(r) -> int:
        score = 0
        if competition and (competition.lower() in str(r[2] or '').lower()):
            score += 4
        if grade and str(r[3]) == str(grade):
            score += 2
        return score

    candidates = [r for r in rows if r[0] not in used_codes]
    if not candidates:
        candidates = list(rows)  # все пройдены — разрешаем повторный прогон
    if not candidates:
        return None
    best = sorted(candidates, key=match, reverse=True)[0]
    return {'code': best[0], 'title': best[1] or best[0]}


# ── Ротация и запись занятий ──────────────────────────────────────────────

def _lessons(user_id: int) -> List[Dict[str, Any]]:
    ensure_tables()
    rows = db.session.execute(text(
        f"SELECT id, seq, lesson_type, status, theme, method_code, method_name, "
        f"probnik_code, probnik_title, olympiad_slug, assigned_date, completed_at, "
        f"completed_set_id FROM {TABLE_NAME} WHERE user_id = :uid ORDER BY seq"
    ), {'uid': user_id}).fetchall()
    return [dict(zip(
        ('id', 'seq', 'lesson_type', 'status', 'theme', 'method_code',
         'method_name', 'probnik_code', 'probnik_title', 'olympiad_slug',
         'assigned_date', 'completed_at', 'completed_set_id'), r)) for r in rows]


def _completed_count(user_id: int) -> int:
    ensure_tables()
    row = db.session.execute(text(
        f"SELECT count(*) FROM {TABLE_NAME} "
        f"WHERE user_id = :uid AND status = 'completed'"
    ), {'uid': user_id}).fetchone()
    return int(row[0]) if row else 0


def _lesson_type_for_position(completed: int) -> str:
    """Занятие 1 блока — метод, занятие 6 — пробник, остальные — практика."""
    pos = (completed % BLOCK_SIZE) + 1
    if pos == 1:
        return 'method'
    if pos == BLOCK_SIZE:
        return 'probnik'
    return 'practice'


def _insert_lesson(user_id: int, seq: int, lesson_type: str,
                    status: str = 'assigned',
                    assigned: Optional[date] = None) -> None:
    theme = method_code = method_name = probnik_code = probnik_title = None
    olympiad_slug = _user_olympiad(user_id)
    if lesson_type == 'practice':
        theme = _theme_for_user(user_id)
    elif lesson_type == 'method':
        m = _pick_method(user_id)
        method_code, method_name = m['code'], m['name']
    elif lesson_type == 'probnik':
        used = {l['probnik_code'] for l in _lessons(user_id) if l['probnik_code']}
        p = _pick_probnik(user_id, olympiad_slug, used)
        if p:
            probnik_code, probnik_title = p['code'], p['title']
    db.session.execute(text(
        f"INSERT INTO {TABLE_NAME} "
        f"(user_id, seq, lesson_type, status, theme, method_code, method_name, "
        f"probnik_code, probnik_title, olympiad_slug, assigned_date) "
        f"VALUES (:uid, :seq, :lt, :st, :theme, :mc, :mn, :pc, :pt, :os, :ad) "
        f"ON CONFLICT (user_id, seq) DO NOTHING"
    ), {
        'uid': user_id, 'seq': seq, 'lt': lesson_type, 'st': status,
        'theme': theme,
        'mc': method_code, 'mn': method_name, 'pc': probnik_code,
        'pt': probnik_title, 'os': olympiad_slug,
        'ad': assigned or date.today(),
    })
    db.session.commit()
    logger.info('[session_plan] inserted lesson #%s type=%s status=%s user=%s',
                seq, lesson_type, status, user_id)


def _slot_of(seq: int) -> int:
    """Слот занятия в блоке 1-из-6: каждый созданный урок занимает
    следующий слот (завершён он или пропущен) — поэтому план сдвигается
    каждый день, а пропуски уходят в долг."""
    return ((seq - 1) % BLOCK_SIZE) + 1


def _to_date(v) -> Optional[date]:
    """assigned_date может прийти строкой (SQLite) или date (PostgreSQL)."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except (ValueError, TypeError):
            return None
    return None


def _sync(user_id: int) -> None:
    """Безопасная синхронизация расписания с календарём (никогда не бросает).

    При ошибке откатываем транзакцию: в PostgreSQL упавший стейтмент
    «отравляет» транзакцию — без rollback все последующие запросы тоже падали бы.
    """
    try:
        _advance_stale(user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] advance_stale failed: %r', e)
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass


def _ensure_today_lesson(user_id: int) -> None:
    """Создать сегодняшнее занятие, если его ещё нет.

    Нужно для хуков завершения (метод/пробник сдаются мимо дашборда):
    после синхронизации долгов назначенного занятия может не быть —
    создаём сегодняшнее, НО только если сегодняшний день ещё не закрыт
    (одно занятие в день: повторная сдача не порождает новое занятие).
    """
    try:
        if not _pilot(user_id):
            return
        lessons = _lessons(user_id)
        if lessons and _to_date(lessons[-1].get('assigned_date')) == date.today():
            return  # сегодняшний урок уже создан (или день уже закрыт)
        current_lesson(user_id)
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] ensure_today_lesson failed: %r', e)
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass


def _advance_stale(user_id: int) -> None:
    """Пропущенные занятия — в долг; система идёт дальше (владелец, 26.10).

    Только для пилотов (гейт в начале): не-пилоту нельзя менять его записи.

    Считаем по ДАТЕ последнего созданного урока (любого статуса — назначенного,
    завершённого или пропущенного), а не только по «открытому» занятию:
    если ученик завершил занятие и не заходил несколько дней, пропущенные
    дни всё равно набегают в долг.

    Правила:
      * последний урок назначен на прошлый день и ещё открыт ('assigned')
        → он сам становится долгом;
      * каждый ПОЛНОСТЬЮ пропущенный день между датой последнего урока
        и сегодня → ещё одно занятие в долг (слот по счёту, дата — тот
        пропущенный день);
      * все записи и пометки выполняются ОДНОЙ транзакцией — при обрыве
        ничего не «наполовину начисляется»;
      * INSERT ... ON CONFLICT DO NOTHING + уникальный индекс (user_id, seq)
        защищают от дублей при параллельных запросах;
      * повторный вызов в тот же день — no-op (идемпотентно).

    Сегодняшнее занятие затем создаётся как обычно (current_lesson) —
    план двигается ежедневно.
    """
    if not _pilot(user_id):
        return
    ensure_tables()
    lessons = _lessons(user_id)
    if not lessons:
        return
    last = lessons[-1]
    assigned = _to_date(last.get('assigned_date'))
    if assigned is None or assigned >= date.today():
        return  # урок назначен на сегодня (или дата битая) — синхронизировать нечего
    today = date.today()
    missed = (today - assigned).days  # сколько дней прошло с последнего урока
    # 1) незакрытый урок прошлого дня — сам становится долгом
    db.session.execute(text(
        f"UPDATE {TABLE_NAME} SET status = 'skipped' "
        f"WHERE user_id = :uid AND status = 'assigned' AND assigned_date < :today"
    ), {'uid': user_id, 'today': today})
    # 2) полностью пропущенные дни (между последним уроком и сегодня) — по занятию в долг;
    #    незакрытый урок прошлого дня уже посчитан пометкой выше (это день `assigned`),
    #    поэтому долги-вставки — только за дни ПОСЛЕ него
    olympiad_slug = _user_olympiad(user_id)
    for i in range(1, missed):
        day = assigned + timedelta(days=i)
        seq = last['seq'] + i
        lesson_type = _lesson_type_for_position(_slot_of(seq) - 1)
        # тема прошлого дня не восстанавливается — не подставляем сегодняшнюю;
        # метод/пробник — детерминированный выбор (как в _insert_lesson)
        theme = method_code = method_name = probnik_code = probnik_title = None
        if lesson_type == 'method':
            m = _pick_method(user_id)
            method_code, method_name = m['code'], m['name']
        elif lesson_type == 'probnik':
            used = {l['probnik_code'] for l in lessons if l['probnik_code']}
            p = _pick_probnik(user_id, olympiad_slug, used)
            if p:
                probnik_code, probnik_title = p['code'], p['title']
        db.session.execute(text(
            f"INSERT INTO {TABLE_NAME} "
            f"(user_id, seq, lesson_type, status, theme, method_code, method_name, "
            f"probnik_code, probnik_title, olympiad_slug, assigned_date) "
            f"VALUES (:uid, :seq, :lt, 'skipped', :theme, :mc, :mn, :pc, :pt, :os, :ad) "
            f"ON CONFLICT (user_id, seq) DO NOTHING"
        ), {
            'uid': user_id, 'seq': seq, 'lt': lesson_type,
            'theme': theme, 'mc': method_code, 'mn': method_name,
            'pc': probnik_code, 'pt': probnik_title, 'os': olympiad_slug,
            'ad': day,
        })
    db.session.commit()  # одна транзакция на всё начисление долгов
    logger.info('[session_plan] user=%s: начислено долгов за %d дн(я/ей)',
                user_id, missed)


def _current_assigned(user_id: int) -> Optional[Dict[str, Any]]:
    """Текущее назначенное занятие БЕЗ создания следующего.

    Важно для хуков завершения: завершение не должно порождать новые
    занятия — иначе один и тот же отвеченный сет мог бы закрывать
    несколько практик подряд (баг 26.10.2026).
    """
    if not _pilot(user_id):
        return None
    ensure_tables()
    lessons = _lessons(user_id)
    assigned = [l for l in lessons if l['status'] == 'assigned']
    return assigned[0] if assigned else None


def is_method_day(user_id: int) -> bool:
    """Сегодняшнее занятие по плану — изучение метода? Пилот-гейт, не бросает.

    ЧИТАЮЩАЯ проверка: не создаёт занятия и не начисляет долги — безопасна
    для вызова из глобального контекст-процессора баннера на любой странице.
    Расписание синхронизируется на /daily_tasks (session_info), поэтому там
    сегодняшний урок уже назначен. В день метода ученика не дёргаем тестом
    по теме (срезом): занятие дня — разбор метода + 3 задачи на /method_week
    (владелец, 26.10.2026). Проверяем урок, датированный сегодня, ЛЮБОГО статуса.
    """
    if not _pilot(user_id):
        return False
    try:
        lessons = _lessons(user_id)
        for l in reversed(lessons):
            if _to_date(l.get('assigned_date')) == date.today():
                return l.get('lesson_type') == 'method'
            return False
        return False
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] is_method_day failed: %r', e)
        return False


def current_lesson(user_id: int) -> Optional[Dict[str, Any]]:
    """Текущее (незавершённое) занятие. Создаёт следующее, если все готовы.

    Тип следующего занятия — по СЛОТУ (счёт созданных уроков), а не по
    завершённым: пропущенные занятия не тормозят план (уходят в долг).

    ОДНО ЗАНЯТИЕ В ДЕНЬ: если сегодняшний урок уже создан (завершён или
    пропущен), новый НЕ создаётся — иначе простой рефреш дашборда порождал
    бы лишний «обязательный» урок, который завтра ушёл бы в долг. Следующий
    урок создаётся только на следующий день (или при полном отсутствии
    истории). Ревью 26.10.2026.
    """
    if not _pilot(user_id):
        return None
    ensure_tables()
    _sync(user_id)  # перед созданием занятия — начислить долги за пропущенные дни
    lessons = _lessons(user_id)
    assigned = [l for l in lessons if l['status'] == 'assigned']
    if assigned:
        return assigned[0]
    # сегодняшний урок уже создан (завершён/пропущен) — нового не создаём
    if lessons and _to_date(lessons[-1].get('assigned_date')) == date.today():
        return None
    # история пуста или последний урок датирован прошлым — создаём следующий по слоту
    seq = (lessons[-1]['seq'] if lessons else 0) + 1
    lesson_type = _lesson_type_for_position(_slot_of(seq) - 1)
    _insert_lesson(user_id, seq, lesson_type)
    lessons = _lessons(user_id)
    assigned = [l for l in lessons if l['status'] == 'assigned']
    return assigned[0] if assigned else None


def complete_current_lesson(user_id: int, lesson_type: Optional[str] = None,
                            completed_set_id: Optional[int] = None) -> bool:
    """Отметить текущее занятие завершённым (идемпотентно).

    lesson_type — опциональная проверка типа (например, 'probnik' при
    сдаче пробника): если тип не совпадает с текущим, ничего не делаем.
    completed_set_id — источник завершения (для практики: id сета дня),
    чтобы один сет не закрывал несколько занятий подряд.
    Возвращает True, если занятие было отмечено сейчас.
    """
    if not _pilot(user_id):
        return False
    ensure_tables()
    # ВАЖНО: берём уже назначенное занятие БЕЗ создания нового —
    # завершение не должно порождать следующие занятия.
    lesson = _current_assigned(user_id)
    if not lesson:
        return False
    if lesson_type and lesson['lesson_type'] != lesson_type:
        return False
    if lesson['status'] != 'assigned':
        return False
    if completed_set_id is not None and lesson['completed_set_id'] == completed_set_id:
        return False  # этот сет уже закрывал данное занятие
    db.session.execute(text(
        f"UPDATE {TABLE_NAME} SET status = 'completed', "
        f"completed_set_id = :sid, completed_at = :now "
        f"WHERE id = :lid AND status = 'assigned'"
    ), {'now': datetime.utcnow(), 'lid': lesson['id'], 'sid': completed_set_id})
    db.session.commit()
    logger.info('[session_plan] completed lesson #%s (%s) user=%s',
                lesson['seq'], lesson['lesson_type'], user_id)
    return True


# ── Хуки завершения (вызываются из мест сдачи) ───────────────────────────

def maybe_complete_practice(user_id: int, daily_set_id: int) -> bool:
    """Практика завершена, если все задачи сегодняшнего сета отвечены.

    Один сет закрывает РОВНО одно занятие-практику: повторные ответы
    по тому же сету (повторы, ретраи) не двигают прогресс дальше.
    """
    try:
        if not _pilot(user_id):
            return False
        _sync(user_id)  # завершение не должно зависеть от захода на дашборд
        from daily_tasks.models import DailyTaskItem, DailyTaskSet
        # сет должен принадлежать этому ученику и быть СЕГОДНЯШНИМ:
        # старый неучтённый сет или чужой сет не закрывают текущую практику
        s = DailyTaskSet.query.get(daily_set_id)
        if not s or s.user_id != user_id:
            return False
        if s.target_date != date.today():
            return False
        items = DailyTaskItem.query.filter_by(daily_set_id=daily_set_id).all()
        if not items:
            return False
        if not all(it.user_answer is not None for it in items):
            return False
        # этот сет уже закрывал ПРАКТИКУ — повторно не считаем
        # (lesson_type в проверке обязателен: id практик и метод-сетов независимы)
        used = db.session.execute(text(
            f"SELECT 1 FROM {TABLE_NAME} "
            f"WHERE user_id = :uid AND lesson_type = 'practice' "
            f"AND completed_set_id = :sid"
        ), {'uid': user_id, 'sid': daily_set_id}).fetchone()
        if used:
            return False
        # после отсутствия назначенного может не быть — создаём сегодняшнее
        if not _current_assigned(user_id):
            _ensure_today_lesson(user_id)
        return complete_current_lesson(user_id, lesson_type='practice',
                                       completed_set_id=daily_set_id)
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] practice hook failed: %r', e)
    return False


def maybe_complete_method(user_id: int) -> bool:
    """Метод завершён, если все задачи метод-сета отвечены.

    Проверяем, что отвечен именно тот метод, который назначен текущим
    занятием (lesson.method_code): метод-сет другой недели не должен
    закрывать назначенное занятие.
    """
    try:
        if not _pilot(user_id):
            return False
        _sync(user_id)  # завершение не должно зависеть от захода на дашборд
        # после отсутствия назначенного может не быть — создаём сегодняшнее
        if not _current_assigned(user_id):
            _ensure_today_lesson(user_id)
        from method_week.models import MethodWeekSet, MethodWeekAnswer
        s = MethodWeekSet.query.filter_by(user_id=user_id).order_by(
            MethodWeekSet.id.desc()).first()
        if not s or not s.tasks_json:
            return False
        lesson = _current_assigned(user_id)
        if not lesson or lesson['lesson_type'] != 'method':
            return False
        set_method = getattr(s, 'method_code', None)
        if lesson['method_code'] and set_method and lesson['method_code'] != set_method:
            # сет ДРУГОЙ недели не закрывает занятие (прошлая неделя и т.п.)
            _ws = date.today() - timedelta(days=date.today().weekday())
            if not s.week_start or s.week_start != _ws:
                return False
            # Неделя пересекла границу месяца после создания сета: кнопка и
            # задачи указывают на метод сета — переуказываем метод занятия
            # на фактический (прогресс и ответы не трогаем), иначе занятие
            # никогда не закроется (владелец, 26.10).
            try:
                db.session.execute(text(
                    f"UPDATE {TABLE_NAME} SET method_code = :mc, "
                    f"method_name = :mn WHERE id = :lid"),
                    {'mc': set_method, 'mn': (getattr(s, 'method_name', None) or ''),
                     'lid': lesson['id']})
                db.session.commit()
                lesson['method_code'] = set_method
            except Exception as e:  # noqa: BLE001
                logger.warning('[session_plan] method re-point failed: %r', e)
                return False
        import json as _json
        tasks = _json.loads(s.tasks_json) if isinstance(s.tasks_json, str) else (s.tasks_json or [])
        if not tasks:
            return False
        answered = {a.position for a in MethodWeekAnswer.query.filter_by(
            set_id=s.id).all() if a.user_answer}
        if all(int(t.get('position') or 0) in answered for t in tasks):
            # этот метод-сет уже закрывал ЗАНЯТИЕ-МЕТОД — повторно не считаем
            # (lesson_type в проверке обязателен: id метод-сетов и практик независимы)
            used = db.session.execute(text(
                f"SELECT 1 FROM {TABLE_NAME} "
                f"WHERE user_id = :uid AND lesson_type = 'method' "
                f"AND completed_set_id = :sid"
            ), {'uid': user_id, 'sid': s.id}).fetchone()
            if used:
                return False
            return complete_current_lesson(user_id, lesson_type='method',
                                           completed_set_id=s.id)
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] method hook failed: %r', e)
    return False


def maybe_complete_probnik(user_id: int, probnik_code: str) -> bool:
    """Пробник сдан — завершаем занятие-пробник."""
    try:
        if not _pilot(user_id):
            return False
        _sync(user_id)  # завершение не должно зависеть от захода на дашборд
        # после отсутствия назначенного может не быть — создаём сегодняшнее
        if not _current_assigned(user_id):
            _ensure_today_lesson(user_id)
        lesson = _current_assigned(user_id)
        if not lesson or lesson['lesson_type'] != 'probnik':
            return False
        if lesson['probnik_code'] and lesson['probnik_code'] != probnik_code:
            return False
        return complete_current_lesson(user_id, lesson_type='probnik')
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] probnik hook failed: %r', e)
    return False


def current_practice_theme(user_id: int) -> Optional[str]:
    """Тема текущего занятия-практики (для привязки сета дня к ротации).

    Возвращает тему, если текущее занятие ротации — практика с темой;
    во всех остальных случаях (метод, пробник, нет занятия) — None,
    чтобы генерация сета работала как раньше (по слабым местам).
    Занятие НЕ создаёт (только читает уже назначенное).
    """
    try:
        lesson = _current_assigned(user_id)
        if lesson and lesson['lesson_type'] == 'practice' and lesson.get('theme'):
            return str(lesson['theme'])
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] practice theme lookup failed: %r', e)
    return None


# ── Публичная сводка (дашборд задач дня + план куратора) ─────────────────

CTA_FOR_TYPE = {
    # Метод — на страницу метода из базы 102 (/olympiads/methods/<код>):
    # статичный разбор + 3 дипсиковые задачи по методу (владелец, 26.10).
    # ВАЖНО: старые ссылки /olympiad/methods (без «s») вели в 404.
    'method': '/olympiads/methods',
    'practice': '/daily_tasks',
    'probnik': '/olympiads/probniks',
}


def session_info(user_id: int) -> Dict[str, Any]:
    """Сводка текущего занятия и плана для интерфейса. Никогда не бросает.

    Сначала — ролловер пропущенных дней (занятия уходят в долг, план
    двигается дальше), затем текущее занятие + план на 6 слотов вперёд
    (текущее + 5 следующих) и список долгов (skipped).
    """
    if not _pilot(user_id):
        return {'active': False}
    try:
        _sync(user_id)
        lesson = current_lesson(user_id)
        lessons = _lessons(user_id)
        today_done = False
        if not lesson:
            # назначенного нет: либо сегодняшний урок уже завершён (молодец,
            # следующий — завтра), либо истории нет вовсе
            if not lessons:
                return {'active': False}
            last = lessons[-1]
            if _to_date(last.get('assigned_date')) != date.today():
                return {'active': False}  # битое состояние — не показываем
            today_done = True
            # «текущий» слот для превью — СЛЕДУЮЩИЙ за завершённым
            next_seq = last['seq'] + 1
            cur_slot = _slot_of(next_seq)
            t = _lesson_type_for_position(cur_slot - 1)
            lesson = {'seq': next_seq, 'lesson_type': t,
                      'theme': None, 'method_name': None,
                      'probnik_title': None, 'method_code': None,
                      'probnik_code': None, 'olympiad_slug': None,
                      'status': 'done_today'}
        completed = _completed_count(user_id)
        if not today_done:
            cur_slot = _slot_of(lesson['seq'])
        t = lesson['lesson_type']
        cta = CTA_FOR_TYPE.get(t, '/daily_tasks')
        if not today_done:
            if t == 'probnik' and lesson['probnik_code']:
                cta = f"/olympiads/probnik/{lesson['probnik_code']}"
            elif t == 'method':
                # если недельный сет уже создан — задачи в нём по его методу
                # (неделя может пересечь границу месяца после создания сета)
                eff = None
                try:
                    from method_week.catalog import week_set_method
                    eff = week_set_method(user_id)
                except Exception:
                    eff = None
                eff = eff or lesson.get('method_code')
                if eff:
                    cta = f"/olympiads/methods/{eff}"
        # ── План: текущее занятие + 5 следующих слотов ──────────────────
        plan = []
        for i in range(BLOCK_SIZE):
            slot = ((cur_slot - 1 + i) % BLOCK_SIZE) + 1
            lt = _lesson_type_for_position(slot - 1)
            entry = {
                'slot': slot,
                'lesson_type': lt,
                'lesson_label': LESSON_LABELS.get(lt, lt),
                'state': ('tomorrow' if today_done else 'current') if i == 0 else 'upcoming',
            }
            if i == 0 and not today_done:
                entry['theme'] = lesson['theme']
                entry['method_name'] = lesson['method_name']
                entry['probnik_title'] = lesson['probnik_title']
            plan.append(entry)
        # ── Долги: пропущенные занятия ────────────────────────────────
        debts = [{
            'seq': l['seq'],
            'lesson_type': l['lesson_type'],
            'lesson_label': LESSON_LABELS.get(l['lesson_type'], l['lesson_type']),
            'theme': l['theme'],
            'method_name': l['method_name'],
            'probnik_title': l['probnik_title'],
            'assigned_date': (l['assigned_date'].isoformat()
                              if hasattr(l['assigned_date'], 'isoformat')
                              else str(l['assigned_date'] or '')),
        } for l in lessons if l['status'] == 'skipped']
        return {
            'active': True,
            'seq': lesson['seq'],
            'lesson_type': t,
            'lesson_label': LESSON_LABELS.get(t, t),
            'position_in_block': cur_slot,
            'block_size': BLOCK_SIZE,
            'completed_lessons': completed,
            'theme': lesson['theme'],
            'method_name': lesson['method_name'],
            'probnik_code': lesson['probnik_code'],
            'probnik_title': lesson['probnik_title'],
            'olympiad_slug': lesson['olympiad_slug'],
            'cta_url': cta,
            'status': lesson['status'],
            'today_done': today_done,
            'plan': plan,
            'debts': debts,
            'debts_count': len(debts),
        }
    except Exception as e:  # noqa: BLE001
        logger.warning('[session_plan] session_info failed: %r', e)
        return {'active': False}
