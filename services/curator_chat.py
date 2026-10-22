# -*- coding: utf-8 -*-
"""services/curator_chat.py — ИИ-куратор для пилота Premium.

Чат с куратором-экспертом по олимпиадам (DeepSeek v4-pro reasoning).
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
            return row[0] if isinstance(row[0], datetime) else None
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] earliest sub lookup failed: %s', e)
    return None


def build_context(user_id: int) -> Dict[str, Any]:
    """Собрать контекст куратора: анкета + неделя + тариф.

    Разделяем «нет данных» и «нулевая активность»: если запрос упал —
    куратор НЕ делает выводов о занятости ученика (data_ok=False).
    Всё в try/except: чат должен работать даже если какая-то часть
    данных недоступна.
    """
    ctx: Dict[str, Any] = {'user_id': user_id}

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

    # Задачи за первые 7 дней ОБУЧЕНИЯ (не «последние 7 дней от сейчас»):
    # считаем от старта первой подписки, чтобы видеть именно первую неделю.
    # Попытки и верные ответы раздельно; data_ok=False если запрос упал.
    started_sub = _earliest_subscription_started(user_id)
    since = (started_sub or datetime.utcnow() - timedelta(days=7))
    until = since + timedelta(days=7)
    now = datetime.utcnow()
    if now < until:
        until = now  # первая неделя ещё идёт — берём что есть
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
            f"- за последние 7 дней: попыток задач {ctx.get('attempted_7d', 0)}, "
            f"верных ответов {ctx.get('correct_7d', 0)} (попытка ≠ верно)")
    else:
        lines.append("- данных о решённых задачах за неделю НЕТ — не делай выводов о занятости ученика")
    if ctx.get('visits_data_ok'):
        lines.append(f"- заходов на сайт за 7 дней: {ctx.get('logins_7d', 0)}")
    else:
        lines.append("- данных о заходах нет")
    if ctx.get('inactive'):
        lines.append("- ВАЖНО: ученик был малоактивен (заходил 1–2 раза) — не обвиняй, мягко предложи маленький первый шаг.")
    return '\n'.join(lines)


# ── Генерация ответа (DeepSeek, асинхронно, с fallback) ──────────────────────

def _call_deepseek(messages: List[Dict[str, str]]) -> str:
    """Синхронная обёртка: async-вызов с таймаутом. Бросает при ошибке."""
    from daily_tasks.pipeline.deepseek_client import DeepSeekClient

    async def _run() -> str:
        async with DeepSeekClient() as client:
            text, _usage = await client.chat(
                MODEL,
                messages,
                temperature=0.5,
                max_tokens=1200,
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
    """План на день для контекста куратора (из пилотного расписания)."""
    try:
        from services.pilot import pilot_session_today
        s = pilot_session_today(user_id)
        if not s.get('enabled'):
            return ''
        plan_map = {
            'diagnostic': 'диагностический тест-срез (5 задач, ~15 мин) + задачи дня по уровню',
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
            return row[0] if isinstance(row[0], datetime) else None
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] sub lookup failed: %s', e)
    return None


def _has_week1_message(user_id: int) -> bool:
    return CuratorChatMessage.query.filter_by(
        user_id=user_id, role='system',
    ).count() > 0


WEEK1_PROMPT_INSTRUCTION = (
    "Напиши ученику первое сообщение от куратора по итогам его первой недели "
    "подписки. Используй ТОЛЬКО данные из блока «Данные ученика». Если активности "
    "мало или её нет — мягко, без обвинений предложи маленький первый шаг "
    "(например, завтра один блок задач дня, 20–30 минут). Если данных нет — "
    "напиши, что статистика пока не видна, и предложи просто начать. "
    "В конце — короткий вопрос или конкретный следующий шаг. До 90 слов."
)


def send_week1_message(user_id: int) -> bool:
    """Системное недельное сообщение куратора (пишет первым, без вопроса ученика).

    Вызывается фоновым планировщиком (раз в час) и лениво при открытии чата.
    Генерируется DeepSeek по контексту недели; при любом сбое — шаблонное
    сообщение (пользователь никогда не встречает тишину). Идемпотентно:
    одно системное сообщение на пользователя (замок защищает от гонки
    «планировщик + открытие чата»). Никогда не бросает.
    """
    with _week1_lock:
        return _send_week1_message_locked(user_id)


def _send_week1_message_locked(user_id: int) -> bool:
    try:
        if _has_week1_message(user_id):
            return False
        started = _earliest_subscription_started(user_id)
        if started is None:
            return False
        if datetime.utcnow() - started < timedelta(days=7):
            return False  # первая неделя обучения ещё не прошла

        ctx = build_context(user_id)

        text = None
        try:
            messages: List[Dict[str, str]] = [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'system', 'content': _context_block(ctx)},
                {'role': 'user', 'content': WEEK1_PROMPT_INSTRUCTION},
            ]
            text = _call_deepseek(messages).strip()
        except Exception as e:  # noqa: BLE001
            logger.warning('[curator_chat] week1 generation failed: %s', e)

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

        add_message(user_id, 'system', text, meta={'kind': 'week1'})
        db.session.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] week1 trigger failed: %s', e)
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

    Отправляет: приветствие (если куратор ещё не писал) и недельный отчёт
    (через 7 дней после старта пилотной подписки). Возвращает число
    отправленных сообщений. Никогда не бросает.
    """
    sent = 0
    try:
        from services.pilot import PILOT_USER_IDS
        for user_id in PILOT_USER_IDS:
            try:
                if send_welcome_message(user_id):
                    sent += 1
                if send_week1_message(user_id):
                    sent += 1
            except Exception as e:  # noqa: BLE001
                logger.warning('[curator_chat] sweep user %s failed: %s', user_id, e)
    except Exception as e:  # noqa: BLE001
        logger.warning('[curator_chat] sweep failed: %s', e)
    return sent
