# -*- coding: utf-8 -*-
"""Эскиз или сбой при наличии проверенного чертежа той же задачи → показывается он.

Один и тот же текст условия каждый раз заново уходит в модель (use_cache=False), и
один из запусков может дать только схематичный эскиз или упасть. Пользователю
честнее показать проверенный чертёж недельной давности с пометкой, чем эскиз без
углов и длин."""
from geoexact import jobs


def _queue(tmp_path, runner):
    engine = jobs.create_engine(f"sqlite:///{tmp_path}/q.db")
    jobs.init_db(engine)
    return jobs.Queue(engine, runner=runner)


def test_sketch_and_crash_are_replaced_by_previous_verified_drawing(tmp_path):
    calls = {"n": 0}

    def runner(problem, with_aux):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": True, "svg": "<svg>good</svg>", "verification": "constraints_only",
                    "warnings": ["w1"]}
        if calls["n"] == 2:
            return {"ok": True, "svg": "<svg>sketch</svg>", "verification": "sketch",
                    "warnings": ["SKETCH: ..."]}
        return {"ok": False, "reason": "PIPELINE_CRASH",
                "detail": "Внутренняя ошибка построения: ZeroDivisionError (render.py:10)"}

    q = _queue(tmp_path, runner)
    text = "В треугольнике ABC угол C = 60°, медиана AM = 6."
    first = q.submit("u1", text, True); q.run_once()
    second = q.submit("u1", "В треугольнике  ABC угол C = 60°, медиана AM = 6.", True); q.run_once()
    third = q.submit("u1", text, True); q.run_once()
    other = q.submit("u1", "Другая задача", True); q.run_once()

    assert q.get(first, "u1")["result"]["svg"] == "<svg>good</svg>"
    r2 = q.get(second, "u1")
    assert r2["status"] == "done" and r2["result"]["svg"] == "<svg>good</svg>"
    assert r2["result"]["reused_from"] and "эскиз" in r2["result"]["warnings"][0]
    r3 = q.get(third, "u1")
    assert r3["status"] == "done" and r3["result"]["svg"] == "<svg>good</svg>"
    assert "ZeroDivisionError" in r3["result"]["warnings"][0]
    r4 = q.get(other, "u1")
    assert r4["status"] == "failed" and r4["result"]["reason"] == "PIPELINE_CRASH"


def test_other_mode_and_other_user_are_not_reused(tmp_path):
    outputs = iter([
        {"ok": True, "svg": "<svg>good</svg>", "verification": "constraints_only"},
        {"ok": True, "svg": "<svg>sketch</svg>", "verification": "sketch"},
        {"ok": True, "svg": "<svg>sketch</svg>", "verification": "sketch"},
    ])
    q = _queue(tmp_path, lambda p, w: next(outputs))
    q.submit("u1", "Задача", True); q.run_once()
    no_aux = q.submit("u1", "Задача", False); q.run_once()
    stranger = q.submit("u2", "Задача", True); q.run_once()
    assert q.get(no_aux, "u1")["result"]["svg"] == "<svg>sketch</svg>"
    assert q.get(stranger, "u2")["result"]["svg"] == "<svg>sketch</svg>"
