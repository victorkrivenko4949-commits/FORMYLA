#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Догенерация задач по Логике для 6 класса (79 → 90)
"""

import asyncio
import aiohttp
import json
import os
import sys
import time
import re
from dotenv import load_dotenv

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
API_URL = "https://api.deepseek.com/v1/chat/completions"
OUTPUT_FILE = "grade6_logic_extra.jsonl"
MAX_WORKERS = 15
LOCK = asyncio.Lock()
stats = {"success": 0, "failed": 0}

TOPIC = "Логика (рыцари и лжецы, логические таблицы)"
TARGET = 15  # Генерируем с запасом (нужно 11, берем 15)

LEVELS_NEEDED = {1: 2, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 3}  # 15 задач


def fix_latex(text: str) -> str:
    cmds = ['overline', 'sqrt', 'frac', 'geq', 'leq', 'neq', 'cdot',
            'times', 'div', 'text', 'mathrm', 'left', 'right', 'ldots',
            'p