#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Fix script: Add retry logic to tutor_send db.session.commit() calls
to handle 'database is locked' errors from APScheduler contention.
"""

import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Replace the two db.session.commit() calls in tutor_send
# with retry-wrapped versions.
# The tutor_send function has two commits:
#   1. After saving user message ({