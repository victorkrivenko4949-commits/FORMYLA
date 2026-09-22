"""Concrete Flask-Login + FORMYLA CSRF integration, disabled unless opted in."""
import os

from flask import Blueprint, abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from .jobs import Queue, QueueFull, make_engine

bp = Blueprint("geoexact", __name__, url_prefix="/geometry/draw",
               template_folder="templates", static_folder="static")


def init_app(app):
    if os.environ.get("GEOEXACT_ENABLED", "0") != "1":
        return
    if "geoexact" in app.extensions:
        return
    url = app.config.get("SQLALCHEMY_DATABASE_URI") or os.environ.get("DATABASE_URL")
    if not url or not url.startswith(("postgres", "postgresql")):
        raise RuntimeError("GeoExact production queue requires PostgreSQL")
    app.extensions["geoexact"] = Queue(
        make_engine(url),
        per_hour=os.environ.get("GEOEXACT_PER_HOUR", "3"),
        per_day=os.environ.get("GEOEXACT_PER_DAY", "10"),
        daily_usd=os.environ.get("GEOEXACT_DAILY_USD", "5.00"),
        queue_size=os.environ.get("GEOEXACT_QUEUE_SIZE", "8"),
    )
    app.register_blueprint(bp)


@bp.before_request
def guard():
    if (not current_user.is_authenticated or getattr(current_user, "is_guest", False)) and request.endpoint != "geoexact.static":
        return jsonify(error="Войдите в аккаунт."), 401
    if request.endpoint != "geoexact.static":
        current_app.extensions["geoexact"].ensure_started()


@bp.after_request
def private(response):
    if request.endpoint != "geoexact.static":
        response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.get("/")
@login_required
def page():
    from services.security import get_csrf_token
    return render_template("geoexact_draw.html", geoexact_csrf=get_csrf_token())


@bp.post("/jobs")
@login_required
def submit():
    from services.security import validate_csrf
    if not validate_csrf(request.headers.get("X-CSRF-Token", "")):
        return jsonify(error="Обновите страницу и повторите запрос."), 403
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return jsonify(error="Генератор ещё не настроен."), 503
    # Read at most 64 KiB even for requests with missing Content-Length.
    if request.content_length is not None and request.content_length > 65536:
        return jsonify(error="Слишком большой запрос."), 413
    if not request.is_json:
        return jsonify(error="Требуется JSON."), 400
    raw = request.stream.read(65537)
    if len(raw) > 65536:
        return jsonify(error="Слишком большой запрос."), 413
    import json
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        return jsonify(error="Некорректный JSON."), 400
    if not isinstance(data, dict) or not isinstance(data.get("problem"), str):
        return jsonify(error="Введите условие задачи."), 400
    text = data["problem"].strip()
    try:
        text.encode("utf-8")
    except UnicodeError:
        return jsonify(error="Некорректный текст."), 400
    if not 10 <= len(text) <= 12000 or type(data.get("with_aux", False)) is not bool:
        return jsonify(error="Нужно от 10 до 12 000 символов и корректный режим."), 400
    try:
        jid = current_app.extensions["geoexact"].submit(
            str(current_user.get_id()), text, data.get("with_aux", False))
    except QueueFull as e:
        return jsonify(error=str(e)), 429
    return jsonify(job_id=jid, status="queued"), 202


@bp.get("/jobs/<jid>")
@login_required
def status(jid):
    result = current_app.extensions["geoexact"].get(jid, str(current_user.get_id()))
    if result is None:
        abort(404)
    return jsonify(result)


@bp.get("/active")
@login_required
def active():
    from sqlalchemy import select
    from .jobs import jobs
    queue = current_app.extensions["geoexact"]
    with queue.engine.connect() as c:
        row = c.execute(select(jobs.c.id).where(
            jobs.c.owner == str(current_user.get_id()),
            jobs.c.status.in_(["queued", "running"])
        ).order_by(jobs.c.created.desc()).limit(1)).first()
    return jsonify(job_id=row.id if row else None)
