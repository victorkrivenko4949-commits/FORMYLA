# -*- coding: utf-8 -*-
"""Выборка задач для листка из FORMYLA_BANK.jsonl (без генерации, без LLM).

select_tasks(...) -> (tasks, warnings); replace_task(...) -> (task | None, warnings).
Уровни — существующая шкала банка 1–4. Квоты 25/37.5/25/12.5 %, метод наибольших
остатков, при равенстве — младший уровень: n=8 -> 2/3/2/1, n=6 -> 2/2/1/1, n=10 -> 3/4/2/1.
"""
from __future__ import annotations

import hashlib
import random
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from teacher.worksheets import bank_index, history

LEVELS = (1, 2, 3, 4)
QUOTA_SHARES = {1: 0.25, 2: 0.375, 3: 0.25, 4: 0.125}
MIN_OLYMPIAD = 2
SOURCE_KEYS = ("olympiad", "year", "stage", "number")


# ───────────────────────── источник / представление ─────────────────────────

def source_of(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Источник олимпиады из записи банка. Поддерживает вложенный dict ``source``
    и плоские ключи olympiad/year/stage/number/source_grade. Нет олимпиады -> None."""
    src = rec.get("source")
    if isinstance(src, dict):
        d = dict(src)
    elif isinstance(src, str) and src.strip():
        d = {"olympiad": src.strip()}
    else:
        d = {k: rec.get(k) for k in SOURCE_KEYS if rec.get(k) not in (None, "")}
        if rec.get("source_grade") not in (None, ""):
            d["grade"] = rec.get("source_grade")
    if not d.get("olympiad"):
        return None
    d.setdefault("grade", rec.get("grade"))
    return d


def source_key(rec: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    s = source_of(rec)
    if not s:
        return None
    return (str(s.get("olympiad", "")).strip().lower(), str(s.get("year", "")).strip())


def methods_of(rec: Dict[str, Any]) -> List[str]:
    m = rec.get("methods") or rec.get("method_codes") or rec.get("techniques") or []
    if isinstance(m, str):
        m = [x.strip() for x in m.split(",") if x.strip()]
    return [str(x) for x in m]


def to_task(rec: Dict[str, Any], target_level: int) -> Dict[str, Any]:
    return {
        "task_id": int(rec[bank_index.ID_FIELD]),
        "level": int(rec["level"]),
        "target_level": int(target_level),
        "grade": int(rec["grade"]),
        "topic": (rec.get("topic") or "").strip(),
        "methods": methods_of(rec),
        "source": source_of(rec),
        "statement": rec.get("task_text") or "",
        "has_figure": bool((rec.get("figure_svg_path") or "").strip()),
    }


# ───────────────────────────────── квоты ─────────────────────────────────

def quotas(n: int, level_min: int = 1, level_max: int = 4) -> Dict[int, int]:
    if n <= 0:
        return {lv: 0 for lv in LEVELS}
    raw = {lv: n * QUOTA_SHARES[lv] for lv in LEVELS}
    q = {lv: int(raw[lv]) for lv in LEVELS}
    rest = n - sum(q.values())
    for lv in sorted(LEVELS, key=lambda l: (-(raw[l] - q[l]), l)):
        if rest <= 0:
            break
        q[lv] += 1
        rest -= 1
    allowed = [lv for lv in LEVELS if level_min <= lv <= level_max]
    if not allowed:
        allowed = list(LEVELS)
    for lv in LEVELS:
        if lv not in allowed and q[lv]:
            nearest = min(allowed, key=lambda a: (abs(a - lv), a))
            q[nearest] += q[lv]
            q[lv] = 0
    return q


def default_seed(teacher_id: Optional[int], topics: Sequence[str], day: Optional[date] = None) -> int:
    day = day or date.today()
    raw = f"{teacher_id}|{day.isoformat()}|{'|'.join(sorted(topics or []))}"
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12], 16)


# ───────────────────────────── кандидаты ─────────────────────────────────

def _pool(grade: int, level: int, topics: Sequence[str], excluded: Set[int],
          only_olympiad: bool, allow_younger: bool) -> List[Dict[str, Any]]:
    recs = list(bank_index.candidates(grade, level, topics))
    if allow_younger and level == 1 and grade - 1 >= 5:
        recs += bank_index.candidates(grade - 1, 1, topics)
    out, seen = [], set()
    for r in recs:
        tid = int(r[bank_index.ID_FIELD])
        if tid in excluded or tid in seen:
            continue
        if only_olympiad and source_of(r) is None:
            continue
        seen.add(tid)
        out.append(r)
    return out


def _resolve_topics(grade: int, topics: Optional[Sequence[str]], mode: str,
                    group_id: Optional[int], warnings: List[str]) -> List[str]:
    if mode == "mixed":
        t = history.group_recent_topics(group_id, limit=4) if group_id else []
        if not t:
            t = bank_index.topics_for_grade(grade)
            warnings.append("mixed: у группы нет листков за историю — взяты все темы класса")
        return list(t)
    t = [x.strip() for x in (topics or []) if x and x.strip()]
    if not t:
        t = bank_index.topics_for_grade(grade)
        warnings.append("темы не заданы — взяты все темы класса")
    return t


# ──────────────────────────── расстановка ────────────────────────────────

def arrange(picked: List[Tuple[Dict[str, Any], int]], warnings: List[str]) -> List[Tuple[Dict[str, Any], int]]:
    """Строго по возрастанию target_level; внутри уровня порядок подбирается так,
    чтобы соседи (в т.ч. через границу уровней) не были из одного источника (olympiad+year)."""
    result: List[Tuple[Dict[str, Any], int]] = []
    conflict = False
    for lv in sorted({p[1] for p in picked}):
        group = [p for p in picked if p[1] == lv]
        while group:
            prev = source_key(result[-1][0]) if result else None
            idx = next((i for i, p in enumerate(group)
                        if prev is None or source_key(p[0]) is None or source_key(p[0]) != prev), None)
            if idx is None:
                idx, conflict = 0, True
            result.append(group.pop(idx))
    if conflict:
        warnings.append("не удалось развести соседние задачи из одного источника")
    return result


# ───────────────────────────── основная функция ──────────────────────────────

def select_tasks(grade: int, topics: Optional[Sequence[str]] = None, n: int = 8,
                 level_min: int = 1, level_max: int = 4, only_olympiad: bool = False,
                 exclude_group_id: Optional[int] = None, mode: str = "topic",
                 seed: Optional[int] = None, teacher_id: Optional[int] = None,
                 exclude_task_ids: Optional[Iterable[int]] = None,
                 ) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    grade = int(grade)
    n = max(1, int(n))
    level_min, level_max = max(1, int(level_min)), min(4, int(level_max))
    if level_min > level_max:
        level_min, level_max = level_max, level_min

    topics_r = _resolve_topics(grade, topics, mode, exclude_group_id, warnings)
    if seed is None:
        seed = default_seed(teacher_id, topics_r)
    rng = random.Random(seed)

    excluded: Set[int] = set(int(x) for x in (exclude_task_ids or []))
    if exclude_group_id:
        excluded |= history.group_solved_task_ids(exclude_group_id)
        excluded |= history.group_recent_worksheet_task_ids(exclude_group_id, days=60)

    q = quotas(n, level_min, level_max)
    pools: Dict[int, List[Dict[str, Any]]] = {}
    for lv in LEVELS:
        pool = _pool(grade, lv, topics_r, excluded, only_olympiad, allow_younger=True)
        rng.shuffle(pool)
        pools[lv] = pool

    picked: List[Tuple[Dict[str, Any], int]] = []
    used: Set[int] = set()

    def take(lv: int, target: int) -> bool:
        for r in pools[lv]:
            tid = int(r[bank_index.ID_FIELD])
            if tid in used:
                continue
            if int(r["grade"]) != grade and target != 1:
                continue  # младший класс — только на позиции уровня 1
            used.add(tid)
            picked.append((r, target))
            return True
        return False

    for lv in LEVELS:
        for _ in range(q[lv]):
            if take(lv, lv):
                continue
            filled = False
            for dist in (1, 2, 3):
                for alt in (lv - dist, lv + dist):
                    if alt in LEVELS and level_min <= alt <= level_max and take(alt, lv):
                        filled = True
                        break
                if filled:
                    break
            if not filled:
                for dist in (1, 2, 3):
                    for alt in (lv - dist, lv + dist):
                        if alt in LEVELS and take(alt, lv):
                            filled = True
                            break
                    if filled:
                        break
            if filled:
                warnings.append(f"уровень {lv}: не хватило кандидатов, взята задача соседнего уровня")
            else:
                warnings.append(f"уровень {lv}: кандидатов нет, позиция пропущена")

    # ≥ MIN_OLYMPIAD задач с источником (если не only_olympiad — пробуем заменить)
    if not only_olympiad:
        have = sum(1 for r, _ in picked if source_of(r) is not None)
        if have < MIN_OLYMPIAD:
            for i, (r, target) in enumerate(picked):
                if have >= MIN_OLYMPIAD:
                    break
                if source_of(r) is not None:
                    continue
                lv = int(r["level"])
                alt = next((c for c in pools[lv] if int(c[bank_index.ID_FIELD]) not in used
                            and source_of(c) is not None and (int(c["grade"]) == grade or target == 1)), None)
                if alt is not None:
                    used.discard(int(r[bank_index.ID_FIELD]))
                    used.add(int(alt[bank_index.ID_FIELD]))
                    picked[i] = (alt, target)
                    have += 1
            if have < MIN_OLYMPIAD:
                warnings.append(f"олимпиадных задач с источником меньше {MIN_OLYMPIAD}: {have}")

    arranged = arrange(picked, warnings)
    tasks = [to_task(r, t) for r, t in arranged]
    for pos, t in enumerate(tasks, start=1):
        t["position"] = pos
    if len(tasks) < n:
        warnings.append(f"собрано {len(tasks)} из {n}")
    return tasks, warnings


# ───────────────────────────── замена задачи ─────────────────────────────────

def replace_task(worksheet, task_id: int, direction: str = "same",
                 seed: Optional[int] = None) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Подобрать замену задаче task_id в листке: та же тема, уровень по direction
    ('same' | 'harder' | 'easier'), не в листке, не решённая группой. Обновляет
    WorksheetTask (task_id, target_level, added_by='teacher') без commit.
    """
    warnings: List[str] = []
    cur = bank_index.get(task_id)
    if cur is None:
        return None, [f"задача {task_id} не найдена в банке"]
    row = next((t for t in worksheet.tasks if int(t.task_id) == int(task_id)), None)
    if row is None:
        return None, [f"задача {task_id} не в листке"]

    lv = int(cur["level"])
    if direction == "harder":
        levels = [l for l in LEVELS if l > lv]
    elif direction == "easier":
        levels = [l for l in LEVELS if l < lv][::-1]
    else:
        levels = [lv]
    if not levels:
        return None, [f"нет уровня {'выше' if direction == 'harder' else 'ниже'} {lv}"]

    excluded = {int(t.task_id) for t in worksheet.tasks}
    gid = getattr(worksheet, "group_id", None)
    if gid:
        excluded |= history.group_solved_task_ids(gid)
    topic = (cur.get("topic") or "").strip()
    grade = int(getattr(worksheet, "grade", cur["grade"]))
    rng = random.Random(seed if seed is not None else default_seed(getattr(worksheet, "teacher_id", None), [topic]))

    for target in levels:
        pool = _pool(grade, target, [topic], excluded, only_olympiad=False, allow_younger=(target == 1))
        pool = [r for r in pool if int(r["grade"]) == grade or target == 1]
        if not pool:
            continue
        rec = rng.choice(pool)
        if target != levels[0]:
            warnings.append(f"на уровне {levels[0]} кандидатов нет, взят уровень {target}")
        row.task_id = int(rec[bank_index.ID_FIELD])
        row.target_level = target
        if hasattr(row, "added_by"):
            row.added_by = "teacher"
        return to_task(rec, target), warnings
    return None, [f"нет замены по теме «{topic}» на уровнях {levels}"]
