# -*- coding: utf-8 -*-
"""services/curator_chat.py — ИИ-куратор для пилота Premium.

Чат с куратором-экспертом по олимпиадам (DeepSeek v4-pro).

Модель одна, режимы разные: анализ недели — С рассуждением (thinking),
обычные ответы в чате — БЕЗ рассуждения (быстрее и дешевле).
Контекст куратора узкий и проверенный: анкета ученика, результаты
первой недели, факт бездействия, тариф. Никакой выдуманной информации
о льготах вузов — только данные из контекста.

Отказоустойчивость (требование: «100% сбоев не было»):
  * генерация асинхронная, с таймаутом;
  * при любой ошибке/таймауте — fallback-шаблон (пользователь никогда
    не встречает тишину или ошибку);
  * недельное сообщение инициирует система (ленивый триггер при
    открытии чата после 7 дней подписки), а не пользователь.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models import db, CuratorChatMessage

logger = logging.getLogger('formyla.curator_chat')

# Замок от гонки «планировщик + открытие чата» (один воркер gunicorn —
# внутри процесса замок надёжен; для масштаба пилота достаточно)
_week1_lock = threading.Lock()

# ── Модель и параметры генерации ────────────────────────────────────────────

MODEL = "deepseek-v4-pro"          # env DEEPSEEK_MODEL переопределяет
GENERATION_TIMEOUT_SEC = 90        # куратор «думает» — пользователь не ждёт
FALLBACK_MESSAGE = (
    "Я на связи, но сейчас не могу ответить развёрнуто — техническая заминка.\n"
    "Коротко: главное — не бросай график. Если что-то не получается — напиши "
    "в Поддержку, они отвечают всегда."
)

WEEK1_SYSTEM_MESSAGE_TEMPLATE = (
    "Привет! Я твой куратор на FORMYLA. Посмотрел твою первую неделю.\n"
    "{activity_line}\n"
    "Расскажи, как тебе формат — и если что-то тяжело, скажи честно: "
    "подстроим график под тебя. Я рядом на протяжении всей подготовки."
)

WEEK1_ACTIVITY_OK = (
    "Видно, что ты занималсяся — {solved} попыток решения за неделю. Так держать: "
    "регулярность важнее рывков."
)
WEEK1_ACTIVITY_LOW = (
    "Занятий пока почти не видно — {solved} попыток решения за неделю. Бывает: старт "
    "всегда самый сложный. Давай без давления: попробуем завтра один блок "
    "задач дня — 20–30 минут. Пойдёт?"
)
WEEK1_ACTIVITY_ZERO = (
    "Решённых задач за неделю пока не видно. Это нормально перед стартом. "
    "Предлагаю просто: завтра один заход, 5 задач дня. Начнём с этого?"
)

# ── Системный промпт куратора ───────────────────────────────────────────────

SYSTEM_PROMPT = """Ты — куратор платформы FORMYLA, эксперт по российским школьным олимпиадам по математике (ВсОШ, Перечневые, Физтех, Ломоносов и др.).

Твой ученик — школьник, готовящийся к олимпиадам. Ты ведёшь его к цели.

