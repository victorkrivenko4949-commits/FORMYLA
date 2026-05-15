#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Диагностика параллелизма regenerate_full.py.

Анализирует последний log в logs/ и отвечает на 3 вопроса:
1. Реально ли asyncio.gather запускает 3 ячейки одновременно?
   (смотрим временные интервалы между START CELL ... и END CELL ... для соседних ячеек)
2. Чистое время одной ячейки (START→END) — без параллелизма.
3. Сколько времени уходит на retry / 429 (по строкам в логах).

Запуск:
    python scripts/diagnose_parallelism.py
    python scripts/diagnose_parallelism.py logs/full_regen_<TS>.log
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# Формат строк: "HH:MM:SS [LEVEL] logger — message"
START_RE = re.compile(
    r"^(?P<ts>\d{2}:\d{2}:\d{2}).*?START CELL\s+(?P<cell>\S+)"
)
END_RE = re.compile(
    r"^(?P<ts>\d{2}:\d{2}:\d{2}).*?END CELL\s+(?P<cell>\S+):\s+success=(?P<success>\d+)\s+review=(?P<review>\d+)\s+dup=(?P<dup>\d+)\s+err=(?P<err>\d+)\s+cost=\$(?P<cost>[\d.]+)\s+avg_iter=(?P<avg>[\d.]+)"
)
BATCH_RE = re.compile(
    r"^(?P<ts>\d{2}:\d{2}:\d{2}).*?BATCH\s+(?P<a>\d+)-(?P<b>\d+)\s+/\s+(?P<total>\d+)"
)
RATE_LIMIT_RE = re.compile(r"429|rate.?limit|Too Many Requests", re.IGNORECASE)
RETRY_RE = re.compile(r"Retrying|tenacity|attempt \d+/\d+", re.IGNORECASE)
OR_ERROR_RE = re.compile(r"OpenRouter\s+\S+\s+→\s+(\d+):")
TASK_LINE_RE = re.compile(
    r"^(?P<ts>[\d\-:\s,]+)\s+.*?\[\s*\d+/\d+\]\s+run=(?P<run>\w+)"
)


