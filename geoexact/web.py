"""Concrete Flask-Login + FORMYLA CSRF integration, disabled unless opted in."""
import os
import time

from flask import Blueprint, abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from .jobs import Queue, QueueFull, init_db, make_engine

bp = Blueprint("geoexact", __name__, url_prefix="/geometry/draw",
               template_folder="templates", static_folder="static")

# In-memory rate-limit для распознавания фото: ≤ 20 фото/час на пользователя.
_PHOTO_RATE_LIMIT = {}

# Vision-модели, для которых провайдер не принял параметр thinking
# (HTTP 400 с упоминанием «thinking») — повтор идёт без параметра.
_VISION_THINKING_UNSUPPORTED: set[str] = set()

# Промпт распознавания: полный текст условия, формулы в LaTeX.
# В конвейер уходит эта версия, а пользователь видит её без LaTeX
# (преобразование на клиенте).
_VISION_PROMPT = (
    "Это фотография геометрической задачи. Верни полный текст условия "
    "задачи так, как он написан, на языке оригинала. Формулы переведи "
    "в LaTeX (например \\frac{3}{4}, \\angle ABC, 90^\\circ). "
    "Без пояснений и без markdown — только текст условия."
)


def init_app(app):
    if os.environ.get("GEOEXACT_ENABLED", "0") != "1":
        return
    if "geoexact" in app.extensions:
        return
    url = app.config.get("SQLALCHEMY_DATABASE_URI") or os.environ.get("DATABASE_URL")
    if not url or not url.startswith(("postgres", "postgresql")):
        raise RuntimeError("GeoExact production queue requires PostgreSQL")
    engine = make_engine(url)
    # AUTO-INIT: таблицы geoexact_jobs_v1/geoexact_mutex_v1 создаются
    # автоматически при первом старте (create_all идемпотентен),
    # иначе любой запрос падает с 500 если забыть manage init-db.
    init_db(engine)
    app.extensions["geoexact"] = Queue(
        engine,
        per_hour=os.environ.get("GEOEXACT_PER_HOUR", "0"),
        per_day=os.environ.get("GEOEXACT_PER_DAY", "0"),
        daily_usd=os.environ.get("GEOEXACT_DAILY_USD", "0"),
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


@bp.post("/recognize-photo")
@login_required
def recognize_photo():
    """Распознать текст условия с фото.

    Основной распознаватель — DeepSeek vision (DEEPSEEK_VISION_MODEL),
    резерв — локальный Tesseract OCR. Тот же пайплайн, что и у проверки
    фото-решений. Формулы возвращаются в LaTeX: конвейер получает полную
    версию, клиент показывает пользователю её же без LaTeX.
    """
    from services.security import validate_csrf
    if not validate_csrf(request.headers.get("X-CSRF-Token", "")):
        return jsonify(error="Обновите страницу и повторите запрос."), 403

    # Rate-limit: ≤ 20 фото/час на пользователя (in-memory).
    rl_key = f"gx-photo:{current_user.get_id()}"
    now = time.time()
    bucket = _PHOTO_RATE_LIMIT.setdefault(rl_key, [])
    bucket[:] = [t for t in bucket if now - t < 3600]
    if len(bucket) >= 20:
        return jsonify(error="Слишком много фото за час, попробуйте позже."), 429
    bucket.append(now)

    if not os.environ.get("DEEPSEEK_API_KEY"):
        return jsonify(error="Распознавание ещё не настроено."), 503
    if request.content_length is not None and request.content_length > 12 * 1024 * 1024:
        return jsonify(error="Фото слишком большое."), 413
    data = request.get_json(silent=True) or {}
    img_b64 = (data.get("image") or "").strip()
    mime = data.get("mime") or "image/jpeg"
    if not img_b64:
        return jsonify(error="Нет фото."), 400
    import base64
    try:
        raw_bytes = base64.b64decode(img_b64)
    except Exception:
        return jsonify(error="Некорректное фото."), 400
    if len(raw_bytes) > 10 * 1024 * 1024:
        return jsonify(error="Фото слишком большое."), 413

    # ── Шаг 1: DeepSeek vision (основной распознаватель) ────────────────
    try:
        import requests as _rq
        model = os.getenv("DEEPSEEK_VISION_MODEL",
                           "deepseek-v4-flash-vision-exp").strip()
        # GEOEXACT_THINKING_FIX (см. geoexact/core/llm.py): без отключения
        # «думания» vision-модель рассуждает перед ответом десятки секунд,
        # а при исчерпании 60-секундного таймаута запрос молча уходит в
        # резервный Tesseract — отсюда «Распознаём фото…» на минуты.
        # Отключаем тем же параметром, что уже работает в проде
        # (services/llm_router.py); max_tokens 2048: текст условия короткий,
        # а большой лимит лишь даёт разгон «размышлениям».
        payload = {"model": model, "max_tokens": 2048, "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": _VISION_PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
            ]},
        ]}
        headers = {"Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"],
                    "Content-Type": "application/json"}
        if model not in _VISION_THINKING_UNSUPPORTED:
            payload["thinking"] = {"type": "disabled"}
        r = _rq.post("https://api.deepseek.com/v1/chat/completions",
                     headers=headers, json=payload, timeout=(15, 60))
        if r.status_code == 400 and model not in _VISION_THINKING_UNSUPPORTED \
                and "thinking" in (r.text or "").lower():
            # Провайдер не знает параметр thinking — повторяем без него.
            _VISION_THINKING_UNSUPPORTED.add(model)
            payload.pop("thinking", None)
            r = _rq.post("https://api.deepseek.com/v1/chat/completions",
                         headers=headers, json=payload, timeout=(15, 60))
        if r.status_code == 200:
            body = r.json()
            if body.get("choices"):
                text = (body["choices"][0].get("message", {}) or {}).get("content") or ""
                if text.strip():
                    return jsonify(text=text.strip(), engine="deepseek_vision")
    except Exception:
        pass

    # ── Шаг 2: локальный Tesseract OCR (резерв) ────────────────────
    try:
        from services.tesseract_ocr import recognize_bytes as _tesseract_ocr
        text, _err = _tesseract_ocr(raw_bytes, mime)
        if text and text.strip():
            return jsonify(text=text.strip(), engine="tesseract")
    except Exception:
        pass

    return jsonify(error="Не удалось распознать фото."), 422
