"""
Асинхронный генератор задач для Free Mock
Предгенерирует задачи в фоновом режиме для мгновенной отдачи пользователю
"""
import threading
import time
import logging
from queue import Queue, Empty
from typing import Dict, Optional
from datetime import datetime, timedelta

# Глобальное хранилище очередей для каждого пользователя
# Ключ: session_id, Значение: {'queue': Queue, 'config': dict, 'last_activity': datetime}
USER_QUEUES: Dict[str, dict] = {}
QUEUE_LOCK = threading.Lock()

# Настройки
PREFETCH_SIZE = 2  # Сколько задач держать в очереди заранее
QUEUE_TIMEOUT = 1800  # 30 минут - время жизни очереди без активности
CLEANUP_INTERVAL = 300  # 5 минут - интервал очистки старых очередей

logger = logging.getLogger(__name__)


def get_or_create_queue(session_id: str, config: dict = None) -> Queue:
    """
    Получить или создать очередь для пользователя
    
    Args:
        session_id: ID сессии пользователя
        config: Конфигурация генерации (class_level, difficulty и т.д.)
    
    Returns:
        Queue объект для данного пользователя
    """
    with QUEUE_LOCK:
        if session_id not in USER_QUEUES:
            USER_QUEUES[session_id] = {
                'queue': Queue(maxsize=PREFETCH_SIZE + 1),
                'config': config or {},
                'last_activity': datetime.now(),
                'task_count': 0
            }
            logger.info(f"[Prefetch] 🆕 Создана новая очередь для сессии {session_id[:8]}...")
        else:
            # Обновляем время последней активности
            USER_QUEUES[session_id]['last_activity'] = datetime.now()
            if config:
                USER_QUEUES[session_id]['config'].update(config)
        
        return USER_QUEUES[session_id]['queue']


def clear_queue(session_id: str):
    """Очистить очередь пользователя"""
    with QUEUE_LOCK:
        if session_id in USER_QUEUES:
            try:
                # Очищаем очередь
                while not USER_QUEUES[session_id]['queue'].empty():
                    USER_QUEUES[session_id]['queue'].get_nowait()
            except Empty:
                pass
            del USER_QUEUES[session_id]
            logger.info(f"[Prefetch] 🗑️ Очередь для сессии {session_id[:8]}... очищена")


def get_queue_size(session_id: str) -> int:
    """Получить текущий размер очереди"""
    with QUEUE_LOCK:
        if session_id in USER_QUEUES:
            return USER_QUEUES[session_id]['queue'].qsize()
    return 0


def background_task_generator(session_id: str, deepseek_client, task_config: dict):
    """
    Фоновая функция для генерации задач
    Работает в отдельном потоке
    
    Args:
        session_id: ID сессии пользователя
        deepseek_client: Инстанс DeepSeekClient
        task_config: Конфигурация задачи (class_level, difficulty, task_number и т.д.)
    """
    try:
        queue = get_or_create_queue(session_id, task_config)
        
        # Проверяем, не заполнена ли уже очередь
        if queue.qsize() >= PREFETCH_SIZE:
            logger.debug(f"[Prefetch] ⏸️ Очередь для {session_id[:8]}... уже заполнена ({queue.qsize()}/{PREFETCH_SIZE})")
            return
        
        logger.info(f"[Prefetch] 🔄 Фоновая генерация задачи #{task_config.get('task_number', '?')} для сессии {session_id[:8]}...")
        
        # Импортируем здесь, чтобы избежать циклических импортов
        from app import generate_task_internal
        
        # Генерируем задачу
        task = generate_task_internal(deepseek_client, task_config)
        
        if task:
            # Добавляем задачу в очередь
            queue.put(task, block=False)
            
            with QUEUE_LOCK:
                if session_id in USER_QUEUES:
                    USER_QUEUES[session_id]['task_count'] += 1
                    USER_QUEUES[session_id]['last_activity'] = datetime.now()
            
            logger.info(f"[Prefetch] ✅ Задача #{task_config.get('task_number', '?')} добавлена в очередь. Размер очереди: {queue.qsize()}")
        else:
            logger.error(f"[Prefetch] ❌ Не удалось сгенерировать задачу #{task_config.get('task_number', '?')}")
            
    except Exception as e:
        logger.error(f"[Prefetch] ❌ Ошибка в фоновой генерации: {e}", exc_info=True)


def start_prefetch(session_id: str, deepseek_client, task_config: dict):
    """
    Запустить фоновую предгенерацию задачи
    
    Args:
        session_id: ID сессии пользователя
        deepseek_client: Инстанс DeepSeekClient
        task_config: Конфигурация задачи
    """
    thread = threading.Thread(
        target=background_task_generator,
        args=(session_id, deepseek_client, task_config),
        daemon=True  # Поток завершится при завершении основного процесса
    )
    thread.start()
    logger.debug(f"[Prefetch] 🚀 Запущен фоновый поток для сессии {session_id[:8]}...")


def get_prefetched_task(session_id: str, timeout: float = 0.1) -> Optional[dict]:
    """
    Получить предсгенерированную задачу из очереди
    
    Args:
        session_id: ID сессии пользователя
        timeout: Время ожидания задачи (секунды)
    
    Returns:
        Задача или None, если очередь пуста
    """
    queue = get_or_create_queue(session_id)
    
    try:
        task = queue.get(block=True, timeout=timeout)
        logger.info(f"[Prefetch] 📤 Выдана предсгенерированная задача. Осталось в очереди: {queue.qsize()}")
        return task
    except Empty:
        logger.debug(f"[Prefetch] ⏳ Очередь пуста для сессии {session_id[:8]}...")
        return None


def cleanup_old_queues():
    """Очистить старые неактивные очереди"""
    with QUEUE_LOCK:
        now = datetime.now()
        to_remove = []
        
        for session_id, data in USER_QUEUES.items():
            if (now - data['last_activity']).total_seconds() > QUEUE_TIMEOUT:
                to_remove.append(session_id)
        
        for session_id in to_remove:
            try:
                while not USER_QUEUES[session_id]['queue'].empty():
                    USER_QUEUES[session_id]['queue'].get_nowait()
            except Empty:
                pass
            del USER_QUEUES[session_id]
            logger.info(f"[Prefetch] 🧹 Удалена неактивная очередь для сессии {session_id[:8]}...")


def start_cleanup_daemon():
    """Запустить фоновый процесс очистки старых очередей"""
    def cleanup_loop():
        while True:
            time.sleep(CLEANUP_INTERVAL)
            cleanup_old_queues()
    
    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    logger.info("[Prefetch] 🧹 Запущен фоновый процесс очистки очередей")


# Запускаем cleanup daemon при импорте модуля
start_cleanup_daemon()