Правила:
- Отвечай по-русски, тепло и по-деловому, как наставник. Без канцелярита.
- КОРОТКО: не больше 120 слов в ответе, если ученик не просит подробный разбор.
- Ты знаешь о ученике только то, что в блоке «Данные ученика». Не выдумывай факты.
- Про льготы в вузы, сроки и правила конкретных олимпиад — если их нет в данных, честно скажи, что нужно уточнить, и предложи проверить на официальном сайте олимпиады. Никаких выдуманных цифр и обещаний.
- ЕСЛИ УЧЕНИК ЕЩЁ НЕ ВЫБРАЛ олимпиады или темы — НЕ спрашивай «с чего хочешь начать» и не предлагай выбирать из пустоты: сам назови 2–3 конкретные темы или олимпиады под его класс и уровень, обоснуй, почему именно они. Решение предложи, а выбор не предлагай.
- Всегда давай план на день: что именно сделать сегодня и сколько времени это займёт.
- Если данных о занятиях нет — признаёшь это мягко («по решениям пока не видно, что ты занимался»), НЕ обвиняй и не стыди.
- Не обещай лёгких побед. Мотивируй через цель и план, а не через «всё легко».
- Если ученик пишет о проблеме с сайтом — попроси обратиться в Поддержку (отвечает всегда).
- В конце — конкретный следующий шаг на сегодня, а не вопрос в пустоту."""


# ── История ─────────────────────────────────────────────────────────────────

def get_history(user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
    """Последние сообщения чата (хронологически)."""
    rows = (CuratorChatMessage.query
            .filter_by(user_id=user_id)
            .order_by(CuratorChatMessage.created_at.desc(), CuratorChatMessage.id.desc())
            .limit(limit).all())
    out = []
    for r in reversed(rows):
        out.append({
            'id': r.id,
            'role': r.role,
            'content': r.content,
            'created_at': r.created_at.isoformat() if r.created_at else None,
        })
    return out


def add_message(user_id: int, role: str, content: str,
                meta: Optional[Dict[str, Any]] = None) -> CuratorChatMessage:
    msg = CuratorChatMessage(
        user_id=user_id,
        role=role,
        content=content,
        meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
    )
    db.session.add(msg)
    return msg


# ── Контекст ученика (узкий, проверенный) ────────────────────────────────────

def _safe_q(query_fn) -> Any:
    try:
        return query_fn()
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] query failed: %s', e)
        return None


def _earliest_subscription_started(user_id: int) -> Optional[datetime]:
    """Старт ПЕРВОЙ пилотной подписки — начало обучения.

    Берём MIN(started_at) только по пилотным тарифам (premium_intense /
    premium_calm): старые исторические подписки (напр., протухший monthly
    за 390 ₽) не должны запустить недельный отчёт раньше времени.
    Смена пилотного тарифа дату не сбрасывает.
    """
    try:
        row = db.session.execute(
            __import__('sqlalchemy').text(
                "SELECT MIN(started_at) FROM subscriptions WHERE user_id = :u "
                "AND plan IN ('premium_intense', 'premium_calm')"),
            {'u': user_id},
        ).first()
        if row and row[0]:
            v = row[0]
            if isinstance(v, datetime):
                return v
            try:
                return datetime.fromisoformat(str(v))
            except (ValueError, TypeError):
                return None
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] earliest sub lookup failed: %s', e)
    return None


def build_context(user_id: int, since: Optional[datetime] = None,
                 until: Optional[datetime] = None) -> Dict[str, Any]:
    """Собрать контекст куратора: анкета + неделя + тариф.

    Разделяем «нет данных» и «нулевая активность»: если запрос упал —
    куратор НЕ делает выводов о занятости ученика (data_ok=False).
    Всё в try/except: чат должен работать даже если какая-то часть
    данных недоступна.
    """
    ctx: Dict[str, Any] = {'user_id': user_id}
    now = datetime.utcnow()
    started_sub = _earliest_subscription_started(user_id)
    if since is None:
        since = now - timedelta(days=7)  # по умолчанию — последние 7 дней
    if until is None or until > now:
        until = now
    if started_sub:
        week_n = int((now - started_sub).total_seconds() // (7 * 86400)) + 1
        ctx['week_number'] = week_n
    ctx['window_label'] = f"{since:%d.%m}–{until:%d.%m}"

    # Тариф
    try:
        from services.subscription import get_subscription_service
        plan = get_subscription_service().get_user_plan(user_id)
        ctx['plan'] = plan.get('plan')
        ctx['plan_display'] = {
            'premium_intense': '«Работяга» (6 занятий/нед)',
            'premium_calm': '«Спокойный» (3 занятия/нед)',
            'premium_monthly': 'Premium',
        }.get(ctx['plan'], ctx['plan'])
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] plan failed: %s', e)

    # Анкета и класс (CuratorState): олимпиады — из target_olympiads,
    # класс — из intake.class_level (подтверждён в анкете)
    grade = None
    intake = None
    olympiads = None
    try:
        from models_curator import CuratorState
        from services.intake_service import _prep_state_dict
        cs = CuratorState.query.filter_by(user_id=user_id).first()
        if cs is not None:
            grade = getattr(cs, 'grade', None)
            ps = _prep_state_dict(cs) or {}
            intake = ps.get('intake') or None
            if not grade and isinstance(intake, dict) and intake.get('class_level'):
                grade = intake.get('class_level')
            to = getattr(cs, 'target_olympiads', None)
            if isinstance(to, str):
                try:
                    to = json.loads(to)
                except Exception:
                    to = None
            if isinstance(to, (list, tuple)) and to:
                olympiads = ', '.join(str(o) for o in to)
            elif isinstance(to, str) and to.strip():
                olympiads = to.strip()
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] curator_state failed: %s', e)
    ctx['grade'] = grade
    ctx['intake'] = intake
    ctx['olympiads'] = olympiads

    # Задачи за окно статистики (по умолчанию последние 7 дней от сейчас;
    # недельная оценка передаёт окно своей недели явно).
    # Попытки и верные ответы раздельно; data_ok=False если запрос упал.
    attempted = correct = 0
    data_ok = True
    try:
        from models import BankIssue
        attempted += BankIssue.query.filter(
            BankIssue.user_id == user_id,
            BankIssue.answered_at >= since,
            BankIssue.answered_at < until,
        ).count()
        correct += BankIssue.query.filter(
            BankIssue.user_id == user_id,
            BankIssue.answered_at >= since,
            BankIssue.answered_at < until,
            BankIssue.is_correct.is_(True),
        ).count()
    except Exception as e:  # noqa: BLE001
        data_ok = False
        logger.warning('[curator_chat] bank stats failed: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
    try:
        from daily_tasks.models import DailyTaskItem, DailyTaskSet
        attempted += (DailyTaskItem.query
                      .join(DailyTaskSet, DailyTaskItem.daily_set_id == DailyTaskSet.id)
                      .filter(DailyTaskSet.user_id == user_id,
                              DailyTaskItem.answered_at >= since,
                              DailyTaskItem.answered_at < until)
                      .count())
        correct += (DailyTaskItem.query
                    .join(DailyTaskSet, DailyTaskItem.daily_set_id == DailyTaskSet.id)
                    .filter(DailyTaskSet.user_id == user_id,
                            DailyTaskItem.answered_at >= since,
                            DailyTaskItem.answered_at < until,
                            DailyTaskItem.is_correct.is_(True))
                    .count())
    except Exception as e:  # noqa: BLE001
        data_ok = False
        logger.warning('[curator_chat] daily stats failed: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
    ctx['attempted_7d'] = attempted
    ctx['correct_7d'] = correct
    ctx['tasks_data_ok'] = data_ok

    # Прогресс ротации занятий 1-из-6 (для пилотов; остальным не активна)
    try:
        from curator.session_plan import session_info
        s = session_info(user_id)
        if s.get('active'):
            ctx['rotation'] = {
                'completed': s.get('completed_lessons', 0),
                'position': s.get('position_in_block'),
                'current_type': s.get('lesson_label'),
                'theme': s.get('theme'),
                'method_name': s.get('method_name'),
                'probnik_title': s.get('probnik_title'),
            }
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] rotation ctx failed: %r', e)

    # Заходы за первую неделю (логины — прокси; отдельный флаг доступности)
    visits = 0
    visits_ok = True
    try:
        from sqlalchemy import text
        row = db.session.execute(text(
            'SELECT COUNT(*) FROM site_events '
            'WHERE user_id = :u AND kind = :k AND ts >= :since AND ts < :until'),
            {'u': user_id, 'k': 'login', 'since': since, 'until': until},
        ).first()
        visits = int(row[0]) if row else 0
    except Exception as e:  # noqa: BLE001
        visits_ok = False
        logger.warning('[curator_chat] visits failed: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
    ctx['logins_7d'] = visits
    ctx['visits_data_ok'] = visits_ok
    ctx['inactive'] = bool(visits_ok and visits <= 2)

    return ctx


def _context_block(ctx: Dict[str, Any]) -> str:
    """Собрать текстовый блок «Данные ученика» для промпта."""
    lines = ['Данные ученика:']
    if ctx.get('grade'):
        lines.append(f"- класс: {ctx['grade']}")
    if ctx.get('plan_display'):
        lines.append(f"- тариф: {ctx['plan_display']}")
    if ctx.get('olympiads'):
        lines.append(f"- целевые олимпиады: {ctx['olympiads']}")
    elif isinstance(ctx.get('intake'), dict):
        # запасной вариант — старое место хранения
        olympiads = ctx['intake'].get('olympiads') or ctx['intake'].get('target_olympiads')
        if olympiads:
            if isinstance(olympiads, (list, tuple)):
                olympiads = ', '.join(str(o) for o in olympiads)
            lines.append(f"- целевые олимпиады (из анкеты): {olympiads}")
    if ctx.get('tasks_data_ok'):
        lines.append(
            f"- за период {ctx.get('window_label', '—')}: "
            f"попыток задач {ctx.get('attempted_7d', 0)}, "
            f"верных ответов {ctx.get('correct_7d', 0)} (попытка ≠ верно)")
    else:
        lines.append("- данных о решённых задачах за неделю НЕТ — не делай выводов о занятости ученика")
    if ctx.get('visits_data_ok'):
        lines.append(f"- заходов на сайт за период: {ctx.get('logins_7d', 0)}")
    else:
        lines.append("- данных о заходах нет")
    rot = ctx.get('rotation')
    if rot:
        lines.append(
            f"- ротация занятий: завершено {rot.get('completed', 0)}; "
            f"сейчас занятие {rot.get('position')} из 6 — {rot.get('current_type')}")
        if rot.get('theme'):
            lines.append(f"- тема текущей практики: {rot['theme']}")
        if rot.get('method_name'):
            lines.append(f"- текущий метод: {rot['method_name']}")
        if rot.get('probnik_title'):
            lines.append(f"- назначенный пробник: {rot['probnik_title']}")
    if ctx.get('week_number'):
        lines.append(f"- сейчас идёт неделя {ctx['week_number']} подписки")
    if ctx.get('inactive'):
        lines.append("- ВАЖНО: ученик был малоактивен (заходил 1–2 раза) — не обвиняй, мягко предложи маленький первый шаг.")
    return '\n'.join(lines)


# ── Генерация ответа (DeepSeek, асинхронно, с fallback) ──────────────────────

def _call_deepseek(messages: List[Dict[str, str]], thinking: bool = False,
                   max_tokens: int = 1200) -> str:
    """Синхронная обёртка: async-вызов с таймаутом. Бросает при ошибке.

    thinking=True — режим с рассуждением (анализ недели; берём больше
    max_tokens, чтобы рассуждение не съело весь ответ),
    thinking=False — явно БЕЗ рассуждения (быстрые ответы в чате).
    Модель форсируем на v4-pro независимо от DEEPSEEK_MODEL
    (как method_week) — прод-логи подтверждают v4-pro и так.
    """
    from daily_tasks.pipeline.deepseek_client import DeepSeekClient

    async def _run() -> str:
        async with DeepSeekClient() as client:
            client._model = MODEL
            text, _usage = await client.chat(
                MODEL,
                messages,
                temperature=0.5,
                max_tokens=max_tokens,
                thinking=thinking,
            )
            return text

    return asyncio.run(asyncio.wait_for(_run(), timeout=GENERATION_TIMEOUT_SEC))


def generate_reply(user_id: int, user_text: str,
                   ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Ответ куратора на сообщение ученика. Никогда не бросает.

    Возвращает {'content': str, 'fallback': bool}.
    """
    ctx = ctx or build_context(user_id)
    try:
        history = get_history(user_id, limit=12)
    except Exception as e:  # noqa: BLE001
        # чат должен работать даже если история недоступна — продолжаем без неё
        logger.warning('[curator_chat] history unavailable: %s', e)
        history = []
    messages: List[Dict[str, str]] = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    messages.append({'role': 'system', 'content': _context_block(ctx)})
    for m in history:
        if m['role'] == 'user':
            messages.append({'role': 'user', 'content': m['content']})
        elif m['role'] == 'curator':
            messages.append({'role': 'assistant', 'content': m['content']})
    messages.append({'role': 'user', 'content': user_text})

    try:
        text = _call_deepseek(messages)
        text = (text or '').strip()
        if text:
            return {'content': text, 'fallback': False}
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] generation failed: %s', e)
    return {'content': FALLBACK_MESSAGE, 'fallback': True}


