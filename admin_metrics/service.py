"""Metrics from recorded facts, never from cached user counters or demo plans.

All displayed days are Europe/Moscow. Existing naive timestamps are UTC.
Missing tables/columns produce null, not a fabricated zero. No writes, no ORM
imports and no app startup: this collector can also run with a read-only DB user.
"""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import MetaData, Table, and_, func, inspect, select

MSK = timezone(timedelta(hours=3))


def collect_metrics(engine, day=None, days=7):
    day = day or datetime.now(MSK).date()
    if type(day) is not date or not 1 <= days <= 31:
        raise ValueError("day must be a date and days must be between 1 and 31")
    if day > datetime.now(MSK).date():
        raise ValueError("Future dates are not measured")
    first = day - timedelta(days=days - 1)
    metadata = MetaData()
    missing = set()

    def bounds(d):
        start = datetime.combine(d, time.min) - timedelta(hours=3)
        return start, start + timedelta(days=1)

    with engine.connect() as conn:
        if conn.dialect.name == "postgresql":
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
        names = set(inspect(conn).get_table_names())

        def table(name, columns):
            if name not in names:
                missing.add(name)
                return None
            t = metadata.tables.get(name)
            if t is None:
                t = Table(name, metadata, autoload_with=conn)
            absent = set(columns) - set(t.c.keys())
            if absent:
                missing.update(f"{name}.{c}" for c in absent)
                return None
            return t

        def timestamp_range(column, start=None, stop=None):
            # Legacy SQLite rows sometimes omit fractional seconds. Comparing
            # raw strings to SQLAlchemy's ".000000" bindings shifts boundaries.
            value = func.julianday(column) if conn.dialect.name == "sqlite" else column
            terms = []
            for bound, lower in ((start, True), (stop, False)):
                if bound is not None:
                    b = func.julianday(bound) if conn.dialect.name == "sqlite" else bound
                    terms.append(value >= b if lower else value < b)
            return and_(*terms)

        users = table("users", ["id", "is_guest", "created_at"])

        def user_count(*conditions):
            if users is None:
                return None
            return conn.scalar(select(func.count()).select_from(users).where(
                users.c.is_guest.is_(False), *conditions))

        def user_field_count(field, predicate):
            t = table("users", [field])
            if t is None:
                return None
            return user_count(predicate(t.c[field]))

        end = bounds(day)[1]
        registrations = user_count(timestamp_range(users.c.created_at, stop=end)) if users is not None else None
        new = user_count(timestamp_range(users.c.created_at, bounds(day)[0], end)) if users is not None else None
        teachers = user_field_count("role", lambda c: c == "teacher")
        tg = user_field_count("telegram_id", lambda c: and_(c.isnot(None), c != ""))
        trials = user_field_count("trial_started_at", lambda c: timestamp_range(c, bounds(day)[0], end))
        stats = table("site_time_sections", ["user_id", "day", "seconds"])

        def active(start, finish):
            if stats is None or users is None:
                return None
            return conn.scalar(select(func.count(func.distinct(stats.c.user_id)))
                .select_from(stats.join(users, stats.c.user_id == users.c.id))
                .where(stats.c.day >= start, stats.c.day <= finish,
                       stats.c.seconds > 0, users.c.is_guest.is_(False)))

        # Each source represents persisted records, not every resubmission.
        sources = []
        daily = table("daily_task_items", ["daily_set_id", "is_correct", "answered_at"])
        sets = table("daily_task_sets", ["id", "user_id"])
        if daily is not None and sets is not None:
            sources.append(("daily", daily.join(sets, daily.c.daily_set_id == sets.c.id),
                            sets.c.user_id, daily.c.answered_at, daily.c.is_correct.is_(True), None))
        for key, name, stamp, flag in [
            ("bank", "bank_issues", "answered_at", "is_correct"),
            ("olympiad", "olympiad_task_attempts", "finished_at", "status"),
            ("verified", "verified_problem_checks", "solved_at", "is_correct"),
        ]:
            t = table(name, ["user_id", stamp, flag])
            if t is not None:
                ok = t.c[flag] == "solved" if flag == "status" else t.c[flag].is_(True)
                sources.append((key, t, t.c.user_id, t.c[stamp], ok, None))
        practice = table("insight_practice_tasks", ["insight_id", "is_correct", "solved_at"])
        insights = table("insights", ["id", "user_id"])
        if practice is not None and insights is not None:
            sources.append(("insight", practice.join(insights, practice.c.insight_id == insights.c.id),
                            insights.c.user_id, practice.c.solved_at,
                            practice.c.is_correct.is_(True), None))
        client = table("test_results_detail", ["user_id", "task_id", "test_type", "is_correct", "created_at"])
        if client is not None:
            sources.append(("client_practice", client, client.c.user_id, client.c.created_at,
                            and_(client.c.test_type == "practice", client.c.is_correct.is_(True),
                                 client.c.task_id.isnot(None)), client.c.task_id))

        series = []
        for offset in range(days):
            d = first + timedelta(days=offset)
            start, stop = bounds(d)
            counts = {k: None for k in ("daily", "bank", "olympiad", "verified", "insight", "client_practice")}
            if users is not None:
                for key, source, uid, stamp, correct, task in sources:
                    query = select(uid).select_from(source.join(users, uid == users.c.id)).where(
                        users.c.is_guest.is_(False), timestamp_range(stamp, start, stop), correct)
                    if task is not None:
                        query = query.add_columns(task).distinct()
                    counts[key] = conn.scalar(select(func.count()).select_from(query.subquery()))
            server = [counts[k] for k in ("daily", "bank", "olympiad", "verified", "insight")]
            series.append({
                "date": d.isoformat(), "tracked_dau": active(d, d),
                "solved_by_source": counts,
                "server_solved": sum(server) if all(x is not None for x in server) else None,
                "available_server_solved": sum(x for x in server if x is not None),
            })
        return {
            "as_of": day.isoformat(), "timezone": "Europe/Moscow",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "registrations": registrations, "registrations_day": new,
            "teachers_current": teachers, "telegram_linked_current": tg,
            "trials_started_day": trials,
            "tracked_dau": active(day, day),
            "tracked_wau": active(day - timedelta(days=6), day),
            "paying_users": None, "telegram_subscribers": None,
            "series": series, "unavailable": sorted(missing),
            "definitions": {
                "activity": "Уникальные негостевые пользователи с seconds > 0 в site_time_sections. Только отслеженная активность, не все посещения.",
                "wau": "Выбранный день и 6 предыдущих дней, уникальные пользователи за весь интервал.",
                "solved": "Верные сохранённые записи по времени ответа; не все попытки и не уникальные задачи между разделами. Старый ответ может быть перезаписан.",
                "client_practice": "Клиентские результаты тренажёра считаются отдельно, без серверного подтверждения.",
                "population": "Гости исключены. Учителя и привязки Telegram показывают текущее состояние, не исторический снимок.",
                "payments": "Демо-Premium не означает оплату. Платёжный источник не подключён.",
                "telegram": "Привязанный Telegram не означает подписку на канал. Подписчики канала неизвестны.",
            },
        }
