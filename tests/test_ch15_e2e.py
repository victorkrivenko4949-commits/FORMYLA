# -*- coding: utf-8 -*-
"""End-to-end test for CH15 condition → solution pipeline.

Uses the exact task from the task spec (isosceles triangle, angle BAC=40°,
solution adds altitude AH).  Only the LLM calls are mocked — the real
deterministic pipeline (base draw → aux draw → audit → credit) runs.

The test verifies:
  - base SVG is built from the condition only;
  - aux SVG contains the dashed altitude from the solution;
  - has_aux=True, aux_reason present, current_stage reaches 'done';
  - credit is charged exactly once (and never refunded).
"""

import os
import sys
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


BASE_PLAN = {
    "version": 2,
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
    "assumptions": [],
}

AUX_PLAN = {
    "has_aux": True,
    "reason": "Проведём высоту AH из вершины A на сторону BC.",
    "constructions": [
        {
            "type": "altitude",
            "id": "aux_altitude_AH",
            "vertex": "A",
            "side_a": "B",
            "side_b": "C",
            "foot_id": "H",
            "dashed": True,
            "style": "aux",
            "purpose": "Высота AH, которая в равнобедренном треугольнике является биссектрисой",
            "solution_evidence": {
                "step_no": 1,
                "quote": "Проведём высоту AH из вершины A на сторону BC",
            },
        }
    ],
}

AUDIT_RESULT = {"approved": True, "issues": []}


def _make_fake_call():
    """Build a fake _call_deepseek that dispatches on the system prompt."""
    def fake(messages, model_name=None, role="base"):
        system = messages[0]["content"] if messages else ""
        if "аудитор" in system:
            content = json.dumps(AUDIT_RESULT, ensure_ascii=False)
        elif "aux-чертёж" in system:
            content = json.dumps(AUX_PLAN, ensure_ascii=False)
        else:
            content = json.dumps(BASE_PLAN, ensure_ascii=False)
        return {
            "content": content,
            "cost_usd": 0.0,
            "model": model_name or "test-model",
            "usage": {},
        }
    return fake


