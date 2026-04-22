"""
Тестовый скрипт для генерации ОДНОЙ задачи
Проверяем работу API с задержками и retry logic
"""

import requests
import json
import time
import re
import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not DEEPSEEK_API_KEY:
    raise ValueError("DEEPSEEK_API_KEY не найден в .env файле!")

API_URL = "https://api.deepseek.com/v1/chat/completions"

def{