# ── Приветствие на старте (сразу, не через неделю) ─────────────────────────

WELCOME_PROMPT_INSTRUCTION = (
    "Напиши ученику ПЕРВОЕ приветственное сообщение от куратора. Представься "
    "в одной фразе (куратор FORMYLA, веду тебя к олимпиадам). Поздоровься тепло. "
    "Если в данных есть план на сегодня — сразу дай его (что сделать, сколько "
    "времени займёт). Если ученик ещё не выбрал олимпиады — предложи сам 2–3 "
    "конкретных варианта под его класс, не спрашивай «что ты хочешь». "
    "Заканчивай конкретным шагом на сегодня. До 100 слов."
)

WELCOME_FALLBACK = (
    "Привет! Я твой куратор на FORMYLA — веду тебя к олимпиадам и баллам.\n"
    "\n"
    "План на сегодня простой: зайди в «Задачи дня» и реши один блок — "
    "это 15–30 минут. Этого достаточно для первого шага.\n"
    "\n"
    "Если что-то не получается или нужны советы по выбору олимпиад — "
    "просто напиши мне здесь. Поехали!"
)


def daily_plan_block(user_id: int) -> str:
    """План на день для контекста куратора (из пилотного расписания).

    SESSION_PLAN_V1 (26.10.2026): приоритет — ротация занятий 1-из-6
    (метод → 4 практики → пробник, прогресс по завершённым занятиям).
    Если она неактивна — старый календарный план pilot_session_today.
    """
    try:
        from curator.session_plan import session_info
        s = session_info(user_id)
        if s.get('active'):
            if s['lesson_type'] == 'method':
                plan = ('изучение метода'
                        + (f" «{s['method_name']}»" if s.get('method_name') else '')
                        + ': 70% разбор метода + 3 задачи на закрепление (~45 мин)')
            elif s['lesson_type'] == 'probnik':
                plan = ('пробник — реальный вариант прошлых лет по регламенту'
                        + (f" ({s['probnik_title']})" if s.get('probnik_title') else ''))
            else:
                plan = 'задачи дня по теме, назначенной куратором'
            return (f"- план на сегодня (занятие {s['position_in_block']} из "
                    f"{s['block_size']}): {plan}")
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] session plan failed: %s', e)
    try:
        from services.pilot import pilot_session_today
        s = pilot_session_today(user_id)
        if not s.get('enabled'):
            return ''
        plan_map = {
            'diagnostic': 'тест (5 задач, ~15 мин) + задачи дня по уровню',
            'tasks': 'блок задач дня (5 задач, ~30 мин)',
            'method': 'изучение метода: 70% разбор метода + 3 задачи на закрепление (~45 мин)',
            'mock': 'пробник — реальный вариант прошлых лет по регламенту олимпиады',
            'rest': 'выходной — отдых, можно по желанию повторить одну тему',
        }
        plan = plan_map.get(s.get('session_type'))
        if not plan:
            return ''
        return f"- план на сегодня (неделя {s.get('week')}): {plan}"
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] daily plan failed: %s', e)
        return ''