class TestConditionSolutionE2E:

    def test_full_pipeline(self, app, test_user, monkeypatch):
        from models import db, FigureBuildJob
        import routes.figures_generator as fg

        # Списание реально проверяется: включаем enforcement.
        monkeypatch.setattr(fg, "FIGURE_CREDITS_ENFORCED", True)
        # CH23 PART B3: legacy-планировщик сохранён за флагом — тест проверяет
        # старый однопроходный aux_planner.
        monkeypatch.setattr(fg, "FIGURE_AUX_LEGACY_PLANNER", True)

        # Ensure the user has credits so _charge_credit succeeds.
        test_user.figure_credits = 10
        db.session.commit()

        # Mock only the LLM transport.
        monkeypatch.setattr(fg, "_call_deepseek", _make_fake_call())

        job = FigureBuildJob(
            user_id=test_user.id,
            problem_text=(
                "В равнобедренном треугольнике ABC известно, что AB = AC "
                "и угол BAC равен 40°. Найдите углы ABC и ACB."
            ),
            solution_text=(
                "1. Проведём высоту AH из вершины A на сторону BC.\n"
                "2. В равнобедренном треугольнике высота, проведённая к "
                "основанию, является также биссектрисой.\n"
                "3. Поэтому угол BAH равен 20°.\n"
                "4. В прямоугольном треугольнике ABH угол ABH равен "
                "90° − 20° = 70°.\n"
                "5. Так как AB = AC, углы ABC и ACB равны. Следовательно, "
                "угол ABC равен углу ACB и равен 70°."
            ),
            generation_mode="condition_solution",
            status="queued",
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

        fg._run_condition_solution_job(job_id, job)

        job = FigureBuildJob.query.get(job_id)
        assert job.status == "done", f"expected done, got {job.status}: {job.error}"
        assert job.current_stage == "done"

        # Base SVG построен.
        assert job.svg_path is not None
        assert len(job.svg_path) > 100
        assert "<svg" in job.svg_path

        # Aux построен (высота пунктиром).
        assert job.has_aux is True
        assert job.aux_svg_path is not None
        assert "stroke-dasharray" in job.aux_svg_path  # пунктир присутствует
        assert job.aux_reason is not None

        # Планы сохранены.
        assert job.base_plan_json is not None
        assert job.aux_plan_json is not None

        # Base SVG не содержит aux-высоты (id высоты — только в aux).
        assert "aux_altitude_AH" not in job.svg_path

        # Кредит списан ровно один раз.
        assert job.credit_charged is True
        refreshed = db.session.get(FigureBuildJob, job_id)
        assert refreshed.credit_charged is True

        from models import User
        user = db.session.get(User, test_user.id)
        assert user.figure_credits == 9  # 10 - 1

    def test_altitude_without_foot_id_retries_then_draws(self, app, test_user, monkeypatch):
        """CH15.1 repair semantics: altitude без foot_id -> retry; после
        исправления с foot_id=H -> drawing permitted."""
        from models import db, FigureBuildJob
        import routes.figures_generator as fg

        monkeypatch.setattr(fg, "FIGURE_CREDITS_ENFORCED", True)
        monkeypatch.setattr(fg, "FIGURE_AUX_LEGACY_PLANNER", True)
        test_user.figure_credits = 10
        db.session.commit()

        bad_aux = {
            "has_aux": True,
            "reason": "Проведём высоту AH.",
            "constructions": [
                {
                    "type": "altitude",
                    "id": "aux_altitude_AH",
                    "vertex": "A",
                    "side_a": "B",
                    "side_b": "C",
                    "dashed": True,
                    "style": "aux",
                    "purpose": "Высота AH",
                    "solution_evidence": {
                        "step_no": 1,
                        "quote": "Проведём высоту AH из вершины A на сторону BC",
                    },
                }
            ],
        }

        call_counter = {"n": 0}

        def fake(messages, model_name=None, role="base"):
            system = messages[0]["content"] if messages else ""
            if "аудитор" in system:
                return {"content": json.dumps(AUDIT_RESULT, ensure_ascii=False),
                        "cost_usd": 0.0, "model": model_name or "test", "usage": {}}
            if "aux-чертёж" in system:
                call_counter["n"] += 1
                if call_counter["n"] == 1:
                    # Первая попытка — без foot_id (должна уйти в repair retry).
                    return {"content": json.dumps(bad_aux, ensure_ascii=False),
                            "cost_usd": 0.0, "model": model_name or "test", "usage": {}}
                # Вторая попытка — исправленный JSON с foot_id=H.
                return {"content": json.dumps(AUX_PLAN, ensure_ascii=False),
                        "cost_usd": 0.0, "model": model_name or "test", "usage": {}}
            return {"content": json.dumps(BASE_PLAN, ensure_ascii=False),
                    "cost_usd": 0.0, "model": model_name or "test", "usage": {}}

        monkeypatch.setattr(fg, "_call_deepseek", fake)

        job = FigureBuildJob(
            user_id=test_user.id,
            problem_text=(
                "В равнобедренном треугольнике ABC известно, что AB = AC "
                "и угол BAC равен 40°."
            ),
            solution_text="1. Проведём высоту AH из вершины A на сторону BC.",
            generation_mode="condition_solution",
            status="queued",
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

        fg._run_condition_solution_job(job_id, job)

        job = FigureBuildJob.query.get(job_id)
        # Aux-планировщик был вызван дважды: 1-й (bad) + repair retry.
        assert call_counter["n"] == 2
        assert job.status == "done", f"expected done, got {job.status}: {job.error}"
        assert job.has_aux is True
        assert job.aux_svg_path is not None
        assert "H" in (job.aux_plan_json or "")

    def test_altitude_without_foot_id_fails_after_retries(self, app, test_user, monkeypatch):
        """CH15.1: без foot_id и без исправления job становится failed (refund)."""
        from models import db, FigureBuildJob
        import routes.figures_generator as fg

        monkeypatch.setattr(fg, "FIGURE_CREDITS_ENFORCED", True)
        monkeypatch.setattr(fg, "FIGURE_AUX_LEGACY_PLANNER", True)
        test_user.figure_credits = 10
        db.session.commit()

        bad_aux = {
            "has_aux": True,
            "reason": "Проведём высоту AH.",
            "constructions": [
                {
                    "type": "altitude",
                    "id": "aux_altitude_AH",
                    "vertex": "A",
                    "side_a": "B",
                    "side_b": "C",
                    "dashed": True,
                    "style": "aux",
                    "purpose": "Высота AH",
                    "solution_evidence": {
                        "step_no": 1,
                        "quote": "Проведём высоту AH из вершины A на сторону BC",
                    },
                }
            ],
        }

        def fake(messages, model_name=None, role="base"):
            system = messages[0]["content"] if messages else ""
            if "аудитор" in system:
                return {"content": json.dumps(AUDIT_RESULT, ensure_ascii=False),
                        "cost_usd": 0.0, "model": model_name or "test", "usage": {}}
            if "aux-чертёж" in system:
                # Всегда плохой (без foot_id) — все MAX_AUX_RETRIES проваливаются.
                return {"content": json.dumps(bad_aux, ensure_ascii=False),
                        "cost_usd": 0.0, "model": model_name or "test", "usage": {}}
            return {"content": json.dumps(BASE_PLAN, ensure_ascii=False),
                    "cost_usd": 0.0, "model": model_name or "test", "usage": {}}

        monkeypatch.setattr(fg, "_call_deepseek", fake)

        job = FigureBuildJob(
            user_id=test_user.id,
            problem_text="В равнобедренном треугольнике ABC AB = AC, угол BAC = 40°.",
            solution_text="1. Проведём высоту AH.",
            generation_mode="condition_solution",
            status="queued",
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

        fg._run_condition_solution_job(job_id, job)

        job = FigureBuildJob.query.get(job_id)
        assert job.status == "failed", f"expected failed, got {job.status}"
        assert job.aux_svg_path is None

    def test_base_only_when_no_solution(self, app, test_user, monkeypatch):
        """Без solution_text выполняется только base-конвейер, aux нет."""
        from models import db, FigureBuildJob
        import routes.figures_generator as fg

        monkeypatch.setattr(fg, "FIGURE_CREDITS_ENFORCED", True)
        test_user.figure_credits = 10
        db.session.commit()

        monkeypatch.setattr(fg, "_call_deepseek", _make_fake_call())

        job = FigureBuildJob(
            user_id=test_user.id,
            problem_text="В треугольнике ABC угол A = 60°, угол B = 80°.",
            solution_text=None,
            generation_mode="condition_solution",
            status="queued",
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

        fg._run_condition_solution_job(job_id, job)

        job = FigureBuildJob.query.get(job_id)
        assert job.status == "done"
        assert job.svg_path is not None
        assert job.has_aux is False
        assert job.aux_svg_path is None
        assert job.credit_charged is True
