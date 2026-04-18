"""
Упрощенная система предгенерации задач для Free Mock
Работает с текущей архитектурой фронтенда
"""
import threading
from typing import Dict, Optional
from datetime import datetime

# Простое хранилище: session_id -> список готовых задач
TASK_CACHE: Dict[str, list] = {}
CACHE_LOCK = threading.Lock()

def get_cached_task(session_id: str) -> Optional[dict]:
    """Получить готовую задачу из кэша"""
    with CACHE_LOCK:
        if session_id in TASK_CACHE and TASK_CACHE[session_id]:
            task = TASK_CACHE[session_id].pop(0)
            print(f"[Prefetch] ⚡ Мгновенная отдача задачи из кэша. Осталось: {len(TASK_CACHE.get(session_id, []))}")
            return task
    return None

def add_task_to_cache(session_id: str, task: dict):
    """Добавить задачу в кэш"""
    with CACHE_LOCK:
        if session_id not in TASK_CACHE:
            TASK_CACHE[session_id] = []
        TASK_CACHE[session_id].append(task)
        print(f"[Prefetch] 💾 Задача добавлена в кэш. Всего в кэше: {len(TASK_CACHE[session_id])}")

def clear_cache(session_id: str):
    """Очистить кэш пользователя"""
    with CACHE_LOCK:
        if session_id in TASK_CACHE:
            del TASK_CACHE[session_id]
            print(f"[Prefetch] 🗑️ Кэш очищен для сессии {session_id[:8]}...")

def get_cache_size(session_id: str) -> int:
    """Получить размер кэша"""
    with CACHE_LOCK:
        return len(TASK_CACHE.get(session_id, []))
