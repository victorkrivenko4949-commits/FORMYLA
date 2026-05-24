# -*- coding: utf-8 -*-
"""
Blueprint: посадочная страница /welcome.

Холодный трафик заходит сюда → проходит бесплатный пробник (/free_mock/setup)
→ видит радар сильных/слабых сторон → план подготовки.
"""

from __future__ import annotations

from flask import Blueprint, render_template

from models import Review

welcome_bp = Blueprint('welcome', __name__, template_folder='../templates')


@welcome_bp.route('/welcome')
def welcome():
    """Лендинг.

    `landing_view` логируется на стороне JS (через /api/track) при загрузке.
    """
    reviews = (
        Review.query
        .filter_by(is_published=True)
        .order_by(Review.sort_order.asc(), Review.created_at.desc())
        .limit(20)
        .all()
    )
    return render_template('welcome.html', reviews=reviews)
