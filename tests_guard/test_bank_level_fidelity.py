# -*- coding: utf-8 -*-
"""Шаг 6. Верность уровня подборки.

Инвариант: ни одна задача в выдаче не отстоит от запрошенного уровня больше
чем на 1, пока соседние уровни не исчерпаны. Уровень ±2 допустим ТОЛЬКО когда
в соседних ячейках задач не хватило. Скачок «уровень 1 -> уровень 3» или
«уровень 4 -> уровень 2» при живых соседях — дефект.

Две части:
  * синтетический индекс — точные проверки механики;
  * реальный FORMYLA_BANK.jsonl — для каждой ячейки (класс, тема) и каждого
    уровня 1..4 выдача из 5 задач не содержит уровней дальше ±1 от запрошенного,
    (если в уровнях L-1..L+1 суммарно есть >=5 задач), и, если ячейка точного
    уровня полная (>=5), все 5 задач — точного уровня.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BANK_MODULE = ROOT / "daily_tasks" / "formyla_bank.py"
DAILY_COUNT = 5


def _fresh_module(name):
    os.environ.pop("FORMYLA_JSONL_FALLBACK", None)
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, BANK_MODULE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cell(level, n, grade=9, topic="Тест-тема"):
    return [{"grade": grade, "topic": topic, "level": level, "position": i,
             "task_text": f"{topic} L{level} #{i}", "correct_answer": "1"}
            for i in range(1, n + 1)]


def _levels(tasks):
    return [int(t["level"]) for t in tasks]


# ───────────────────────── синтетика ─────────────────────────

def test_no_jump_over_level_when_neighbors_alive():
    fb = _fresh_module("_fb_fid_a")
    fb._index = {(9, "Тест-тема", 1): _cell(1, 35), (9, "Тест-тема", 2): _cell(2, 35),
                 (9, "Тест-тема", 4): _cell(4, 35)}
    fb._loaded = True
    got = _levels(fb.get_tasks(9, "Тест-тема", 3, count=DAILY_COUNT, user_id=None, day_seed=0))
    assert got and all(abs(lv - 3) <= 1 for lv in got), f"скачок через уровень: {got}"
    assert 1 not in got


def test_level_plus_minus_2_only_when_neighbors_exhausted():
    fb = _fresh_module("_fb_fid_b")
    fb._index = {(9, "Тест-тема", 1): _cell(1, 35), (9, "Тест-тема", 2): _cell(2, 1),
                 (9, "Тест-тема", 4): _cell(4, 1)}
    fb._loaded = True
    got = Counter(_levels(fb.get_tasks(9, "Тест-тема", 3, count=DAILY_COUNT, user_id=None, day_seed=0)))
    assert got[2] == 1 and got[4] == 1, f"сначала исчерпываются соседи: {dict(got)}"
    assert got[1] == 3, f"уровень -2 добирает только остаток: {dict(got)}"


def test_level1_student_never_gets_level3_with_live_level2():
    fb = _fresh_module("_fb_fid_c")
    fb._index = {(7, "Тест-тема", 2): _cell(2, 35), (7, "Тест-тема", 3): _cell(3, 35),
                 (7, "Тест-тема", 4): _cell(4, 35)}
    fb._loaded = True
    got = _levels(fb.get_tasks(7, "Тест-тема", 1, count=DAILY_COUNT, user_id=None, day_seed=0))
    assert got == [2] * DAILY_COUNT, f"ученик уровня 1 при пустом L1 получает только L2: {got}"


def test_level4_student_never_gets_level2_with_live_level3():
    fb = _fresh_module("_fb_fid_d")
    fb._index = {(11, "Тест-тема", 2): _cell(2, 35), (11, "Тест-тема", 3): _cell(3, 35)}
    fb._loaded = True
    got = _levels(fb.get_tasks(11, "Тест-тема", 4, count=DAILY_COUNT, user_id=None, day_seed=1))
    assert got == [3] * DAILY_COUNT, f"ученик уровня 4 при пустом L4 получает только L3: {got}"


def test_full_cell_gives_exact_level_only():
    fb = _fresh_module("_fb_fid_e")
    fb._index = {(8, "Тест-тема", lv): _cell(lv, 35) for lv in (1, 2, 3, 4)}
    fb._loaded = True
    for lv in (1, 2, 3, 4):
        for seed in (0, 1, 5):
            got = _levels(fb.get_tasks(8, "Тест-тема", lv, count=DAILY_COUNT, user_id=777, day_seed=seed))
            assert got == [lv] * DAILY_COUNT, f"уровень {lv}, seed {seed}: {got}"


# ───────────────────────── реальный банк ─────────────────────────

@pytest.fixture(scope="module")
def real_bank():
    mod = _fresh_module("_fb_fid_real")
    mod.load()
    if not mod._index:
        pytest.skip("FORMYLA_BANK.jsonl не загружен")
    return mod


def test_real_bank_no_task_farther_than_one_level(real_bank):
    fb = real_bank
    cells = sorted({(g, t) for (g, t, _) in fb._index})
    problems = []
    for g, topic in cells:
        for level in (1, 2, 3, 4):
            got = _levels(fb.get_tasks(g, topic, level, count=DAILY_COUNT, user_id=None))
            if not got:
                problems.append(f"класс {g}, «{topic}», L{level}: пусто")
                continue
            near_pool = sum(len(fb._index.get((g, topic, lv), ())) for lv in (level - 1, level, level + 1))
            far = [lv for lv in got if abs(lv - level) > 1]
            if far and near_pool >= DAILY_COUNT:
                problems.append(f"класс {g}, «{topic}», L{level}: задачи уровней {sorted(set(far))}, хотя в уровнях {level-1}..{level+1} есть {near_pool} задач")
            exact_cell = len(fb._index.get((g, topic, level), ()))
            if exact_cell >= DAILY_COUNT and any(lv != level for lv in got):
                problems.append(f"класс {g}, «{topic}», L{level}: ячейка полная ({exact_cell}), но выданы уровни {sorted(set(got))}")
    assert not problems, "\n".join(problems[:40]) + (f"\n… и ещё {len(problems) - 40}" if len(problems) > 40 else "")


def test_real_bank_hole_mix_is_not_mostly_lower(real_bank):
    """Для каждой дырки (пустая ячейка уровня 2 или 3) выдача не должна быть
    преимущественно из уровня ниже — это ровно сценарий скриншота 15.10."""
    fb = real_bank
    cells = sorted({(g, t) for (g, t, _) in fb._index})
    problems = []
    for g, topic in cells:
        for level in (2, 3):
            if fb._index.get((g, topic, level)):
                continue
            if not fb._index.get((g, topic, level + 1)) or not fb._index.get((g, topic, level - 1)):
                continue
            for seed in (0, 1):
                got = Counter(_levels(fb.get_tasks(g, topic, level, count=DAILY_COUNT, user_id=None, day_seed=seed)))
                if got[level - 1] > got[level + 1]:
                    problems.append(f"класс {g}, «{topic}», L{level} (дырка), seed {seed}: снизу {got[level-1]}, сверху {got[level+1]}")
    assert not problems, "\n".join(problems)
