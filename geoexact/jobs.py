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


def failure(code, message):
    return {"ok": False, "reason": code, "detail": message}


class Queue:
    def __init__(self, engine, *, per_hour=3, per_day=10, daily_usd="5.00",
                 queue_size=8, runner=None):
        self.engine = engine
        self.per_hour = int(per_hour)
        self.per_day = int(per_day)
        self.daily_jobs = int(Decimal(str(daily_usd)) / Decimal("0.10"))
        self.queue_size = int(queue_size)
        if min(self.per_hour, self.per_day, self.daily_jobs, self.queue_size) < 1:
            raise ValueError("GeoExact limits must be positive")
        self.runner = runner or run_generation
        self._thread = None
        self._start_lock = threading.Lock()

    def submit(self, owner, problem, with_aux):
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
            if count(jobs.c.owner == owner, jobs.c.created > now - 3600) >= self.per_hour:
                raise QueueFull("Часовой лимит исчерпан. Попробуйте позже.")
            if count(jobs.c.owner == owner, jobs.c.created >= midnight) >= self.per_day:
                raise QueueFull("Дневной лимит исчерпан.")
            if count(jobs.c.created >= midnight) >= self.daily_jobs:
                raise QueueFull("Дневной лимит сервиса исчерпан.")
            if count(jobs.c.status.in_(["queued", "running"])) >= self.queue_size:
                raise QueueFull("Очередь заполнена. Попробуйте позже.")
            c.execute(insert(jobs).values(
                id=jid, owner=owner, status="queued", created=now,
                problem=problem, with_aux=int(with_aux)))
        return jid

    def get(self, jid, owner):
        with self.engine.connect() as c:
            row = c.execute(select(jobs.c.status, jobs.c.payload).where(
                jobs.c.id == jid, jobs.c.owner == owner)).first()
        if not row:
            return None
        return {"status": row.status,
                "result": json.loads(row.payload) if row.payload else None}

    def claim(self):
        now = time.time()
        with self.engine.begin() as c:
            _lock(c)
            # Interrupted work is failed, NEVER automatically re-sent to a paid API.
            expired = failure("INTERRUPTED",
                "Генерация прервана или истекло время ожидания. "
                "Автоматического платного повторения не было.")
            c.execute(update(jobs).where(
                ((jobs.c.status == "running") & (jobs.c.started < now - 900)) |
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
            payload = self.runner(row["problem"], bool(row["with_aux"]))
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


def run_generation(problem, with_aux):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
               MKL_NUM_THREADS="1")
    try:
        process = subprocess.run(
            [sys.executable, "-m", "geoexact.worker"],
            input=json.dumps({"problem": problem, "with_aux": with_aux}),
            text=True, capture_output=True, timeout=600, env=env,
        )
    except subprocess.TimeoutExpired:
        return failure("TIMEOUT",
            "Превышено время генерации. Возможен расход API; автоматического повторения нет.")
    if process.returncode != 0:
        return failure("WORKER_ERROR", "Не удалось завершить генерацию.")
    return json.loads(process.stdout)
