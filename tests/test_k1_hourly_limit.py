# -*- coding: utf-8 -*-
"""K1: Test hourly rate limit (10 builds per hour).

Uses F0 fixtures (app, auth_client).
"""


def test_hourly_limit_11th_request(app, auth_client):
    """Create 10 jobs in the last hour, then the 11th gets 429."""
    import json
    from models import db, FigureBuildJob
    from datetime import datetime, timedelta

    # Register the figures_gen blueprint to enable the /start route
    from routes.figures_generator import figures_gen_bp
    app.register_blueprint(figures_gen_bp)

    # Create 10 jobs that were created within the last hour
    for i in range(10):
        job = FigureBuildJob(
            user_id=1,
            problem_text=f'[TEST K1] rate limit test problem {i}',
            status='done',
            model_name='test-model',
            credit_charged=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(job)
    db.session.commit()

    # The 11th request should be blocked
    resp = auth_client.post(
        '/figures/generate/start',
        data=json.dumps({
            'problem_text': '[TEST K1] 11th problem — should be blocked',
        }),
        content_type='application/json',
    )

    print(f"STATUS: {resp.status_code}")
    print(f"BODY: {resp.data.decode('utf-8')[:500]}")

    assert resp.status_code != 500, (
        f"Expected non-500 status for rate-limited request, "
        f"got {resp.status_code}"
    )
    assert resp.status_code in (429, 400), (
        f"Expected 429 or 400, got {resp.status_code}"
    )

    body = resp.get_json() or {}
    error_msg = body.get('error', '')
    assert error_msg, f"Expected non-empty error message, got: {body}"
    assert any(word in error_msg.lower() for word in ['много', 'лимит', 'попробуйте', 'limit']), (
        f"Expected Russian error text about limit, got: {error_msg}"
    )
