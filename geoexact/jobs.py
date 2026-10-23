"""Persistent, globally bounded queue. No Flask app imports in worker threads."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import (
    Column, Float, Integer, MetaData, String, Table, Text, create_engine,
    delete, func, insert, select, update,
)

metadata = MetaData()
jobs = Table(
    "geoexact_jobs_v1", metadata,
    Column("id", String(32), primary_key=True),
    Column("owner", String(128), nullable=False, index=True),
    Column("status", String(16), nullable=False, index=True),
    Column("created", Float, nullable=False, index=True),
    Column("started", Float),
    Column("problem", Text, nullable=False),
    Column("with_aux", Integer, nullable=False),
    Column("payload", Text),
)
mutex = Table(
    "geoexact_mutex_v1", metadata,
    Column("id", Integer, primary_key=True),
    Column("revision", Integer, nullable=False),
)

# ── Тайминги живучести очереди ──────────────────────────────────────────────
# Воркер-процесс живёт не дольше WORKER_TIMEOUT_SEC (subprocess.run), а его
# собственный будильник — GEOEXACT_TIME_LIMIT + 25 (см. worker.py). Задание,
# которое числится running дольше RUNNING_STALE_SEC, точно никем не выполняется:
# либо процесс сервера перезапустился (деплой, рестарт Render), либо воркер
# убит. Раньше порог был 400 с — пользователь смотрел на «Строим и проверяем
# чертёж…» почти 7 минут после деплоя.
WORKER_TIMEOUT_SEC = 215
RUNNING_STALE_SEC = float(os.environ.get("GEOEXACT_RUNNING_STALE_SEC", "0") or 0) or (WORKER_TIMEOUT_SEC + 30)
QUEUED_STALE_SEC = float(os.environ.get("GEOEXACT_QUEUED_STALE_SEC", "0") or 0) or 1800.0
# Осиротевшее задание (сервер перезапустился во время генерации) один раз
# возвращается в очередь, а не падает с INTERRUPTED: пользователь ничего не
# нажимал, чертёж он не получил, повтор — одна оплата вместо нуля результатов.
# Второй подряд обрыв уже честно завершается ошибкой (нет бесконечных повторов
# платного API). GEOEXACT_ORPHAN_REQUEUE=0 возвращает прежнее поведение.
ORPHAN_REQUEUE = (os.environ.get("GEOEXACT_ORPHAN_REQUEUE") or "1").strip().lower() not in ("0", "no", "off")
_REQUEUED_MARK = json.dumps({"requeued": 1})


class QueueFull(Exception):
    pass


def make_engine(url):
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    kwargs = {"pool_pre_ping": True}
    if url.startswith("postgresql"):
        # Все приёмы и захваты идут через строковую блокировку geoexact_mutex_v1.
        # Без lock_timeout зависшее соединение убитого процесса держало бы строку,
        # и поток очереди вис бы на UPDATE навсегда — «бесконечная генерация» у всех.
        # С таймаутом ожидание падает исключением, _loop повторяет через 3 с.
        kwargs["connect_args"] = {
            "options": "-c lock_timeout=5000 -c statement_timeout=60000",
        }
    return create_engine(url, **kwargs)


def init_db(engine):
    """Explicit additive migration; never touch existing FORMYLA tables."""
    metadata.create_all(engine)
    from sqlalchemy.exc import IntegrityError
    try:
        with engine.begin() as c:
            if c.execute(select(mutex.c.id)).first() is None:
                c.execute(insert(mutex).values(id=1, revision=0))
    except IntegrityError:
        pass  # Concurrent first install, singleton already created.


def _lock(c):
    # UPDATE takes a transactional row lock on PostgreSQL. Also works in SQLite
    # integration tests. All admissions and claims use this same singleton.
    r = c.execute(update(mutex).where(mutex.c.id == 1).values(
        revision=mutex.c.revision + 1))
    if r.rowcount != 1:
        raise RuntimeError("Run python -m geoexact.manage init-db first")


_HISTORY_MARK = "\x1eGXH1\x1e"
_SOLUTION_MARK = "\x1eGXS1\x1e"    # задача «полное решение»: другой исполнитель


def wrap_problem(problem, history):
    """Job text with the expert chat attached (the jobs table has no spare column)."""
    if not history:
        return problem
    return _HISTORY_MARK + json.dumps({"p": problem, "h": history}, ensure_ascii=False)


def wrap_solution(problem, history):
    """Job text of a «full solution» request (same column, different marker)."""
    return _SOLUTION_MARK + json.dumps({"p": problem, "h": history or []},
                                       ensure_ascii=False)


def unwrap_solution(stored):
    if isinstance(stored, str) and stored.startswith(_SOLUTION_MARK):
        try:
            d = json.loads(stored[len(_SOLUTION_MARK):])
            return d["p"], (d.get("h") or None)
        except (ValueError, KeyError, TypeError):
            return stored[len(_SOLUTION_MARK):], None
    return stored, None


def is_solution_job(stored) -> bool:
    return isinstance(stored, str) and stored.startswith(_SOLUTION_MARK)


def unwrap_problem(stored):
    if isinstance(stored, str) and stored.startswith(_HISTORY_MARK):
        try:
            d = json.loads(stored[len(_HISTORY_MARK):])
            return d["p"], d["h"]
        except (ValueError, KeyError, TypeError):
            return stored[len(_HISTORY_MARK):], None
    return stored, None


def clean_history(history):
    """Only well-formed chat turns of bounded size; anything else is dropped."""
    if not isinstance(history, list) or not 1 <= len(history) <= 40:
        return None
    out, total = [], 0
    for i, m in enumerate(history):
        if not (isinstance(m, dict) and m.get("role") == ("user" if i % 2 == 0 else "assistant")
                and isinstance(m.get("content"), str)):
            return None
        total += len(m["content"])
        out.append({"role": m["role"], "content": m["content"]})
    if total > 60000 or out[-1]["role"] != "assistant":
        return None
    return out


def failure(code, message):
    return {"ok": False, "reason": code, "detail": message}


_INTERRUPTED = failure(
    "INTERRUPTED",
    "Генерация прервана или истекло время ожидания. "
    "Автоматического платного повторения не было.")
_INTERRUPTED_TWICE = failure(
    "INTERRUPTED",
    "Сервер перезапускался во время генерации дважды подряд; задание уже "
    "повторялось автоматически один раз. Запустите построение ещё раз.")


def _was_requeued(payload) -> bool:
    if not payload:
        return False
    try:
        return bool(json.loads(payload).get("requeued"))
    except (ValueError, AttributeError):
        return False


# Результаты, которые не стоит показывать, если есть проверенный чертёж той же
# задачи: эскиз по ключевым словам и сбои без чертежа вовсе.
_WEAK_VERIFICATION = ("sketch",)
_REPLACEABLE_FAILURES = ("TIMEOUT", "WORKER_ERROR", "PIPELINE_CRASH", "INTERRUPTED")
# Какой сохранённый чертёж можно ПОДСТАВИТЬ вместо неудачного нового запуска.
# Раньше годился любой done-результат, кроме эскиза, — в том числе «проверенный»
# отрезок вместо треугольника (задача 9.6: SLIVER, BAD_ASPECT, «A лежит на BC»,
# измерено 24.5 вместо 15.5). Когда новый код начал отвергать вырождение, очередь
# подставляла именно его — пользователь 21 час видел ту же линию. Теперь годится
# только чистый результат: точная проверка, без предупреждений о вырождении,
# построенный не раньше REUSE_NOT_BEFORE (деплой защиты от вырождения; env
# GEOEXACT_REUSE_NOT_BEFORE переопределяет; 0 — без отсечки по времени).
_REUSE_BAD_CODES = ("SLIVER", "BAD_ASPECT", "UNDECLARED_INCIDENCE", "DEGENERATE",
                    "APPROXIMATE", "SIMPLIFIED", "SKETCH", "INTERNAL", "INVALID_CONDITION")
_NOT_REUSABLE_VERIFICATION = ("sketch", "approximate", "simplified")
_REUSE_DEFAULT_NOT_BEFORE = 1792078800.0      # 2026-10-15 15:40 UTC
_env_nb = (os.environ.get("GEOEXACT_REUSE_NOT_BEFORE") or "").strip()
REUSE_NOT_BEFORE = float(_env_nb) if _env_nb else _REUSE_DEFAULT_NOT_BEFORE


def _reusable(data, created) -> bool:
    """Сохранённый результат достаточно надёжен, чтобы показать его вместо нового."""
    if created < REUSE_NOT_BEFORE:
        return False
    if not isinstance(data, dict) or not data.get("ok") or data.get("kind") == "solution":
        return False
    if data.get("verification") in _NOT_REUSABLE_VERIFICATION or data.get("reused_from"):
        return False
    for w in data.get("warnings") or []:
        code = str(w).split(":", 1)[0].strip()
        if code in _REUSE_BAD_CODES:
            return False
    return bool(data.get("svg"))


def _same_problem(a, b) -> bool:
    norm = lambda s: " ".join(str(s or "").split()).casefold()  # noqa: E731
    return bool(a) and norm(a) == norm(b)


class Queue:
    def __init__(self, engine, *, per_hour=0, per_day=0, daily_usd="0",
                 queue_size=8, runner=None):
        # 0 = лимит отключён (без ограничения). Раньше: 3/час, 10/день,
        # $5/день на сервис — блокировали владельца при активном тестировании.
        self.engine = engine
        self.per_hour = int(per_hour)
        self.per_day = int(per_day)
        self.daily_jobs = (
            0 if Decimal(str(daily_usd)) <= 0
            else int(Decimal(str(daily_usd)) / Decimal("0.10"))
        )
        self.queue_size = int(queue_size)
        if self.queue_size < 1:
            raise ValueError("GeoExact queue_size must be positive")
        self.runner = runner or run_generation
        self._thread = None
        self._start_lock = threading.Lock()
        self._recovered = False

    def submit(self, owner, problem, with_aux, history=None):
        jid = self._admit(owner)
        now = time.time()
        with self.engine.begin() as c:
            c.execute(insert(jobs).values(
                id=jid, owner=owner, status="queued", created=now,
                problem=wrap_problem(problem, history), with_aux=int(with_aux)))
        return jid

    def submit_solution(self, owner, problem, history=None):
        """«Полное решение»: те же лимиты и одна незавершённая задача на пользователя."""
        jid = self._admit(owner)
        now = time.time()
        with self.engine.begin() as c:
            c.execute(insert(jobs).values(
                id=jid, owner=owner, status="queued", created=now,
                problem=wrap_solution(problem, history), with_aux=2))
        return jid

    def _admit(self, owner):
        now = time.time()
        midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp()
        jid = uuid.uuid4().hex
        with self.engine.begin() as c:
            _lock(c)
            count = lambda *where: c.execute(
                select(func.count()).select_from(jobs).where(*where)).scalar_one()
            if count(jobs.c.owner == owner,
                     jobs.c.status.in_(["queued", "running"])):
                raise QueueFull("У вас уже есть незавершённый запрос.")
            if self.per_hour > 0 and count(
                    jobs.c.owner == owner,
                    jobs.c.created > now - 3600) >= self.per_hour:
                raise QueueFull("Часовой лимит исчерпан. Попробуйте позже.")
            if self.per_day > 0 and count(
                    jobs.c.owner == owner,
                    jobs.c.created >= midnight) >= self.per_day:
                raise QueueFull("Дневной лимит исчерпан.")
            if self.daily_jobs > 0 and count(
                    jobs.c.created >= midnight) >= self.daily_jobs:
                raise QueueFull("Дневной лимит сервиса исчерпан.")
            if count(jobs.c.status.in_(["queued", "running"])) >= self.queue_size:
                raise QueueFull("Очередь заполнена. Попробуйте позже.")
        return jid

    def get(self, jid, owner):
        with self.engine.connect() as c:
            row = c.execute(select(
                jobs.c.status, jobs.c.payload, jobs.c.created).where(
                jobs.c.id == jid, jobs.c.owner == owner)).first()
        if not row:
            return None
        if row.status in ("queued", "running"):
            # payload у незавершённого задания — служебная пометка (requeued),
            # клиенту она не нужна. age_sec — возраст задания по часам СЕРВЕРА:
            # фронт показывает честный таймер даже после смены раздела и
            # возврата на страницу (локальные часы браузера не используются).
            return {"status": row.status, "result": None,
                    "age_sec": round(time.time() - row.created, 1)}
        return {"status": row.status,
                "result": json.loads(row.payload) if row.payload else None}

    def last_done(self, owner):
        """Newest successful DRAWING job of this owner that is still stored
        (with_aux=2 is a «full solution» job, not a drawing to restore)."""
        with self.engine.connect() as c:
            row = c.execute(select(jobs.c.id).where(
                jobs.c.owner == owner, jobs.c.status == "done",
                jobs.c.with_aux != 2,
                jobs.c.created > time.time() - 7 * 86400
            ).order_by(jobs.c.created.desc()).limit(1)).first()
        return row.id if row else None

    def previous_drawing(self, owner, problem, with_aux):
        """Последний ПРОВЕРЕННЫЙ чертёж этой же задачи (тот же текст, тот же режим).

        Используется, когда новый запуск дал только эскиз или упал: показать
        проверенный результат недельной давности честнее, чем эскиз без углов и
        длин. Но только если он действительно чистый (см. _reusable).
        Возвращает (payload, created) или None.
        """
        with self.engine.connect() as c:
            rows = c.execute(select(jobs.c.payload, jobs.c.created).where(
                jobs.c.owner == owner, jobs.c.status == "done",
                jobs.c.with_aux == int(bool(with_aux)),
                jobs.c.created > time.time() - 7 * 86400
            ).order_by(jobs.c.created.desc()).limit(30)).all()
        for payload, created in rows:
            try:
                data = json.loads(payload) if payload else None
            except ValueError:
                continue
            if not _reusable(data, created):
                continue
            if _same_problem(data.get("problem_text"), problem):
                return data, created
        return None

    def _reuse_if_better(self, row, payload):
        """Эскиз или сбой при наличии проверенного чертежа той же задачи → тот чертёж."""
        if is_solution_job(row["problem"]):
            return payload
        weak_ok = isinstance(payload, dict) and payload.get("ok") \
            and payload.get("verification") in _WEAK_VERIFICATION
        failed = isinstance(payload, dict) and not payload.get("ok") \
            and payload.get("reason") in _REPLACEABLE_FAILURES
        if not (weak_ok or failed):
            return payload
        problem = unwrap_problem(row["problem"])[0]
        found = self.previous_drawing(row["owner"], problem, row["with_aux"])
        if found is None:
            return payload
        earlier, created = found
        age = max(1, int((time.time() - created) / 60))
        when = (f"{age} мин назад" if age < 120 else f"{age // 60} ч назад"
                if age < 2880 else f"{age // 1440} дн назад")
        why = (payload.get("detail") or payload.get("reason") or "эскиз по ключевым словам") \
            if failed else "получился только схематичный эскиз"
        reused = dict(earlier)
        reused["reused_from"] = when
        reused["warnings"] = [f"Показан предыдущий проверенный чертёж этой задачи ({when}): "
                              f"новый запуск не удался — {why}."] + list(earlier.get("warnings") or [])
        return reused

    # ── Осиротевшие и просроченные задания ─────────────────────────────────────
    def _expire(self, c, where):
        """Задания по условию where: один раз вернуть в очередь, иначе — INTERRUPTED.

        Вызывается внутри транзакции под _lock. Возвращает (requeued, failed).
        """
        rows = c.execute(select(jobs.c.id, jobs.c.payload, jobs.c.problem)
                         .where(where)).all()
        requeued = failed = 0
        for jid, payload, problem in rows:
            if ORPHAN_REQUEUE and problem and not _was_requeued(payload):
                c.execute(update(jobs).where(jobs.c.id == jid).values(
                    status="queued", started=None, payload=_REQUEUED_MARK))
                requeued += 1
            else:
                verdict = _INTERRUPTED_TWICE if _was_requeued(payload) else _INTERRUPTED
                c.execute(update(jobs).where(jobs.c.id == jid).values(
                    status="failed", payload=json.dumps(verdict, ensure_ascii=False),
                    problem=""))
                failed += 1
        return requeued, failed

    def recover_orphans(self):
        """После старта процесса: всё, что числится running, никем не выполняется.

        Исполнитель один на сервис (см. ensure_started), а старт нового процесса
        означает, что прежний умер вместе со своим подпроцессом-воркером. Ждать
        RUNNING_STALE_SEC незачем — задание сразу возвращается в очередь (один
        раз) или завершается INTERRUPTED.
        """
        with self.engine.begin() as c:
            _lock(c)
            return self._expire(c, jobs.c.status == "running")

    def claim(self):
        now = time.time()
        with self.engine.begin() as c:
            _lock(c)
            # Interrupted work: one automatic retry for an orphaned job, then a
            # verdict. Never an endless loop against a paid API.
            self._expire(c, (
                ((jobs.c.status == "running") & (jobs.c.started < now - RUNNING_STALE_SEC)) |
                ((jobs.c.status == "queued") & (jobs.c.created < now - QUEUED_STALE_SEC))
            ))
            c.execute(delete(jobs).where(
                jobs.c.created < now - 7 * 86400,
                jobs.c.status.in_(["done", "failed"])))
            if c.execute(select(jobs.c.id).where(
                    jobs.c.status == "running").limit(1)).first():
                return None
            row = c.execute(select(jobs).where(jobs.c.status == "queued")
                            .order_by(jobs.c.created, jobs.c.id).limit(1)).mappings().first()
            if row is None:
                return None
            c.execute(update(jobs).where(jobs.c.id == row["id"]).values(
                status="running", started=now))
            return dict(row)

    def run_once(self):
        row = self.claim()
        if row is None:
            return False
        try:
            payload = self.runner(row["problem"], int(row["with_aux"]))
            if isinstance(payload, dict) and payload.get("ok"):
                # The result is the user's own; it is kept 7 days so a refresh (or another
                # device) shows the drawing together with its condition.
                source = (unwrap_solution(row["problem"])[0]
                          if is_solution_job(row["problem"])
                          else unwrap_problem(row["problem"])[0])
                payload = dict(payload, problem_text=source[:12000],
                               with_aux=bool(row["with_aux"]))
        except Exception:
            payload = failure("WORKER_ERROR",
                "Не удалось завершить генерацию. Автоматического повторения не было.")
        try:
            payload = self._reuse_if_better(row, payload)
        except Exception:  # noqa: BLE001 - подмена результата никогда не ломает очередь
            pass
        with self.engine.begin() as c:
            c.execute(update(jobs).where(
                jobs.c.id == row["id"], jobs.c.status == "running"
            ).values(status="done" if payload.get("ok") else "failed",
                     payload=json.dumps(payload, ensure_ascii=False), problem=""))
        return True

    def ensure_started(self):
        # Lazy start after Gunicorn fork. One active job across ALL app processes.
        with self._start_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._loop, daemon=True,
                                            name="geoexact-queue")
            self._thread.start()

    def _loop(self):
        import logging
        log = logging.getLogger(__name__)
        while True:
            try:
                if not self._recovered:
                    requeued, failed = self.recover_orphans()
                    self._recovered = True
                    if requeued or failed:
                        log.warning("GeoExact queue: orphaned jobs after restart — "
                                    "requeued=%d, failed=%d", requeued, failed)
                worked = self.run_once()
            except Exception:
                # Never log task text, API responses or connection URLs.
                log.error("GeoExact queue unavailable")
                worked = False
            time.sleep(.2 if worked else 3)


def _sketch_payload(problem, with_aux):
    """Model-free keyword sketch (milliseconds) when the worker ran out of time."""
    try:
        from dataclasses import asdict
        from .core.pipeline import _norm, _sketch_result
        res = _sketch_result(_norm(problem), bool(with_aux), None)
    except Exception:  # noqa: BLE001 - fallback must never break the queue
        return None
    if res is None:
        return None
    payload = asdict(res)
    for field in ("plan", "usage", "cost", "seconds", "retries", "cls"):
        payload.pop(field, None)
    return payload


def run_generation(problem, with_aux):
    if is_solution_job(problem):
        # «Полное решение»: продолжение того же диалога с экспертом + LaTeX.
        problem, history = unwrap_solution(problem)
        env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                   MKL_NUM_THREADS="1")
        try:
            process = subprocess.run(
                [sys.executable, "-m", "geoexact.worker"],
                input=json.dumps({"solution": True, "problem": problem,
                                  "history": history}),
                text=True, capture_output=True, timeout=200, env=env,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "kind": "solution", "reason": "TIMEOUT",
                    "detail": "Превышено время получения решения. Возможен расход API; "
                              "автоматического повторения нет."}
        if process.returncode != 0:
            return {"ok": False, "kind": "solution", "reason": "WORKER_ERROR",
                    "detail": "Не удалось получить полное решение."}
        return json.loads(process.stdout)
    problem, history = unwrap_problem(problem)
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               MKL_NUM_THREADS="1")
    try:
        process = subprocess.run(
            [sys.executable, "-m", "geoexact.worker"],
            input=json.dumps({"problem": problem, "with_aux": with_aux, "history": history}),
            text=True, capture_output=True, timeout=WORKER_TIMEOUT_SEC, env=env,
        )
    except subprocess.TimeoutExpired:
        return _sketch_payload(problem, with_aux) or failure("TIMEOUT",
            "Превышено время генерации. Возможен расход API; автоматического повторения нет.")
    if process.returncode != 0:
        if process.returncode in (124, -14):        # the worker's own time alarm
            return _sketch_payload(problem, with_aux) or failure("TIMEOUT",
                "Превышено время генерации. Возможен расход API; автоматического повторения нет.")
        return failure("WORKER_ERROR", "Не удалось завершить генерацию.")
    return json.loads(process.stdout)
