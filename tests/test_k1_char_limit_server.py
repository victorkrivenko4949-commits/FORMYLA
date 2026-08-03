# -*- coding: utf-8 -*-
"""K1: Test server-side char limit (4000 chars).

Sends a request with >4000 characters directly via test_client,
bypassing HTML/JS client-side validation.
"""


def test_char_limit_server_side(app, auth_client):
    """Request with 4001 chars is rejected, not silently truncated."""
    import json

    from routes.figures_generator import figures_gen_bp
    app.register_blueprint(figures_gen_bp)

    long_text = 'A' * 4001

    resp = auth_client.post(
        '/figures/generate/start',
        data=json.dumps({'problem_text': long_text}),
        content_type='application/json',
    )

    print(f"STATUS: {resp.status_code}")
    print(f"BODY: {resp.data.decode('utf-8')[:500]}")

    assert resp.status_code != 500, (
        f"Expected non-500 status for too-long text, got {resp.status_code}"
    )

    body = resp.get_json() or {}
    error_msg = body.get('error', '')

    assert error_msg, f"Expected error message, got empty body: {resp.data.decode('utf-8')[:200]}"
    assert 'длинн' in error_msg.lower() or 'символ' in error_msg.lower() or 'максимум' in error_msg.lower(), (
        f"Expected Russian text about length limit, got: {error_msg}"
    )

    # Verify no job was created in the database
    from models import FigureBuildJob
    jobs = FigureBuildJob.query.filter_by(
        problem_text=long_text,
    ).all()
    assert len(jobs) == 0, (
        f"Job was created despite text being too long! Found {len(jobs)} jobs."
    )
    print("OK: No job created for >4000 char text, server rejected with message")