def send_welcome_message(user_id: int) -> bool:
    """Приветствие куратора при первом открытии чата (сразу на старте).

    Отправляется один раз: если в чате ещё нет ни одного сообщения от
    куратора/системы. Генерируется DeepSeek (приветствие + план на день),
    при сбое — шаблон. Никогда не бросает.
    """
    try:
        existing = (CuratorChatMessage.query
                    .filter(CuratorChatMessage.user_id == user_id,
                            CuratorChatMessage.role.in_(['curator', 'system']))
                    .count())
        if existing:
            return False  # куратор уже писал — не дублируем

        ctx = build_context(user_id)
        plan_line = daily_plan_block(user_id)

        text = None
        try:
            sys_block = _context_block(ctx)
            if plan_line:
                sys_block += '\n' + plan_line
            messages: List[Dict[str, str]] = [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'system', 'content': sys_block},
                {'role': 'user', 'content': WELCOME_PROMPT_INSTRUCTION},
            ]
            text = _call_deepseek(messages).strip()
        except Exception as e:  # noqa: BLE001
            logger.warning('[curator_chat] welcome generation failed: %s', e)

        if not text:
            text = WELCOME_FALLBACK

        add_message(user_id, 'system', text, meta={'kind': 'welcome'})
        db.session.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] welcome failed: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return False


