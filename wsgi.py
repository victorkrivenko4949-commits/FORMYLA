#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WSGI entry point for production deployment.
Used by gunicorn and other WSGI servers.
"""

from app import app

if __name__ == "__main__":
    app.run()
