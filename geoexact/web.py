"""Concrete Flask-Login + FORMYLA CSRF integration, disabled unless opted in."""
import os
import re
import time

from flask import Blueprint, abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required

from .jobs import Queue, QueueFull, clean_history, init_db, make_engine

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
    "Без пояснений и без markdown — только текст условия. Если на фото "
    "нет текста задачи или он нечитаем — ответь одним словом: UNREADABLE."
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
    history = None
    retry_of = data.get("retry_of")
    if retry_of is not None:
        # «Another construction»: continue the expert chat of the user's own earlier job.
        if not isinstance(retry_of, str) or not re.fullmatch(r"[0-9a-f]{32}", retry_of) \
                or not data.get("with_aux", False):
            return jsonify(error="Некорректный повторный запрос."), 400
        earlier = current_app.extensions["geoexact"].get(retry_of, str(current_user.get_id()))
        history = ((earlier or {}).get("result") or {}).get("expert_history")
        history = clean_history(history)      # None: the expert had not answered, ask afresh
    try:
        jid = current_app.extensions["geoexact"].submit(
            str(current_user.get_id()), text, data.get("with_aux", False), history)
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


@bp.post("/solution")
@login_required
def solution():
    """«Полное решение»: тот же диалог с экспертом (Луна) продолжается
    просьбой решить задачу; DeepSeek оформляет ответ в LaTeX."""
    from services.security import validate_csrf
    if not validate_csrf(request.headers.get("X-CSRF-Token", "")):
        return jsonify(error="Обновите страницу и повторите запрос."), 403
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return jsonify(error="Генератор ещё не настроен."), 503
    if not request.is_json:
        return jsonify(error="Требуется JSON."), 400
    data = request.get_json(silent=True) or {}
    jid = data.get("job_id")
    if not isinstance(jid, str) or not re.fullmatch(r"[0-9a-f]{32}", jid):
        return jsonify(error="Некорректный запрос решения."), 400
    earlier = current_app.extensions["geoexact"].get(jid, str(current_user.get_id()))
    if not earlier or earlier.get("status") != "done":
        return jsonify(error="Сначала постройте чертёж."), 404
    result = earlier.get("result") or {}
    if not result.get("ok") or result.get("kind") == "solution":
        return jsonify(error="Сначала постройте чертёж."), 404
    problem = result.get("problem_text")
    if not isinstance(problem, str) or not problem.strip():
        return jsonify(error="У задания не сохранилось условие."), 404
    history = clean_history(result.get("expert_history"))
    try:
        jid = current_app.extensions["geoexact"].submit_solution(
            str(current_user.get_id()), problem, history)
    except QueueFull as e:
        return jsonify(error=str(e)), 429
    return jsonify(job_id=jid, status="queued"), 202


@bp.get("/last")
@login_required
def last():
    return jsonify(job_id=current_app.extensions["geoexact"].last_done(str(current_user.get_id())))


@bp.get("/active")
@login_required
def active():
    """Незавершённое задание пользователя + его возраст по часам сервера.

    Задание живёт в БД и выполняется сервером независимо от страницы:
    смена раздела не прерывает генерацию. age_sec и problem_head нужны
    фронтенду, чтобы после возврата в раздел показать честный таймер
    («уже строится N секунд»), а не «часы с нуля», которые выглядели как
    перезапуск генерации.
    """
    from sqlalchemy import select
    from .jobs import jobs
    queue = current_app.extensions["geoexact"]
    with queue.engine.connect() as c:
        row = c.execute(select(
            jobs.c.id, jobs.c.created, jobs.c.with_aux, jobs.c.problem
        ).where(
            jobs.c.owner == str(current_user.get_id()),
            jobs.c.status.in_(["queued", "running"])
        ).order_by(jobs.c.created.desc()).limit(1)).first()
    if not row:
        return jsonify(job_id=None)
    # Служебные обёртки (история эксперта / задание «решение») не показываем.
    problem = row.problem or ""
    head = "" if problem.startswith("\x1e") else problem[:80]
    return jsonify(job_id=row.id,
                   age_sec=round(time.time() - row.created, 1),
                   with_aux=int(row.with_aux or 0), problem_head=head)


def _vision_request(url, key, model, mime, img_b64, *, thinking_off=False,
                    max_tokens=2048, timeout=(15, 60)):
    """Один OpenAI-совместимый vision-запрос с _VISION_PROMPT.

    Возвращает (text, None) при успехе или (None, причина) при отказе —
    причина уходит в лог, чтобы «Не удалось распознать фото» больше не
    было немым (раньше все исключения глушились except: pass).
    """
    import requests as _rq
    payload = {"model": model, "max_tokens": max_tokens, "temperature": 0.1,
               "messages": [
                   {"role": "user", "content": [
                       {"type": "text", "text": _VISION_PROMPT},
                       {"type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                   ]},
               ]}
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    if "openrouter.ai" in url:
        headers["HTTP-Referer"] = os.environ.get("DOMAIN_URL", "https://formyla.net")
        headers["X-Title"] = "FORMYLA.net GeoExact OCR"
    # GEOEXACT_THINKING_FIX (см. geoexact/core/llm.py): без отключения
    # «думания» vision-модель DeepSeek рассуждает десятки секунд и упирается
    # в таймаут. При HTTP 400 с упоминанием thinking — повтор без параметра.
    if thinking_off and model not in _VISION_THINKING_UNSUPPORTED:
        payload["thinking"] = {"type": "disabled"}
    try:
        r = _rq.post(url, headers=headers, json=payload, timeout=timeout)
        if r.status_code == 400 and "thinking" in payload \
                and "thinking" in (r.text or "").lower():
            _VISION_THINKING_UNSUPPORTED.add(model)
            payload.pop("thinking", None)
            r = _rq.post(url, headers=headers, json=payload, timeout=timeout)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}: {(r.text or '')[:200]}"
        body = r.json()
        if not body.get("choices"):
            return None, "empty choices"
        text = ((body["choices"][0].get("message", {}) or {}).get("content") or "").strip()
        if not text:
            return None, "empty content"
        if text.upper().startswith("UNREADABLE"):
            return None, "UNREADABLE"
        return text, None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:200]}"


