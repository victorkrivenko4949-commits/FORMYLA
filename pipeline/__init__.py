# -*- coding: utf-8 -*-
"""
Pipeline: генерация олимпиадных задач для Адаптивного теста FORMYLA.

Архитектура: 3 нейросети через OpenRouter
  Generator (deepseek/deepseek-chat)  → генерация задачи
  Validator (anthropic/claude-sonnet-4) → проверка корректности
  Calibrator (openai/gpt-4o)          → калибровка уровня

Управляющий цикл: до 4 итераций с feedback-петлёй.
"""
