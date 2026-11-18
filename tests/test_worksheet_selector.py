# -*- coding: utf-8 -*-
"""Спринт 1, этап 2: select_tasks / replace_task на синтетическом банке (БД не нужна)."""
import json
from types import SimpleNamespace

import pytest

from teacher.worksheets import bank_index, history
from teacher.worksheets.selector import select_tasks, replace_task, quotas, source_key


def _rec(pos, grade, topic, level, olympiad=None, year=None, fig=""):
    d = {"position": pos, "grade": grade, "topic": topic, "level": level,
         "task_text": f"Задача {pos} ({topic}, L{level})", "correct_answer": "1", "solution": "…",
         "figure_svg_path": fig}
    if olympiad:
        d["olympiad"], d["year"], d["number"] = olympiad, year, pos % 7 + 1
    return d


@pytest.fixture
def bank(tmp_path, monkeypatch):
    recs, pos = [], 1
    oly = [("ВсОШ", 2021), ("ВсОШ", 2022), ("ВсОШ", 2023), ("Матпраздник", 2022), ("Турнир городов", 2023), (None, None)]
    for topic in ("Делимость", "Комбинаторика"):
        for level in (1, 2, 3, 4):
            for k in range(6):
                o, y = oly[k % len(oly)]
                recs.append(_rec(pos, 8, topic, level, o, y, fig="f.svg" if k == 0 else ""))
                pos += 1
    for k in range(3):
        recs.append(_rec(pos, 7, "Делимость", 1, "ВсОШ", 2020)); pos += 1
    recs.append(_rec(pos, 8, "Редкая", 1, "ВсОШ", 2019)); pos += 1
    recs.append(_rec(pos, 8, "Редкая", 4, "ВсОШ", 2019)); pos += 1
    p = tmp_path / "bank.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in recs), encoding="utf-8")
    bank_index.reset()
    bank_index.load(path=p)
    monkeypatch.setattr(history, "group_solved_task_ids", lambda gid: set())
    monkeypatch.setattr(history, "group_recent_worksheet_task_ids", lambda gid, days=60: set())
    monkeypatch.setattr(history, "group_recent_topics", lambda gid, limit=4: [])
    yield recs
    bank_index.reset()


def _levels(tasks):
    out = {1: 0, 2: 0, 3: 0, 4: 0}
    for t in tasks:
        out[t["target_level"]] += 1
    return out


@pytest.mark.parametrize("n,expected", [(8, (2, 3, 2, 1)), (6, (2, 2, 1, 1)), (10, (3, 4, 2, 1))])
def test_quotas(n, expected):
    q = quotas(n)
    assert (q[1], q[2], q[3], q[4]) == expected
    assert sum(q.values()) == n


def test_quotas_redistribute_outside_range():
    q = quotas(8, level_min=2, level_max=3)
    assert q[1] == 0 and q[4] == 0 and sum(q.values()) == 8


@pytest.mark.parametrize("n", [6, 8, 10])
def test_distribution_when_enough_candidates(bank, n):
    tasks, warnings = select_tasks(8, ["Делимость", "Комбинаторика"], n=n, seed=1)
    assert len(tasks) == n
    q = quotas(n)
    assert _levels(tasks) == q
    assert [t["target_level"] for t in tasks] == sorted(t["target_level"] for t in tasks)
    assert not any("не хватило" in w for w in warnings)


def test_adjacent_sources_differ_and_min_olympiad(bank):
    tasks, _ = select_tasks(8, ["Делимость"], n=8, seed=7)
    keys = [source_key(bank_index.get(t["task_id"])) for t in tasks]
    for a, b in zip(keys, keys[1:]):
        assert a is None or b is None or a != b
    assert sum(1 for t in tasks if t["source"]) >= 2


def test_only_olympiad(bank):
    tasks, _ = select_tasks(8, ["Делимость", "Комбинаторика"], n=8, only_olympiad=True, seed=3)
    assert len(tasks) == 8 and all(t["source"] for t in tasks)