# ── Недельное сообщение (системный триггер) ────────────────────────────────

def _subscription_started_at(user_id: int) -> Optional[datetime]:
    """Дата начала активной подписки (для отсчёта недели)."""
    try:
        row = db.session.execute(
            __import__('sqlalchemy').text(
                'SELECT started_at FROM subscriptions '
                'WHERE user_id = :u AND status = :s ORDER BY id DESC LIMIT 1'),
            {'u': user_id, 's': 'active'},
        ).first()
        if row and row[0]:
            v = row[0]
            if isinstance(v, datetime):
                return v
            try:
                return datetime.fromisoformat(str(v))
            except (ValueError, TypeError):
                return None
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] sub lookup failed: %s', e)
    return None


def _has_weekly_message(user_id: int, week_n: int) -> bool:
    """Уже отправлена оценка недели week_n? (kind='weekly' или старый week1)."""
    rows = CuratorChatMessage.query.filter_by(
        user_id=user_id, role='system').all()
    for r in rows:
        try:
            meta = json.loads(r.meta_json or '{}')
        except Exception:  # noqa: BLE001
            meta = {}
        kind = (meta or {}).get('kind')
        if kind == 'weekly' and int((meta or {}).get('week', 0) or 0) == week_n:
            return True
        if kind == 'week1' and week_n == 1:
            return True
    return False


