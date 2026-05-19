# -*- coding: utf-8 -*-
"""Обогащение архивных задач ВсОШ-9 полным текстом условия + решением + ответом.

Берёт данные из Python-модуля вида `OLYMPIADS_DB = [...]` (структура с ключами
`olympiad`, `year`, `grade`, `round`, `problems: [{num, text, answer, solution}]`)
и обновляет в БД записи `OlympiadTask`, привязанные к архивным пробникам
`vsosh-9-archive-{YEAR}` (см. `scripts/import_vsosh9_methods.py`).

Сопоставление задачи в БД ↔ задачи в источнике:
  • БД задача:    `OlympiadTask.number = '{prefix}-{N}'` (например `Р-4`, `З1-5`),
                  `year`, `stage` ∈ {school, municipal, regional, final},
                  `probnik_id` принадлежит `Probnik.code = 'vsosh-9-archive-{year}'`.
  • Источник:     `OLYMPIADS_DB` запись с `olympiad='vsosh'`, `grade=9`,
                  `year=YYYY`, `round='school'|'municipal'|'regional'|'final'`,
                  внутри `problems: [{num: N, text, answer, solution}]`.

Что обновляется (только если в источнике поле не пустое):
  • `condition_md`  — `problem.text` (но **только** если в БД стоит заглушка
                      «*Текст задачи будет добавлен позже.*» или укороченный
                      excerpt, который короче текста из источника);
  • `solution_md`   — `problem.solution`, всегда если в БД заглушка
                      «*Полное решение будет добавлено позже.*»;
  • `answer`        — `problem.answer`, если в БД пусто или совпадает с прежним.

`idea_md` не трогаем (там по-прежнему placeholder; в источнике идеи нет).

Опции CLI:
    --path PATH      Путь к файлу с `OLYMPIADS_DB` (по умолчанию ищем рядом).
    --dry-run        Прокатать без commit (отчёт + rollback).
    --force-replace  Перезаписывать condition_md / solution_md / answer даже
                     если они не плейсхолдеры (использовать осторожно).

Запуск:
    python scripts/enrich_archive_tasks_from_olympiads_db.py \
        --path "C:\\Users\\Victor\\Downloads\\olympiads_with_real_solutions-3.py"
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from collections import Counter
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app import app  # noqa: E402
from models import db  # noqa: E402
from models_olympiad import Probnik, OlympiadTask  # noqa: E402


# Карта `round` → нормализованный stage (как в БД).
ROUND_TO_STAGE = {
    'school':    'school',
    'municipal': 'municipal',
    'regional':  'regional',
    'final':     'final',
}

# Маркеры заглушек — если condition_md / solution_md равен или начинается с
# одной из этих фраз, считаем, что в БД нет настоящего содержимого.
PLACEHOLDER_PREFIXES = (
    '*Текст задачи будет добавлен позже.*',
    '*Идея решения будет добавлена позже.*',
    '*Полное решение будет добавлено позже.*',
)


def _is_placeholder(s: Optional[str]) -> bool:
    if not s:
        return True
    s = s.strip()
    if not s:
        return True
    for p in PLACEHOLDER_PREFIXES:
        if s.startswith(p):
            return True
    return False


def _load_olympiads_db(path: str) -> list:
    spec = importlib.util.spec_from_file_location('olymp_src', path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Не удалось загрузить модуль из {path!r}')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    if not hasattr(mod, 'OLYMPIADS_DB'):
        raise RuntimeError(f'В файле {path!r} нет переменной OLYMPIADS_DB')
    db_list = mod.OLYMPIADS_DB
    if not isinstance(db_list, list):
        raise RuntimeError('OLYMPIADS_DB должен быть list')
    return db_list


def _build_source_index(db_list: list) -> dict:
    """Возвращает {(year, stage, num): {'text', 'answer', 'solution'}} только
    для ВсОШ-9."""
    idx: dict[tuple[int, str, int], dict] = {}
    dup = 0
    for entry in db_list:
        if entry.get('olympiad') != 'vsosh':
            continue
        if entry.get('grade') != 9:
            continue
        year = entry.get('year')
        rnd = entry.get('round')
        stage = ROUND_TO_STAGE.get(rnd)
        if not year or not stage:
            continue
        for p in entry.get('problems') or []:
            try:
                num = int(p.get('num'))
            except (TypeError, ValueError):
                continue
            key = (int(year), stage, num)
            payload = {
                'text': (p.get('text') or '').strip(),
                'answer': (p.get('answer') or '').strip(),
                'solution': (p.get('solution') or '').strip(),
            }
            if key in idx:
                dup += 1
                # Берём более длинную/полную версию.
                old = idx[key]
                if len(payload.get('solution') or '') > len(old.get('solution') or ''):
                    idx[key] = payload
                continue
            idx[key] = payload
    if dup:
        print(f'  [info] в источнике обнаружено {dup} дублирующихся ключей '
              f'(оставлены наиболее полные версии)')
    return idx


# Парсим OlympiadTask.number вида 'Р-4', 'М-1', 'З1-5', 'З2-3', 'Ш-2' → суффикс
# (последнее число после дефиса) = problem.num.
_NUM_TAIL_RE = re.compile(r'-(\d+)$')


def _problem_num_from_task_number(task_number: str) -> Optional[int]:
    m = _NUM_TAIL_RE.search(task_number or '')
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def enrich(db_path: str, dry_run: bool = False, force_replace: bool = False) -> None:
    print(f'📂 Источник: {db_path}')
    db_list = _load_olympiads_db(db_path)
    print(f'  Записей всего: {len(db_list)}')
    src_idx = _build_source_index(db_list)
    print(f'  Источник: {len(src_idx)} задач ВсОШ-9 (по ключу year/stage/num)')

    with app.app_context():
        # Берём все архивные пробники.
        archive_probniks = (
            Probnik.query
            .filter(Probnik.code.like('vsosh-9-archive-%'))
            .all()
        )
        archive_ids = {p.id for p in archive_probniks}
        print(f'  Архивных пробников в БД: {len(archive_ids)}')

        # Все задачи этих пробников.
        tasks = (
            OlympiadTask.query
            .filter(OlympiadTask.probnik_id.in_(archive_ids))
            .all()
        )
        print(f'  Архивных задач в БД: {len(tasks)}')

        stats = Counter()
        unmatched_in_db = []  # задачи в БД, для которых не нашли источник
        skipped_already_full = 0

        for t in tasks:
            stats['total'] += 1
            num = _problem_num_from_task_number(t.number or '')
            if num is None or t.year is None or t.stage is None:
                stats['no_key'] += 1
                continue
            key = (int(t.year), t.stage, num)
            src = src_idx.get(key)
            if src is None:
                unmatched_in_db.append((t.id, t.number, key))
                stats['no_source'] += 1
                continue

            changed = False

            # condition_md: обновляем, если плейсхолдер ИЛИ источник заметно
            # длиннее (минимум +50 символов), ИЛИ --force-replace.
            new_text = src['text']
            if new_text:
                cond = t.condition_md or ''
                cond_is_ph = _is_placeholder(cond)
                if force_replace or cond_is_ph or (
                    len(new_text) >= len(cond) + 50
                ):
                    if cond.strip() != new_text:
                        t.condition_md = new_text
                        changed = True
                        stats['condition_updated'] += 1

            # solution_md: всегда обновляем, если плейсхолдер или пусто.
            new_sol = src['solution']
            if new_sol:
                if force_replace or _is_placeholder(t.solution_md):
                    if (t.solution_md or '').strip() != new_sol:
                        t.solution_md = new_sol
                        changed = True
                        stats['solution_updated'] += 1

            # answer: обновляем, если в БД пусто или короче.
            new_ans = src['answer']
            if new_ans:
                old_ans = (t.answer or '').strip()
                # answer — String(500), отрежем на всякий случай.
                new_ans_cut = new_ans[:500]
                if force_replace or not old_ans or len(old_ans) < len(new_ans_cut):
                    if old_ans != new_ans_cut:
                        t.answer = new_ans_cut
                        changed = True
                        stats['answer_updated'] += 1

            if changed:
                stats['tasks_changed'] += 1
            else:
                skipped_already_full += 1

        print()
        print('─' * 60)
        print('📊 Итоги:')
        for k in (
            'total', 'tasks_changed',
            'condition_updated', 'solution_updated', 'answer_updated',
            'no_source', 'no_key',
        ):
            print(f'  {k:>22}: {stats.get(k, 0)}')
        print(f'  {"already_full_skipped":>22}: {skipped_already_full}')

        if unmatched_in_db:
            print(f'\n  [warn] нет источника для {len(unmatched_in_db)} задач '
                  '(пример первых 10):')
            for tid, num, key in unmatched_in_db[:10]:
                print(f'     - task #{tid} number={num!r} key={key}')

        if dry_run:
            db.session.rollback()
            print('\n🟡 Dry-run: транзакция откачена.')
        else:
            db.session.commit()
            print('\n✅ Изменения сохранены в БД.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        '--path',
        default=os.path.join(ROOT, 'olympiads_with_real_solutions.py'),
        help='Путь к Python-файлу с переменной OLYMPIADS_DB.',
    )
    ap.add_argument('--dry-run', action='store_true', help='Без commit.')
    ap.add_argument(
        '--force-replace', action='store_true',
        help='Перезаписывать condition/solution/answer даже если в БД '
             'не плейсхолдер.',
    )
    args = ap.parse_args()

    if not os.path.isfile(args.path):
        print(f'❌ Файл не найден: {args.path}', file=sys.stderr)
        sys.exit(1)

    enrich(args.path, dry_run=args.dry_run, force_replace=args.force_replace)


if __name__ == '__main__':
    main()