def test_deterministic_by_seed(bank):
    a, _ = select_tasks(8, ["Делимость"], n=8, seed=42)
    b, _ = select_tasks(8, ["Делимость"], n=8, seed=42)
    c, _ = select_tasks(8, ["Делимость"], n=8, seed=43)
    assert [t["task_id"] for t in a] == [t["task_id"] for t in b]
    assert [t["task_id"] for t in a] != [t["task_id"] for t in c]


def test_exclusions_solved_and_recent(bank, monkeypatch):
    solved = {r["position"] for r in bank if r["topic"] == "Делимость" and r["level"] == 2}
    recent = {r["position"] for r in bank if r["topic"] == "Делимость" and r["level"] == 3}
    monkeypatch.setattr(history, "group_solved_task_ids", lambda gid: solved)
    monkeypatch.setattr(history, "group_recent_worksheet_task_ids", lambda gid, days=60: recent)
    tasks, warnings = select_tasks(8, ["Делимость"], n=8, exclude_group_id=1, seed=5)
    ids = {t["task_id"] for t in tasks}
    assert not ids & solved and not ids & recent
    assert any("не хватило" in w for w in warnings)
    assert len(tasks) == 8


def test_younger_grade_only_on_level1_positions(bank):
    tasks, _ = select_tasks(8, ["Делимость"], n=8, seed=11)
    for t in tasks:
        if t["grade"] == 7:
            assert t["target_level"] == 1


def test_shortage_borrows_neighbor_level_with_warning(bank):
    tasks, warnings = select_tasks(8, ["Редкая"], n=4, seed=2)
    assert len(tasks) == 2
    assert any("кандидатов нет" in w or "не хватило" in w for w in warnings)
    assert any("собрано 2 из 4" in w for w in warnings)


def test_mixed_mode_uses_group_recent_topics(bank, monkeypatch):
    monkeypatch.setattr(history, "group_recent_topics", lambda gid, limit=4: ["Комбинаторика"])
    tasks, _ = select_tasks(8, None, n=8, mode="mixed", exclude_group_id=1, seed=1)
    assert tasks and all(t["topic"] == "Комбинаторика" for t in tasks)


def _ws(tasks, grade=8, group_id=None):
    rows = [SimpleNamespace(task_id=t["task_id"], position=t["position"], target_level=t["target_level"], added_by="selector")
            for t in tasks]
    return SimpleNamespace(id=1, teacher_id=1, grade=grade, group_id=group_id, tasks=rows)


@pytest.mark.parametrize("direction", ["same", "harder", "easier"])
def test_replace_task_directions(bank, direction):
    tasks, _ = select_tasks(8, ["Делимость"], n=8, seed=9)
    victim = next(t for t in tasks if t["level"] == 2)
    ws = _ws(tasks)
    before = {t.task_id for t in ws.tasks}
    new, warnings = replace_task(ws, victim["task_id"], direction, seed=1)
    assert new is not None and not warnings
    assert new["task_id"] not in before
    assert new["topic"] == "Делимость"
    expected = {"same": 2, "harder": 3, "easier": 1}[direction]
    assert new["level"] == expected
    row = next(t for t in ws.tasks if t.task_id == new["task_id"])
    assert row.added_by == "teacher" and row.target_level == expected


def test_replace_task_respects_group_solved(bank, monkeypatch):
    tasks, _ = select_tasks(8, ["Делимость"], n=8, seed=9)
    victim = next(t for t in tasks if t["level"] == 4)
    others = {r["position"] for r in bank if r["topic"] == "Делимость" and r["level"] == 4} - {victim["task_id"]}
    monkeypatch.setattr(history, "group_solved_task_ids", lambda gid: others)
    new, warnings = replace_task(_ws(tasks, group_id=1), victim["task_id"], "same", seed=1)
    assert new is None and warnings


def test_replace_task_no_harder_than_4(bank):
    tasks, _ = select_tasks(8, ["Делимость"], n=8, seed=9)
    victim = next(t for t in tasks if t["level"] == 4)
    new, warnings = replace_task(_ws(tasks), victim["task_id"], "harder")
    assert new is None and warnings