WEEKLY_PROMPT_INSTRUCTION = (
    "Напиши ученику сообщение куратора — оценку недели обучения. "
    "Используй ТОЛЬКО данные из блока «Данные ученика». Структура: "
    "(1) короткая оценка — что на этой неделе получилось хорошо "
    "(конкретно: сколько решено верно, прогресс ротации занятий), "
    "(2) что просело или отстаёт — мягко, без обвинений, "
    "(3) конкретный следующий шаг на завтра (одно действие). "
    "Если активности мало или её нет — предложи маленький первый шаг "
    "(например, завтра один блок задач дня, 20–30 минут). "
    "Если данных нет — напиши, что статистика пока не видна. "
    "В конце — короткий вопрос. До 100 слов. На «ты», живо, без списков "
    "и заголовков — как сообщение в чате."
)


def send_week1_message(user_id: int) -> bool:
    """Совместимость: оценка первой недели = недельная оценка (week=1)."""
    return send_weekly_message(user_id)


def send_weekly_message(user_id: int) -> bool:
    """Системная недельная оценка куратора (пишет первым, без вопроса ученика).

    Одна оценка на каждую неделю подписки (неделя 1, 2, 3, ...); окно
    статистики — именно та неделя. Вызывается фоновым планировщиком
    (раз в час) и лениво при открытии чата. Генерируется DeepSeek по
    контексту недели; при любом сбое — шаблонное сообщение (пользователь
    никогда не встречает тишину). Идемпотентно: замок защищает от гонки
    «планировщик + открытие чата». Никогда не бросает.

    ТОЛЬКО для пилотов-админов (victor + lavrik) — по требованию владельца:
    обычным пользователям недельные оценки не отправляются (до запуска).
    """
    try:
        from services.pilot import is_pilot_id
        if not is_pilot_id(user_id):
            return False
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] pilot check failed: %s', e)
        return False

    with _week1_lock:
        return _send_weekly_message_locked(user_id)


