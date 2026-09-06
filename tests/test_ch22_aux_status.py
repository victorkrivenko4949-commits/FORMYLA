# -*- coding: utf-8 -*-
"""CH22 STEP 1: aux_status переходы (5 значений)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import routes.figures_generator as fg  # noqa: E402


BASE_PLAN = {
    "canvas": {"width": 600, "height": 500, "margin": 40},
    "constructions": [
        {"type": "free_point", "id": "A", "x": 300, "y": 80},
        {"type": "free_point", "id": "B", "x": 120, "y": 400},
        {"type": "free_point", "id": "C", "x": 480, "y": 400},
        {"type": "triangle_isosceles", "id": "tri_ABC", "p1": "A", "p2": "B", "p3": "C"},
        {"type": "segment", "id": "AB", "p1": "A", "p2": "B"},
        {"type": "segment", "id": "AC", "p1": "A", "p2": "C"},
        {"type": "segment", "id": "BC", "p1": "B", "p2": "C"},
    ],
}

AUX_ALTITUDE = {
    "has_aux": True,
    "reason": "Проведём высоту AH.",
    "constructions": [{
        "type": "altitude", "id": "aux_alt_AH", "vertex": "A",
        "side_a": "B", "side_b": "C", "foot_id": "H",
        "dashed": True, "style": "aux", "purpose": "высота",
        "solution_evidence": {"step_no": 1, "quote": "Проведём высоту AH"},
    }],
}

AUX_NONE = {"has_aux": False, "reason": "", "constructions": []}


def _run(app, user, monkeypatch, aux, solution_text, base=None, aux_calls=None):
    from models import db, FigureBuildJob

    base = base or BASE_PLAN
    counter = {"n": 0}

    def fake(messages, model_name=None, role="base"):
        system = messages[0]["content"] if messages else ""
        if "aux-чертёж" in system:
            if aux_calls is not None:
                aux_calls["n"] += 1
                idx = aux_calls["n"]
                if idx <= len(aux_calls["responses"]):
                    return {"content": json.dumps(aux_calls["responses"][idx - 1], ensure_ascii=False),
                            "cost_usd": 0.0, "model": model_name or "test", "usage": {}}
            return {"content": json.dumps(aux, ensure_ascii=False),
                    "cost_usd": 0.0, "model": model_name or "test", "usage": {}}
        return {"content": json.dumps(base, ensure_ascii=False),
                "cost_usd": 0.0, "model": model_name or "test", "usage": {}}

    monkeypatch.setattr(fg, "_call_deepseek", fake)
    monkeypatch.setattr(fg, "FIGURE_CREDITS_ENFORCED", True)
    # CH23 PART B3: aux_status-переходы CH22 проверяют legacy-планировщик,
    # сохранённый за флагом.
    monkeypatch.setattr(fg, "FIGURE_AUX_LEGACY_PLANNER", True)
    job = FigureBuildJob(
        user_id=user.id,
        problem_text="В треугольнике ABC AB=AC.",
        solution_text=solution_text,
        generation_mode="condition_solution",
        status="queued",
    )
    db.session.add(job); db.session.commit()
    fg._run_condition_solution_job(job.id, job)
    return db.session.get(FigureBuildJob, job.id)


@pytest.fixture
def user(app, test_user):
    from models import db
    test_user.figure_credits = 10
    db.session.commit()
    return test_user


class TestAuxStatus:
    def test_aux_not_needed(self, app, user, monkeypatch):
        job = _run(app, user, monkeypatch, AUX_NONE, "1. Ответ очевиден.")
        assert job.aux_status == "AUX_NOT_NEEDED"

    def test_aux_built(self, app, user, monkeypatch):
        job = _run(app, user, monkeypatch, AUX_ALTITUDE,
                   "1. Проведём высоту AH из вершины A на сторону BC.")
        assert job.aux_status == "AUX_BUILT"
        assert job.has_aux is True

    def test_aux_plan_rejected(self, app, user, monkeypatch):
        # aux с сегментом без действия построения — валидатор отклоняет.
        bad_aux = {
            "has_aux": True, "reason": "x",
            "constructions": [{
                "type": "segment", "id": "s1", "p1": "A", "p2": "B",
                "dashed": True, "style": "aux", "purpose": "x",
                "solution_evidence": {"step_no": 1, "quote": "MC является радиусом"},
            }],
        }
        job = _run(app, user, monkeypatch, bad_aux, "1. MC является радиусом.")
        assert job.aux_status == "AUX_PLAN_REJECTED"
        assert job.status == "failed"

    def test_aux_rolled_back(self, app, user, monkeypatch):
        # Первая попытка невалидна, вторая откатывается к has_aux=false.
        bad_aux = {
            "has_aux": True, "reason": "x",
            "constructions": [{
                "type": "segment", "id": "s1", "p1": "A", "p2": "B",
                "dashed": True, "style": "aux", "purpose": "x",
                "solution_evidence": {"step_no": 1, "quote": "MC является радиусом"},
            }],
        }
        job = _run(app, user, monkeypatch, None, "1. MC является радиусом.",
                   aux_calls={"n": 0, "responses": [bad_aux, AUX_NONE]})
        assert job.aux_status == "AUX_ROLLED_BACK"

    def test_aux_build_failed(self, app, user, monkeypatch):
        # Валидный aux-план, но движок не строит: параллельные прямые пересечь
        # нельзя -> ConstructionError -> AUX_BUILD_FAILED.
        base_with_parallel = {
            "canvas": {"width": 600, "height": 500, "margin": 40},
            "constructions": [
                {"type": "free_point", "id": "A", "x": 100, "y": 100},
                {"type": "free_point", "id": "B", "x": 400, "y": 100},
                {"type": "free_point", "id": "C", "x": 100, "y": 300},
                {"type": "free_point", "id": "D", "x": 400, "y": 300},
                {"type": "line", "id": "l1", "p1": "A", "p2": "B"},
                {"type": "line", "id": "l2", "p1": "C", "p2": "D"},
            ],
        }
        bad_aux = {
            "has_aux": True, "reason": "x",
            "constructions": [{
                "type": "intersect_lines", "id": "P", "line1": "l1", "line2": "l2",
                "dashed": True, "style": "aux", "purpose": "пересечение параллельных",
                "solution_evidence": {"step_no": 1, "quote": "Построим точку пересечения"},
            }],
        }
        job = _run(app, user, monkeypatch, bad_aux,
                   "1. Построим точку пересечения прямых.", base=base_with_parallel)
        # intersect_lines параллельных -> ConstructionError -> движок не строит aux.
        assert job.aux_status == "AUX_BUILD_FAILED"