def parse_ts(s: str) -> datetime | None:
    """Лог пишет только HH:MM:SS — добавим фиктивную дату 2000-01-01.
    Если timestamp перескакивает за полночь — добавим день."""
    s = s.strip().rstrip(",")
    for fmt in ("%H:%M:%S",):
        try:
            return datetime.strptime("2000-01-01 " + s, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    return None


def main() -> int:
    if len(sys.argv) > 1:
        log_path = Path(sys.argv[1])
    else:
        candidates = sorted(LOG_DIR.glob("full_regen_*.log"))
        if not candidates:
            print(f"No logs in {LOG_DIR}")
            return 1
        log_path = candidates[-1]

    print(f"=== Analyzing: {log_path.name} ===\n")
    text = log_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    print(f"total lines: {len(lines)}")

    # ─── Сбор событий ─────────────────────────────────────────────────────
    starts: dict[str, list[datetime]] = defaultdict(list)
    ends: dict[str, list[tuple[datetime, dict]]] = defaultdict(list)
    batches: list[tuple[datetime, int, int, int]] = []
    rate_limit_hits = 0
    retry_hits = 0
    or_errors: dict[int, int] = defaultdict(int)

    for line in lines:
        # START CELL
        m = START_RE.search(line)
        if m:
            ts = parse_ts(m.group("ts"))
            if ts:
                starts[m.group("cell")].append(ts)
            continue
        # END CELL
        m = END_RE.search(line)
        if m:
            ts = parse_ts(m.group("ts"))
            if ts:
                ends[m.group("cell")].append((ts, {
                    "success": int(m.group("success")),
                    "review": int(m.group("review")),
                    "dup": int(m.group("dup")),
                    "err": int(m.group("err")),
                    "cost": float(m.group("cost")),
                    "avg_iter": float(m.group("avg")),
                }))
            continue
        # BATCH
        m = BATCH_RE.search(line)
        if m:
            ts = parse_ts(m.group("ts"))
            if ts:
                batches.append((ts, int(m.group("a")), int(m.group("b")), int(m.group("total"))))
            continue
        # ошибки
        if RATE_LIMIT_RE.search(line):
            rate_limit_hits += 1
        if RETRY_RE.search(line):
            retry_hits += 1
        m = OR_ERROR_RE.search(line)
        if m:
            or_errors[int(m.group(1))] += 1

    print(f"START CELL events: {sum(len(v) for v in starts.values())}")
    print(f"END   CELL events: {sum(len(v) for v in ends.values())}")
    print(f"BATCH events:      {len(batches)}")
    print(f"rate-limit lines:  {rate_limit_hits}")
    print(f"retry lines:       {retry_hits}")
    if or_errors:
        print(f"OpenRouter errors by status:")
        for code, n in sorted(or_errors.items()):
            print(f"  {code}: {n}")
    else:
        print("OpenRouter errors by status: (none parsed by regex)")

    # ─── Q1: параллелизм — пересечение интервалов START..END между ячейками
    print("\n=== Q1: параллелизм (overlap intervals) ===")
    completed = []
    for cell, st_list in starts.items():
        for st in st_list:
            # ищем ближайший END > ST для той же ячейки
            for en, _ in ends.get(cell, []):
                if en > st:
                    completed.append((cell, st, en))
                    break

    if not completed:
        print("(нет завершённых ячеек — нечего сравнивать)")
    else:
        completed.sort(key=lambda x: x[1])
        # для каждой ячейки считаем, сколько других ячеек выполнялись параллельно
        overlap_counts = []
        for i, (c, st, en) in enumerate(completed):
            n_overlap = 0
            for j, (c2, st2, en2) in enumerate(completed):
                if i == j:
                    continue
                if st2 < en and en2 > st:
                    n_overlap += 1
            overlap_counts.append((c, st, en, n_overlap))

        max_par = max(o[3] for o in overlap_counts) + 1
        print(f"  max parallel cells observed: {max_par}")
        print(f"  expected (batch-size=3):     3")
        if max_par >= 3:
            print("  ✓ параллелизм РАБОТАЕТ — ячейки реально пересекаются во времени")
        elif max_par == 2:
            print("  ⚠ параллелизм ЧАСТИЧНЫЙ (видим max 2 одновременно)")
        else:
            print("  ✗ параллелизм НЕ работает — ячейки идут последовательно")

        # распределение overlap
        from collections import Counter
        dist = Counter(o[3] for o in overlap_counts)
        print(f"  distribution (n other cells running): {dict(sorted(dist.items()))}")

    # ─── Q2: чистое время одной ячейки
    print("\n=== Q2: время одной ячейки (START→END) ===")
    if not completed:
        print("(нет данных)")
    else:
        durations = [(en - st).total_seconds() for _, st, en, _ in [
            (c, st, en, 0) for c, st, en in completed
        ]]
        # отсортируем
        durations.sort()
        n = len(durations)
        print(f"  cells with full START→END: {n}")
        print(f"  min:    {min(durations):.0f} sec ({min(durations)/60:.1f} min)")
        print(f"  median: {durations[n//2]:.0f} sec ({durations[n//2]/60:.1f} min)")
        print(f"  mean:   {sum(durations)/n:.0f} sec ({sum(durations)/n/60:.1f} min)")
        print(f"  max:    {max(durations):.0f} sec ({max(durations)/60:.1f} min)")

    # ─── Q3: время на retry/429 — оценка
    print("\n=== Q3: retry / rate-limit влияние ===")
    print(f"  rate-limit hits: {rate_limit_hits}")
    print(f"  retry attempts:  {retry_hits}")
    if rate_limit_hits == 0 and retry_hits == 0:
        print("  → проблем с rate-limit не видно в текущем логе")
    else:
        # tenacity exponential backoff RETRY_WAIT_MIN..RETRY_WAIT_MAX (см. pipeline/config.py)
        print("  → backoff в pipeline/openrouter_client.py: wait_exponential(min=2, max=60) по умолч.")
        avg_backoff = 10  # секунд (примерно)
        est_lost = retry_hits * avg_backoff
        print(f"  → грубая оценка потери времени: {retry_hits} × ~{avg_backoff}s = ~{est_lost}s ({est_lost/60:.1f} min)")

    # ─── Бонус: последние 5 ячеек со стат
    print("\n=== Последние 5 ячеек (по END timestamp) ===")
    flat_ends = []
    for cell, es in ends.items():
        for ts, stats in es:
            flat_ends.append((ts, cell, stats))
    flat_ends.sort()
    for ts, cell, stats in flat_ends[-5:]:
        print(f"  {ts}  {cell}: success={stats['success']} review={stats['review']} "
              f"dup={stats['dup']} err={stats['err']} ${stats['cost']:.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