@bp.post("/recognize-photo")
@login_required
def recognize_photo():
    """Распознать текст условия с фото.

    Цепочка движков — как в services/solution_ocr.py (фото-решения):
    DeepSeek vision (DEEPSEEK_VISION_MODEL) → Gemini через OpenRouter
    (OCR_OPENROUTER_MODEL) → Gemini через OdiRouter (GEMINI_VISION_MODEL)
    → локальный Tesseract OCR. Каждый отказ пишется в лог с причиной.
    Формулы возвращаются в LaTeX: конвейер получает полную версию,
    клиент показывает пользователю её же без LaTeX.
    """
    from services.security import validate_csrf
    if not validate_csrf(request.headers.get("X-CSRF-Token", "")):
        return jsonify(error="Обновите страницу и повторите запрос."), 403

    ds_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    or_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    gm_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not (ds_key or or_key or gm_key):
        return jsonify(error="Распознавание ещё не настроено."), 503

    # Rate-limit: ≤ 20 фото/час на пользователя (in-memory).
    rl_key = f"gx-photo:{current_user.get_id()}"
    now = time.time()
    bucket = _PHOTO_RATE_LIMIT.setdefault(rl_key, [])
    bucket[:] = [t for t in bucket if now - t < 3600]
    if len(bucket) >= 20:
        return jsonify(error="Слишком много фото за час, попробуйте позже."), 429
    bucket.append(now)

    def _fail(status, msg, **extra):
        # Неудачная попытка не списывается из лимита.
        try:
            bucket.remove(now)
        except ValueError:
            pass
        return jsonify(error=msg, **extra), status

    if request.content_length is not None and request.content_length > 12 * 1024 * 1024:
        return _fail(413, "Фото слишком большое.")
    data = request.get_json(silent=True) or {}
    img_b64 = (data.get("image") or "").strip()
    if img_b64.startswith("data:"):
        img_b64 = img_b64.split(",", 1)[-1]
    mime = data.get("mime") or "image/jpeg"
    if not img_b64:
        return _fail(400, "Нет фото.")
    import base64
    try:
        raw_bytes = base64.b64decode(img_b64)
    except Exception:
        return _fail(400, "Некорректное фото.")
    if len(raw_bytes) > 10 * 1024 * 1024:
        return _fail(413, "Фото слишком большое.")

    log = current_app.logger
    errors = []

    # ── Шаг 1: DeepSeek vision (основной распознаватель) ────────────────
    if ds_key:
        model = os.getenv("DEEPSEEK_VISION_MODEL",
                          "deepseek-v4-flash-vision-exp").strip()
        text, err = _vision_request("https://api.deepseek.com/v1/chat/completions",
                                    ds_key, model, mime, img_b64, thinking_off=True)
        if text:
            return jsonify(text=text, engine="deepseek_vision")
        errors.append(f"deepseek {model}: {err}")
        log.warning("[geoexact photo] deepseek vision %s failed: %s", model, err)

    # ── Шаг 2: Gemini flash через OpenRouter (резерв) ───────────────────
    if or_key:
        env_models = [m.strip() for m in
                      (os.environ.get("OCR_OPENROUTER_MODEL", "") or "").split(",") if m.strip()]
        for model in env_models or ["google/gemini-3-flash-preview",
                                    "google/gemini-3.7-flash",
                                    "google/gemini-2.5-flash"]:
            text, err = _vision_request("https://openrouter.ai/api/v1/chat/completions",
                                        or_key, model, mime, img_b64, timeout=(15, 50))
            if text:
                return jsonify(text=text, engine="openrouter_gemini")
            errors.append(f"openrouter {model}: {err}")
            log.warning("[geoexact photo] openrouter %s failed: %s", model, err)
            if err == "UNREADABLE":
                break

    # ── Шаг 3: Gemini через OdiRouter (резерв) ──────────────────────────
    if gm_key:
        base = (os.environ.get("GEMINI_API_BASE") or "https://api.odirouter.ai/v1").strip().rstrip("/")
        env_model = (os.environ.get("GEMINI_VISION_MODEL") or "").strip()
        for model in ([env_model] if env_model else ["gemini-3.8-flash", "gemini-3.7-flash"]):
            text, err = _vision_request(f"{base}/chat/completions",
                                        gm_key, model, mime, img_b64)
            if text:
                return jsonify(text=text, engine="gemini_vision")
            errors.append(f"odirouter {model}: {err}")
            log.warning("[geoexact photo] odirouter %s failed: %s", model, err)
            if err == "UNREADABLE":
                break

    # ── Шаг 4: локальный Tesseract OCR (резерв) ─────────────────────────
    try:
        from services.tesseract_ocr import recognize_bytes as _tesseract_ocr
        text, _err = _tesseract_ocr(raw_bytes, mime)
        if text and text.strip():
            return jsonify(text=text.strip(), engine="tesseract")
        errors.append(f"tesseract: {_err}")
    except Exception as e:
        errors.append(f"tesseract: {type(e).__name__}: {str(e)[:200]}")

    log.error("[geoexact photo] all engines failed for user %s: %s",
              current_user.get_id(), " | ".join(errors))
    return _fail(422, "Не удалось распознать фото.",
                 detail=(errors[-1][:200] if errors else None))
