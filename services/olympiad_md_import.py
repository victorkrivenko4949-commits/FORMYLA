# -*- coding: utf-8 -*-
"""Парсер `formyla_vsosh9_13_ready_methods_combined.md` для seed-функции.

Извлекает 13 методов (E14, F1, F8, B1, F3, F2, D12, D1, C5a, F4a, E5, A2, E10)
с расширенными разделами (по ~10 примеров на метод, 7 семейств и т.д.).
Логика парсинга позаимствована из scripts/import_vsosh9_10_methods_md.py,
но обёрнута в idempotent ORM-обновление вместо raw SQLite.
"""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple


_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 'data', 'olympiads'
)
MD_PATH_PRIMARY = os.path.join(_DATA_DIR, 'formyla_vsosh9_13_ready_methods_combined.md')
MD_PATH_FALLBACK = os.path.join(_DATA_DIR, 'formyla_vsosh9_10_methods_combined.md')

TARGET_CODES = (
    'E14', 'F1', 'F8',
    'B1', 'F3', 'F2', 'D12', 'D1', 'C5a', 'F4a', 'E5', 'A2', 'E10',
)

_RE_METHOD_HEAD = re.compile(r'^##\s+([A-H][0-9]+[a-z]?)\s*:\s*(.+?)\s*$')
_RE_H2 = re.compile(r'^##\s+(.+?)\s*$')

_SECTION_KEY_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'^дизайн[-–\s]?макет'), 'design'),
    (re.compile(r'^статья для ученика'), 'why'),
    (re.compile(r'^почему\b'), 'why'),
    (re.compile(r'^реальные ориентиры'), 'real'),
    (re.compile(r'^самые популярные идеи'), 'main_idea'),
    (re.compile(r'^главная идея'), 'main_idea'),
    (re.compile(r'^базовый алгоритм'), 'algorithm'),
    (re.compile(r'^как распознать'), 'recognize'),
    (re.compile(r'^карта выбора идеи'), 'algorithm'),
    (re.compile(r'^7 семейств'), 'families'),
    (re.compile(r'^лестница задач.*7 семейств'), 'families'),
    (re.compile(r'^решённый пример'), 'families'),
    (re.compile(r'^решенный пример'), 'families'),
    (re.compile(r'^как (решать|писать)'), 'olympiad_strategy'),
    (re.compile(r'^типовые ошибки'), 'mini_test'),
    (re.compile(r'^мини[-–\s]?тест'), 'mini_test'),
    (re.compile(r'^финальный конспект'), 'summary'),
]


def _classify_h2(title: str) -> Optional[str]:
    t = title.strip().lower()
    t = re.sub(r'\s+[a-h][0-9]+[a-z]?$', '', t).strip()
    for pattern, key in _SECTION_KEY_RULES:
        if pattern.search(t):
            return key
    return None


def split_methods(md_text: str) -> Dict[str, str]:
    """Режет MD по '## CODE: …' границам метода."""
    lines = md_text.splitlines()
    methods: Dict[str, List[str]] = {}
    current: Optional[str] = None
    for line in lines:
        m = _RE_METHOD_HEAD.match(line)
        if m:
            current = m.group(1)
            methods[current] = []
            continue
        if current is not None:
            methods[current].append(line)
    return {c: '\n'.join(v).strip() for c, v in methods.items()}


def split_into_sections(method_text: str) -> Dict[str, str]:
    """Режет внутри метода по `## …` подзаголовкам, классифицирует ключ."""
    sections: Dict[str, List[str]] = {}
    current_key = '__intro__'
    current_lines: List[str] = []

    for line in method_text.splitlines():
        m = _RE_H2.match(line)
        if m:
            if current_lines:
                sections.setdefault(current_key, []).extend(current_lines)
                sections[current_key].append('')
            title = m.group(1)
            key = _classify_h2(title) or f'__unknown__:{title}'
            current_key = key
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.setdefault(current_key, []).extend(current_lines)
    return {k: '\n'.join(v).strip() for k, v in sections.items() if v}


def assemble_columns(section_blocks: Dict[str, str]) -> Dict[str, str]:
    """Собирает 6 колонок БД из именованных секций."""
    def _join(keys: List[str]) -> str:
        parts = [section_blocks.get(k, '').strip() for k in keys]
        return '\n\n'.join(p for p in parts if p)

    return {
        'definition_md':         _join(['why', 'real']),
        'main_theorems_md':      _join(['main_idea']),
        'typical_techniques_md': _join(['recognize', 'algorithm']),
        'worked_example_md':     _join(['families']),
        'triggers_md':           _join(['olympiad_strategy']),
        'pitfalls_md':           _join(['mini_test', 'summary']),
    }


def parse_md_file(path: str) -> Dict[str, Dict[str, str]]:
    """Парсит MD-файл и возвращает {method_code: {column_name: text}}."""
    if not os.path.exists(path):
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        md_text = f.read()
    by_code = split_methods(md_text)
    result: Dict[str, Dict[str, str]] = {}
    for code, method_text in by_code.items():
        sections = split_into_sections(method_text)
        cols = assemble_columns(sections)
        # Сохраняем только методы с непустым worked_example_md (это
        # основной сигнал что MD действительно содержит контент).
        if cols.get('worked_example_md'):
            result[code] = cols
    return result


def import_rich_md_into_theory(db, TheoryBlock) -> int:
    """Обогащает 13 «полных» методов расширенным контентом из MD.

    Возвращает количество обновлённых методов. Idempotent: если в БД
    `worked_example_md` уже длиннее (> 500 символов), считаем что
    «расширенная» версия уже там и не трогаем (это даёт переключатель:
    seed_theory_only уже залил короткий вариант из JSON — теперь
    перезаписываем длинным).
    """
    src_path = MD_PATH_PRIMARY if os.path.exists(MD_PATH_PRIMARY) else MD_PATH_FALLBACK
    parsed = parse_md_file(src_path)
    if not parsed:
        print(f'[THEORY-MD] No MD content parsed from {src_path}')
        return 0

    print(f'[THEORY-MD] MD source: {src_path} ({len(parsed)} methods)')
    updated = 0
    for code, cols in parsed.items():
        try:
            tb = TheoryBlock.query.filter_by(method_code=code).first()
            if tb is None:
                continue
            # Idempotency: пропускаем, если уже большое содержимое.
            cur_fam = (tb.worked_example_md or '').strip()
            if len(cur_fam) >= 2000 and cur_fam == cols.get('worked_example_md', '').strip():
                continue
            changed = False
            for fld, val in cols.items():
                v = (val or '').strip()
                if not v:
                    continue
                old = getattr(tb, fld, None) or ''
                old_stripped = old.strip()
                # Перезаписываем, если:
                #   - поле пустое,
                #   - или новое СУЩЕСТВЕННО длиннее (хотя бы в 1.5×),
                #   - или существующий контент очень короткий (< 300 символов,
                #     т.е. stub/заглушка, а не полноценный текст).
                if (not old_stripped) or len(v) >= max(int(len(old) * 1.5), 800) or len(old_stripped) < 300:
                    setattr(tb, fld, v)
                    changed = True
            if changed:
                updated += 1
        except Exception as e:
            print(f'[THEORY-MD] row failed ({code}): {e}')

    try:
        db.session.commit()
        print(f'[THEORY-MD] Rich content imported for {updated} methods')
    except Exception as e:
        db.session.rollback()
        print(f'[THEORY-MD] commit failed: {e}')
        return 0
    return updated
