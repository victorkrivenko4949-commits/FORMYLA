from datetime import date

from flask import Blueprint, abort, current_app, jsonify, make_response, render_template, request
from flask_login import current_user, login_required
from sqlalchemy.exc import SQLAlchemyError

from models import db
from .service import collect_metrics

bp = Blueprint("admin_metrics", __name__, template_folder="../templates")


@bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@bp.route("/admin/metrics")
@bp.route("/admin/metrics.json", endpoint="metrics_json")
@login_required
def metrics():
    if getattr(current_user, "is_admin", False) is not True:
        abort(403)
    try:
        day = date.fromisoformat(request.args["date"]) if request.args.get("date") else None
        days = int(request.args.get("days", "7"))
        result = collect_metrics(db.engine, day=day, days=days)
    except (ValueError, OverflowError):
        return jsonify(error="Нужна существующая дата не в будущем (YYYY-MM-DD) и days от 1 до 31."), 400
    except SQLAlchemyError:
        # Do not echo exception SQL or connection details to the browser.
        current_app.logger.warning("Admin metrics database query failed")
        return jsonify(error="Метрики временно недоступны. Проверьте состояние БД."), 503
    if request.path.endswith(".json"):
        return jsonify(result)
    return make_response(render_template("admin_metrics.html", metrics=result, days=days))
