# -*- coding: utf-8 -*-
"""
FORMYLA AI Site Assistant — closed-domain helper for the FORMYLA platform.

Public entry points:
    * Blueprint: ``assistant_bp`` (registered at ``/api/assistant``).
    * Service:   :func:`assistant.service.answer`
    * KB init:   :func:`assistant.knowledge.init_db`

This package is a clean rebuild of the previous ``site_concierge`` helper.
It exposes NO general-purpose chat — every answer is grounded in the
FORMYLA knowledge base, and out-of-scope questions are refused before
any LLM call.
"""
from .routes import assistant_bp  # noqa: F401

__all__ = ["assistant_bp"]
