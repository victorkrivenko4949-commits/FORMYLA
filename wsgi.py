#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WSGI entry point for production deployment.
Used by gunicorn and other WSGI servers.

Render Start Command (set in Render Dashboard -> Settings -> Deploy):
    gunicorn wsgi:app --timeout 120 --workers 2 --max-requests 1000 --max-requests-jitter 50

Why --timeout 120:
    /api/drawing/generate runs a 1-3 minute LLM pipeline.
    Default Gunicorn timeout is 30s, which kills the worker mid-request (SIGKILL).
    120s gives the pipeline enough headroom.

Why --workers 2:
    Two workers allow one to serve polling/status requests while the other
    runs the long drawing pipeline.

Why --max-requests 1000 --max-requests-jitter 50:
    Recycle workers periodically to prevent memory leaks from the LLM pipeline.
"""

from app import app

if __name__ == "__main__":
    app.run()
