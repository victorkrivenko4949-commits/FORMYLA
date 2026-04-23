#!/usr/bin/env python3
# Generator for routes/friends.py
# Avoids tool truncation issues by building content programmatically

import os

os.makedirs('routes', exist_ok=True)

code = '''# -*- coding: utf-8 -*-
"""Friendship routes for FORMYLA - bidirectional friend system"""
from flask import Blueprint, jsonify, render_template, abort
from flask_login import login_required, current_user
from models import db, User, Friendship, Notification
import json, logging

logger = logging.getLogger(__name__)
friends_bp = Blueprint("friends", __name__)


def _notif(uid, ntype, sender_id, data=None):
    """Create notification helper."""
    n = Notification(
        user_id=uid,
        type=ntype,
        from_user_id=sender_id,
        data=json