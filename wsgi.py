#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WSGI entry point for production deployment.
Used by gunicorn and other WSGI servers.

Render Start Command (set in Render Dashboard -> Settings -> Deploy):
    gunicorn wsgi:app --timeout 120 --workers 2 --max-requests 1000 --max-requests-jitter 50

Why --timeout 120:
    Default Gunicorn timeout is 30s.
    120s gives the pipeline enough headroom for long-running requests.

Why --workers 2:
    Two workers allow one to serve polling/status requests while the other
    handles long-running operations.

Why --max-requests 1000 --max-requests-jitter 50:
    Recycle workers periodically to prevent memory leaks from the LLM pipeline.
"""

from app import app

if __name__ == "__main__":
    app.run()
