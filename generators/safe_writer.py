#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SafeJSONWriter - Graceful Shutdown Support
Ensures valid JSON output even when process is interrupted.
"""

import json
import signal
import sys
import atexit
from typing import List, Dict, Optional, TextIO


class SafeJSONWriter:
    """
    Безопасная запись JSON с graceful shutdown.
    Гарантирует валидность JSON даже при прерывании процесса (SIGTERM/SIGINT).
    """
    
    def __init__(self, filepath: str):
        """
        Args:
            filepath: Путь к выходному JSON-файлу
        """
        self.filepath = filepath
        self.file: Optional[TextIO] = None
        self.tasks_written = 0
        self.is_closed = False
        
        # Регистрация обработчиков сигналов для graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        atexit.register(self._cleanup)
        
        print(f"📝 SafeJSONWriter initialized: {filepath}")
        
    def open(self):
        """Открывает файл и пишет начало JSON-массива."""
        self.file = open(self.filepath, 'w', encoding='utf-8')
        self.file.write('[\n')
        self.file.flush()
        print(f"✅ JSON file opened: {self.filepath}")
        
    def write_task(self, task: Dict):
        """
        Записывает одну задачу в JSON.
        Автоматически добавляет запятую между элементами.
        
        Args:
            task: Словарь с данными задачи
        """
        if self.is_closed:
            raise RuntimeError("Writer is closed")
            
        if not self.file:
            raise RuntimeError("Writer not opened. Call open() first.")
            
        # Добавляем запятую перед всеми элементами кроме первого
        if self.tasks_written > 0:
            self.file.write(',\n')
        
        # Записываем задачу с отступами
        json.dump(task, self.file, ensure_ascii=False, indent=2)
        self.file.flush()  # Немедленная запись на диск (защита от потери данных)
        self.tasks_written += 1
        
    def write_batch(self, tasks: List[Dict]):
        """
        Записывает батч задач.
        
        Args:
            tasks: Список задач для записи
        """
        for task in tasks:
            self.write_task(task)
        print(f"💾 Batch written: {len(tasks)} tasks (total: {self.tasks_written})")
            
    def close(self):
        """Закрывает JSON-массив и файл."""
        if not self.is_closed and self.file:
            self.file.write('\n]')
            self.file.flush()
            self.file.close()
            self.is_closed = True
            print(f"✅ JSON file closed gracefully. Total tasks written: {self.tasks_written}")
            
    def _signal_handler(self, signum, frame):
        """
        Обработчик сигналов SIGTERM/SIGINT.
        Обеспечивает graceful shutdown при Ctrl+C или kill.
        """
        print(f"\n⚠️  Received signal {signum}. Closing JSON gracefully...")
        self.close()
        sys.exit(0)
        
    def _cleanup(self):
        """
        Вызывается при выходе из программы (atexit).
        Гарантирует закрытие файла даже при неожиданном завершении.
        """
        if not self.is_closed:
            print("\n🔧 atexit cleanup: closing JSON file...")
            self.close()