def _send_weekly_message_locked(user_id: int) -> bool:
    try:
        started = _earliest_subscription_started(user_id)
        if started is None:
            return False
        now = datetime.utcnow()
        # оцениваем ПОСЛЕДНЮЮ ЗАВЕРШЁННУЮ неделю: возраст 7-13 дней = неделя 1
        week_n = int((now - started).total_seconds() // (7 * 86400))
        if week_n < 1:
            return False  # первая неделя ещё идёт — оценивать нечего
        if _has_weekly_message(user_id, week_n):
            return False

        # окно оцениваемой (завершённой) недели подписки
        since = started + timedelta(days=7 * (week_n - 1))
        until = min(started + timedelta(days=7 * week_n), now)
        ctx = build_context(user_id, since=since, until=until)

        text = None
        try:
            messages: List[Dict[str, str]] = [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'system', 'content': _context_block(ctx)},
                {'role': 'user', 'content': WEEKLY_PROMPT_INSTRUCTION},
            ]
            text = _call_deepseek(messages, thinking=True, max_tokens=3000).strip()
        except Exception as e:  # noqa: BLE001
            logger.warning('[curator_chat] weekly generation failed: %s', e)

        if not text:
            # Шаблонный фолбэк по уровню активности
            if not ctx.get('tasks_data_ok'):
                activity = ("Статистика занятий пока не видна с моей стороны — "
                            "начнём с простого: завтра один блок задач дня.")
            else:
                attempted = ctx.get('attempted_7d', 0)
                if attempted >= 5:
                    activity = WEEK1_ACTIVITY_OK.format(solved=attempted)
                elif attempted >= 1:
                    activity = WEEK1_ACTIVITY_LOW.format(solved=attempted)
                else:
                    activity = WEEK1_ACTIVITY_ZERO.format(solved=0)
            text = WEEK1_SYSTEM_MESSAGE_TEMPLATE.format(activity_line=activity)

        add_message(user_id, 'system', text,
                    meta={'kind': 'weekly', 'week': week_n})
        db.session.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] weekly trigger failed: %s', e)
        try:
            db.session.rollback()
        except Exception:
            pass
        return False


def maybe_send_week1_message(user_id: int) -> bool:
    """Ленивый триггер при открытии чата (дублирует фоновый запуск)."""
    return send_week1_message(user_id)


def sweep_pilot_week1() -> int:
    """Фоновый обход пилотных аккаунтов (вызывается планировщиком раз в час).

    Отправляет: приветствие (если куратор ещё не писал) и недельную
    оценку (по одной на каждую неделю пилотной подписки). Возвращает
    число отправленных сообщений. Никогда не бросает.
    """
    sent = 0
    try:
        from services.pilot import PILOT_USER_IDS
        for user_id in PILOT_USER_IDS:
            try:
                if send_welcome_message(user_id):
                    sent += 1
                if send_weekly_message(user_id):
                    sent += 1
            except Exception as e:  # noqa: BLE001
                logger.warning('[curator_chat] sweep user %s failed: %s', user_id, e)
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] sweep failed: %s', e)
    return sent
