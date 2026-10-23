# -*- coding: utf-8 -*-
"""Смена раздела не перезапускает генерацию: задание живёт в очереди сервера,
а его возраст клиент узнаёт от сервера (age_sec). Тогда после возврата в раздел
таймер продолжает показывать «уже строится N секунд», а не «часы с нуля»,
которые выглядели как перезапуск генерации."""
import time

from geoexact import jobs
from geoexact.jobs import jobs as jobs_table
from sqlalchemy import update


def _queue(tmp_path, runner):
    engine = jobs.create_engine(f"sqlite:///{tmp_path}/q.db")
    jobs.init_db(engine)
    return jobs.Queue(engine, runner=runner)


def test_unfinished_job_reports_server_age(tmp_path):
    q = _queue(tmp_path, runner=lambda p, a: {"ok": True})
    jid = q.submit("u1", "В треугольнике ABC проведена медиана AM.", False)
    row = q.get(jid, "u1")
    assert row["status"] == "queued"
    # возраст по часам СЕРВЕРА: фронт не должен полагаться на свои часы
    assert isinstance(row["age_sec"], float)
    assert 0.0 <= row["age_sec"] < 60.0


def test_age_reflects_server_clock_deterministically(tmp_path):
    """Задание создано 45 секунд назад — возраст обязан быть ~45, а не 0.

    Ловит регрессию «age_sec всегда 0»: тогда после возврата в раздел таймер
    снова начинался бы с нуля и выглядел как перезапуск генерации."""
    q = _queue(tmp_path, runner=lambda p, a: {"ok": True})
    jid = q.submit("u1", "В треугольнике ABC проведена медиана AM.", False)
    with q.engine.begin() as c:
        c.execute(update(jobs_table).where(jobs_table.c.id == jid)
                  .values(created=time.time() - 45))
    row = q.get(jid, "u1")
    assert row["status"] == "queued"
    assert 44.0 <= row["age_sec"] <= 60.0


def test_done_job_has_no_age(tmp_path):
    q = _queue(tmp_path, runner=lambda p, a: {"ok": True, "svg": "<svg/>"})
    jid = q.submit("u1", "В треугольнике ABC проведена медиана AM.", False)
    q.run_once()
    row = q.get(jid, "u1")
    assert row["status"] == "done"
    assert "age_sec" not in row          # готовому чертежу таймер не нужен
