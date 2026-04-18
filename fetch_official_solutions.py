# -*- coding: utf-8 -*-
"""
Скрипт для получения НАСТОЯЩИХ АВТОРСКИХ решений олимпиадных задач
Использует DeepSeek с доступом к интернету для поиска решений на problems.ru, mccme.ru, olympiads.biz
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from olympiads import OLYMPIADS_DB
from ai{