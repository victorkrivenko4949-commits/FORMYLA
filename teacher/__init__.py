"""teacher — blueprint-пакет учительских инструментов (спринт «Конструктор листка»).

Подключение: gunicorn.conf.py::post_worker_init регистрирует teacher_bp и создаёт таблицы
(паттерн SECTION_STATS_V1). Эквивалент для app.py:
    from teacher import teacher_bp
    app.register_blueprint(teacher_bp)
"""
from flask import Blueprint

teacher_bp = Blueprint("teacher", __name__, template_folder="templates")

from teacher.worksheets import models as _worksheet_models  # noqa: E402,F401
from teacher.worksheets import api as _worksheet_api        # noqa: E402,F401
from teacher.worksheets import pages as _worksheet_pages    # noqa: E402,F401

__all__ = ["teacher_bp"]
