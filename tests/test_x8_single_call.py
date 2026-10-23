# -*- coding: utf-8 -*-
"""X8 acceptance test: single API call for a pair of drawings.

The generator in routes/figures_generator.py uses _call_deepseek exactly
once per job (the aux data is extracted from the same JSON response).
This test monkeypatches _call_deepseek and asserts call_count == 1.
"""

import pytest


def test_single_api_call_for_pair(app, monkeypatch):
    """Monkeypatch _call_deepseek and assert one call when running a job.

    The 'app' fixture provides the Flask app context needed for DB access.
    """
    call_count = [0]

    def fake_call(messages):
        call_count[0] += 1
        return {
            "content": (
                '{"canvas":{"width":600,"height":500,"margin":40},'
                '"constructions":['
                '{"type":"free_point","id":"A","x":100,"y":400},'
                '{"type":"free_point","id":"B","x":500,"y":400},'
                '{"type":"free_point","id":"C","x":300,"y":80},'
                '{"type":"triangle_arbitrary","id":"tri","p1":"A","p2":"B","p3":"C"}],'
                '"aux":{"has_aux":true,"reason":"Perpendicular CH dropped",'
                '"constructions":['
                '{"type":"foot_perpendicular","id":"H","p1":"C","line1":"l_AB"},'
                '{"type":"segment","id":"CH","p1":"C","p2":"H","dashed":true}]}}'
            ),
            "cost_usd": 0.0,
        }

    import routes.figures_generator as gen
    monkeypatch.setattr(gen, '_call_deepseek', fake_call)

    from models import db, FigureBuildJob
    from datetime import datetime

    job = FigureBuildJob(
        user_id=1,
        problem_text='[TEST] geometry task with aux',
        status='queued',
        model_name='test-model',
        credit_charged=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()
    job_id = job.id

    try:
        gen._run_build_job(job_id)
    except Exception:
        pass

    assert call_count[0] == 1, (
        f"Expected 1 API call, got {call_count[0]}"
    )
