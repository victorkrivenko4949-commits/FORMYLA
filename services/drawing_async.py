"""
Async drawing task runner.

Provides run_drawing_async() which launches generate_drawing() in a
background thread and stores the result in an in-memory task store.

Usage in routes/drawing.py:
    from services.drawing_async import run_drawing_async, get_task_status

    task_id = run_drawing_async(problem, app_root, bypass_cache,
                                save_png_fn, log_to_db_fn)
    return jsonify({"task_id": task_id, "status": "processing"})
"""

from __future__ import annotations

import base64
import logging
import threading
import time
import uuid
from threading import Lock

logger = logging.getLogger(__name__)

# ── In-memory task store ──────────────────────────────────────────────────────
_STORE: dict = {}
_STORE_LOCK = Lock()
_TTL = 1800  # 30 minutes


def _cleanup() -> None:
    now = time.time()
    with _STORE_LOCK:
        expired = [k for k, v in _STORE.items()
                   if now - v.get("ts", 0) > _TTL]
        for k in expired:
            del _STORE[k]


def _set(task_id: str, **kw) -> None:
    with _STORE_LOCK:
        if task_id not in _STORE:
            _STORE[task_id] = {"ts": time.time()}
        _STORE[task_id].update(kw)


def get_task_status(task_id: str) -> dict | None:
    """Return a copy of the task dict, or None if not found."""
    _cleanup()
    with _STORE_LOCK:
        return dict(_STORE[task_id]) if task_id in _STORE else None


def run_drawing_async(
    problem: str,
    app_root: str,
    bypass_cache: bool,
    save_png_fn,
    log_to_db_fn,
) -> str:
    """
    Launch generate_drawing() in a daemon thread.
    Returns task_id immediately (status='processing').
    When done, task status becomes 'completed' or 'error'.
    """
    from services.drawing_service import generate_drawing
    from services.sandbox import SandboxError, SandboxRejected, SandboxTimeout
    from services.openrouter_client import OpenRouterError

    task_id = uuid.uuid4().hex
    _set(task_id, status="processing")

    def _worker():
        try:
            result = generate_drawing(
                problem,
                app_root=app_root,
                use_cache=not bypass_cache,
            )
        except (SandboxRejected, SandboxTimeout, SandboxError,
                OpenRouterError, ValueError, Exception) as exc:
            err = str(exc)
            logger.error("[drawing_async] task %s failed: %s", task_id, err)
            try:
                log_to_db_fn(problem=problem, status="error", error=err)
            except Exception:
                pass
            _set(task_id, status="error", error=err)
            return

        image_url = None
        image_abs = None
        try:
            image_url, image_abs = save_png_fn(result.image_bytes)
        except Exception as pe:
            logger.warning("[drawing_async] task %s PNG save failed: %s",
                           task_id, pe)

        status_str = "cache_hit" if result.cache_hit else "ok"
        try:
            log_to_db_fn(problem=problem, status=status_str,
                         result=result, image_path=image_abs)
        except Exception:
            pass

        image_b64 = base64.b64encode(result.image_bytes).decode("ascii")
        _set(task_id, status="completed", result={
            "image_url": image_url,
            "image_b64": image_b64,
            "data_url": "data:image/png;base64," + image_b64,
            "model": result.model,
            "cost_usd": result.cost_usd,
            "render_ms": result.render_ms,
            "cache_hit": result.cache_hit,
            "repair_iters": result.repair_iters,
            "critique_rounds": result.critique_rounds,
            "critique_accepted": result.critique_accepted,
            "critique_rejected": result.critique_rejected,
        })
        logger.info("[drawing_async] task %s completed", task_id)

    t = threading.Thread(target=_worker, daemon=True, name=f"drawing-{task_id[:8]}")
    t.start()
    return task_id
