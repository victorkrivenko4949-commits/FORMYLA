"""teacher — blueprint-пакет учительских инструментов (спринты «Конструктор листка» и «Ведомость»).

Подключение: gunicorn.conf.py::post_worker_init регистрирует teacher_bp и создаёт таблицы.
Эквивалент для app.py:
    from teacher import teacher_bp
    app.register_blueprint(teacher_bp)
"""
from flask import Blueprint

teacher_bp = Blueprint("teacher", __name__, template_folder="templates")

from teacher.worksheets import models as _worksheet_models  # noqa: E402,F401
from teacher.worksheets import api as _worksheet_api        # noqa: E402,F401
from teacher.worksheets import pages as _worksheet_pages    # noqa: E402,F401
from teacher.worksheets import pdf as _worksheet_pdf        # noqa: E402,F401
from teacher.worksheets import student as _worksheet_student  # noqa: E402,F401
from teacher.worksheets import marks as _worksheet_marks      # noqa: E402,F401

__all__ = ["teacher_bp"]
