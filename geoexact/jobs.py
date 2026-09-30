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


class QueueFull(Exception):
    pass


def make_engine(url):
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return create_engine(url, pool_pre_ping=True)


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


def wrap_problem(problem, history, expert="luna"):
    """Job text with the expert chat and the chosen expert attached (the jobs table has
    no spare column). A plain Luna job without history stays the bare problem text."""
    if not history and expert != "sol":
        return problem
    return _HISTORY_MARK + json.dumps({"p": problem, "h": history or [], "e": expert},
                                      ensure_ascii=False)


def wrap_solution(problem, history, expert="luna"):
    """Job text of a «full solution» request (same column, different marker)."""
    return _SOLUTION_MARK + json.dumps({"p": problem, "h": history or [], "e": expert},
                                       ensure_ascii=False)


def unwrap_expert(stored):
    """Which expert a stored job asked for; old jobs without the field are Luna."""
    for mark in (_HISTORY_MARK, _SOLUTION_MARK):
        if isinstance(stored, str) and stored.startswith(mark):
            try:
                e = json.loads(stored[len(mark):]).get("e")
            except (ValueError, AttributeError, TypeError):
                return "luna"
            return e if e == "sol" else "luna"
    return "luna"


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
            return d["p"], (d["h"] or None)
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

    def submit(self, owner, problem, with_aux, history=None, expert="luna"):
        jid = self._admit(owner)
        now = time.time()
        with self.engine.begin() as c:
            c.execute(insert(jobs).values(
                id=jid, owner=owner, status="queued", created=now,
                problem=wrap_problem(problem, history, expert), with_aux=int(with_aux)))
        return jid

    def submit_solution(self, owner, problem, history=None, expert="luna"):
        """«Полное решение»: те же лимиты и одна незавершённая задача на пользователя."""
        jid = self._admit(owner)
        now = time.time()
        with self.engine.begin() as c:
            c.execute(insert(jobs).values(
                id=jid, owner=owner, status="queued", created=now,
                problem=wrap_solution(problem, history, expert), with_aux=2))
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
            row = c.execute(select(jobs.c.status, jobs.c.payload).where(
                jobs.c.id == jid, jobs.c.owner == owner)).first()
        if not row:
            return None
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

    def claim(self):
        now = time.time()
        with self.engine.begin() as c:
            _lock(c)
            # Interrupted work is failed, NEVER automatically re-sent to a paid API.
            expired = failure("INTERRUPTED",
                "Генерация прервана или истекло время ожидания. "
                "Автоматического платного повторения не было.")
            c.execute(update(jobs).where(
                ((jobs.c.status == "running") & (jobs.c.started < now - 400)) |
                ((jobs.c.status == "queued") & (jobs.c.created < now - 1800))
            ).values(status="failed", payload=json.dumps(expired, ensure_ascii=False),
                     problem=""))
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
        while True:
            try:
                worked = self.run_once()
            except Exception:
                # Never log task text, API responses or connection URLs.
                logging.getLogger(__name__).error("GeoExact queue unavailable")
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
        expert = unwrap_expert(problem)
        problem, history = unwrap_solution(problem)
        env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                   MKL_NUM_THREADS="1")
        try:
            process = subprocess.run(
                [sys.executable, "-m", "geoexact.worker"],
                input=json.dumps({"solution": True, "problem": problem,
                                  "history": history,
                                  **({"expert": "sol"} if expert == "sol" else {})}),
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
    expert = unwrap_expert(problem)
    problem, history = unwrap_problem(problem)
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               MKL_NUM_THREADS="1")
    try:
        process = subprocess.run(
            [sys.executable, "-m", "geoexact.worker"],
            input=json.dumps({"problem": problem, "with_aux": with_aux, "history": history,
                              **({"expert": "sol"} if expert == "sol" else {})}),
            text=True, capture_output=True, timeout=215, env=env,
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
