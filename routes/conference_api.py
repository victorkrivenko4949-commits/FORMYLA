# FORMYLA — Conference HTTP API blueprint.
#
# Provides REST endpoints for the conference page:
#   POST /api/conference/create-room  — generate a 6-digit room code
#
# NOTE: The room is NOT pre-created here. The first participant who joins
# via WebSocket (wb_ws.py on_join) will create the room and become host.
# This avoids the mismatch between create_room() signatures.

from flask import Blueprint, jsonify, request, current_app
import random
import string

conference_api_bp = Blueprint("conference_api", __name__)


def _generate_room_code():
    """Generate a 6-digit numeric room code."""
    return "".join(random.choices(string.digits, k=6))


@conference_api_bp.route("/api/conference/create-room", methods=["POST"])
def create_room():
    """Generate a new conference room code.

    The room is created lazily when the first participant joins via WebSocket.
    Returns a 6-digit numeric code that the client uses to join.
    """
    code = _generate_room_code()
    current_app.logger.info("[CONF] Room code generated: %s", code)
    return jsonify({"room": code})
