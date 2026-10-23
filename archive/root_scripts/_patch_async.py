"""Patch _gen_678.py: replace async_main() with concurrent time-based version."""
import re

with open('_gen_678.py', 'r', encoding='utf-8') as f:
    content = f.read()

# New async_main function with time-based concurrent execution
new_func = '''async def async_main(target: int = 1000, max_concurrent: int = 1, max_duration: int = 20):
    """Основной асинхронный цикл генерации с конкурентным выполнением.

    Args:
        target: Сколько задач принять — для отчёта (сумма L8+L7+L6).
        max_concurrent: Сколько задач обрабатывать одновременно.
        max_duration: Максимальное время работы в минутах (default: 20).
    """
    ensure_dirs()
    global SEEN_TEXTS
    SEEN_TEXTS = load_seen_texts()
    logger.info(f"Загружено {len(SEEN_TEXTS)} seen_texts для детекции клонов")

    # Загружаем checkpoint если есть
    cp = load_checkpoint()
    if cp:
        raw_counts = cp.get('accepted_counts', {})
        cp_total = sum(raw_counts.values()) if isinstance(raw_counts, dict) else 0
        logger.info(f"Найден checkpoint: принято {cp_total} задач, "
                     f"blacklist {cp.get('blacklist_count', 0)}, "
                     f"next_id={cp.get('next_id', 800001)}")
        next_id = cp.get('next_id', load_next_id())
        accepted_counts = {}
        for k, v in raw_counts.items():
            try:
                accepted_counts[int(k)] = v
            except (ValueError, TypeError):
                pass
        for k in [8, 7, 6]:
            accepted_counts.setdefault(k, 0)
        blacklist_count = cp.get('blacklist_count', 0)
        reserve_count = cp.get('reserve_count', 0)
        correction_count = cp.get('correction_count', 0)
        start_time = cp.get('start_time', time.time())
        consecutive_blacklist = cp.get('consecutive_blacklist', 0)
        topic_index = cp.get('topic_index', 0)
    else:
        next_id = load_next_id()
        accepted_counts = {8: 0, 7: 0, 6: 0}
        blacklist_count = 0
        reserve_count = 0
        correction_count = 0
        start_time = time.time()
        consecutive_blacklist = 0
        topic_index = 0

    total_accepted = sum(accepted_counts.values())

    # Проверяем, сколько уже есть сохранённых задач в L8/L7/L6
    for level_dir, level_key in [(L8_DIR, 8), (L7_DIR, 7), (L6_DIR, 6)]:
        existing = [f for f in os.listdir(level_dir) if f.endswith('.json')]
        accepted_counts[level_key] = max(accepted_counts[level_key], len(existing))

    total_accepted = sum(accepted_counts.values())
    logger.info(f"Уже принято: L8={accepted_counts[8]}, L7={accepted_counts[7]}, L6={accepted_counts[6]}, всего={total_accepted}")

    client = DeepSeekClient()
    logger.info("DeepSeekClient инициализирован")

    # ── Конкурентная инфраструктура ──
    semaphore = asyncio.Semaphore(max_concurrent)
    id_lock = asyncio.Lock()
    stats_lock = asyncio.Lock()
    checkpoint_counter = 0

    async def process_one_task_wrapper(topic_val):
        """Обёртка: захватывает семафор, ID, запускает process_one_task, обновляет статистику."""
        nonlocal next_id, total_accepted