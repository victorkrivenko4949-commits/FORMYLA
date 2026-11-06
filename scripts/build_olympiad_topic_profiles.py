# -*- coding: utf-8 -*-
"""scripts/build_olympiad_topic_profiles.py — частоты тем олимпиад по классам.

Владелец (06.11.2026): «анализируешь олимпиаду (например, Росатом),
смотришь самое популярное и даёшь в первую очередь, а потом уже
оставшееся — для каждого класса и каждой из 11 олимпиад».

Скрипт раскладывает реальные задачи каталога (data/olymp_catalog/*.json)
по темам банка задач дня (G{класс}_T{n}) по ключевым словам условия,
считает частоту тем для каждой пары «олимпиада + класс» и пишет
data/olympiad_topic_profiles.json. Темы без задач в банке для класса
отбрасываются (выдать по ним задачи дня нечем).

Запуск:  python scripts/build_olympiad_topic_profiles.py
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
from typing import Dict, List, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CATALOG = os.path.join(ROOT, 'data', 'olymp_catalog')
OUT = os.path.join(ROOT, 'data', 'olympiad_topic_profiles.json')

SKIP_FILES = {'_index.json', 'quarantine.json', 'collision_survivors.json',
              'rawtex_leftovers.json', 'other.json'}

# Понятие → (регулярки по условию, регулярка по названию темы реестра).
# Порядок — приоритет при равных очках.
CONCEPTS = [
    ('stereo', [r'пирамид', r'\bкуб(а|е|ом)?\b', r'призм', r'тетраэдр', r'\bсфер', r'\bшар',
                r'конус', r'цилиндр', r'параллелепипед', r'пространств'],
     r'Пространствен|Отрезки|Длины'),
    ('cutting', [r'разреж', r'разрез', r'клетчат', r'клетк', r'доск', r'домино', r'замощ',
                 r'покры', r'фигурк', r'уголк'],
     r'Разрезан|Клетчат'),
    ('angles', [r'\bугол', r'\bугл', r'\\angle', r'∠', r'градус', r'вписан', r'окружност',
                r'касательн', r'описанн'],
     r'Углы'),
    ('lengths', [r'площад', r'отрез', r'длин', r'периметр', r'медиан', r'биссектрис',
                 r'высот', r'треугольник', r'трапец', r'параллелограмм', r'прямоугольник',
                 r'ромб', r'четырёхугольник', r'четырехугольник'],
     r'Отрезки|Длины|площад'),
    ('construct_geo', [r'постро(ение|йте|ить)', r'циркул', r'симметри', r'поворот',
                       r'гомотет'],
     r'Дополнительные построения'),
    ('games', [r'\bигр(а|у|ы|е|ок|оки|оков)\b', r'по очереди', r'выигр', r'первый игрок',
               r'стратеги', r'ходом', r'\bход\b'],
     r'игры'),
    ('weighing', [r'взвеш', r'чашечн', r'\bвес(ы|ах|ов)\b', r'фальшив', r'переливан',
                  r'\bлитр'],
     r'Взвешива'),
    ('logic', [r'рыцар', r'лжец', r'правду', r'лж[её]т', r'солгал', r'кто из них',
               r'утвержд(ение|ал)'],
     r'Логическ'),
    ('graphs', [r'граф', r'знаком', r'дорог', r'город', r'турнир', r'\bматч', r'сыграл',
                r'команд', r'рукопожат'],
     r'Граф'),
    ('invariants', [r'раскрас', r'покраш', r'покрас', r'цвет', r'инвариант', r'шахматн',
                    r'можно ли получить', r'можно ли добиться'],
     r'Инвариант'),
    ('dirichlet', [r'найдутся', r'хотя бы два', r'хотя бы две', r'дирихле',
                   r'обязательно найд'],
     r'Дирихле'),
    ('processes', [r'операци', r'за один ход', r'каждую минуту', r'каждую секунду',
                   r'процесс', r'алгоритм', r'робот', r'на каждом шаге', r'разрешается'],
     r'Процессы'),
    ('counting', [r'сколькими способами', r'сколько существует', r'сколько (различных|всего|разных)',
                  r'вероятност', r'количество (способов|вариантов)', r'перестановк'],
     r'Комбинаторный подсчёт|Перебор'),
    ('motion', [r'скорост', r'км/ч', r'поезд', r'пешеход', r'автомобил', r'велосипед',
                r'катер', r'догна', r'навстречу', r'\bпуть\b'],
     r'движени'),
    ('work', [r'производительн', r'бассейн', r'наполн', r'смес', r'концентрац', r'процент',
              r'сплав', r'раствор', r'бригад', r'\bработ'],
     r'Работа|Проценты|Части'),
    ('time', [r'возраст', r'лет назад', r'календар', r'часы показ', r'\bлет\b.*\bстарше'],
     r'Время'),
    ('trig', [r'\\sin', r'\\cos', r'\\tg', r'\\ctg', r'\bsin\b', r'\bcos\b', r'\btg\b',
              r'\\log', r'\blog', r'логарифм', r'производн', r'параметр',
              r'при каких значениях', r'\\arc', r'\barc'],
     r'Тригонометр|аналитическ|уравнения и системы|Уравнения и системы'),
    ('functional', [r'функциональн', r'f\s*\(\s*x', r'f\s*\(\s*\w\s*\+'],
     r'Функциональн'),
    ('sequences', [r'последовательност', r'прогресси', r'a_\{?n', r'рекуррент',
                   r'\bчлен(ов|ы)?\b'],
     r'Последовательност'),
    ('primes', [r'просто(е|го|му|м) числ', r'простых чис', r'простые чис', r'\bНОД\b',
                r'\bНОК\b', r'делител'],
     r'Простые'),
    ('diophantine', [r'в целых числах', r'в натуральных числах', r'натуральные решения',
                     r'целые решения', r'целочисленн'],
     r'Диофант|целых числах'),
    ('digits', [r'цифр', r'десятичн', r'систем[аеуы]? счисления', r'ребус', r'звёздочк',
                r'запис(ь|ано|ал|и)'],
     r'Цифр|ребус|систем'),
    ('divisibility', [r'дели(тся|мост|т\b)', r'кратн', r'остат', r'чётн', r'четн',
                      r'нечётн', r'нечетн', r'\\pmod', r'\bmod\b'],
     r'Делимость'),
    ('inequality', [r'неравенств', r'наибольш', r'наименьш', r'максимальн', r'минимальн',
                    r'\\geq?\b', r'\\leq?\b', r'≥', r'≤', r'оцени'],
     r'Неравенств|Оценка'),
    ('polynomial', [r'многочлен', r'трёхчлен', r'трехчлен', r'квадратн(ое|ый|ого)',
                    r'корн(и|ей|ям)', r'виет', r'x\^', r'тождеств', r'разложи'],
     r'Многочлен|тождеств|Алгебраические преобразования'),
    ('equations', [r'уравнени', r'систем[ау] уравнений', r'решите', r'найдите все'],
     r'уравнения и системы|Уравнения и системы|Алгебраические преобразования и уравнения|Алгебраические уравнения'),
    ('example', [r'приведите пример', r'существует ли', r'можно ли', r'пример'],
     r'Арифметические конструкции|Оценка и построение|Числа, цифры|Процессы'),
]

_COMPILED = [(name, [re.compile(p, re.I) for p in pats], re.compile(title_re, re.I))
             for name, pats, title_re in CONCEPTS]


def _load_titles() -> Dict[str, str]:
    with open(os.path.join(ROOT, 'data', 'theme_titles.json'), encoding='utf-8') as f:
        return json.load(f)


def _bank_coverage() -> collections.Counter:
    c = collections.Counter()
    with open(os.path.join(ROOT, 'FORMYLA_BANK.jsonl'), encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                c[(r.get('grade'), r.get('topic'))] += 1
    return c


def themes_for_grade(titles: Dict[str, str], grade: int) -> List[str]:
    pref = f'G{grade}_'
    return sorted((k for k in titles if k.startswith(pref)),
                  key=lambda k: int(k.split('_T')[1]))


def classify(text: str, grade: int, titles: Dict[str, str]) -> Optional[str]:
    """Тема реестра для условия задачи или None (не распознали)."""
    grade_themes = themes_for_grade(titles, grade)
    scored = []
    for order, (name, pats, title_re) in enumerate(_COMPILED):
        score = sum(len(p.findall(text)) for p in pats)
        if score:
            scored.append((-score, order, title_re))
    for _neg, _order, title_re in sorted(scored):
        for tid in grade_themes:
            if title_re.search(titles[tid]):
                return tid
    return None


def _grades_of(raw) -> List[int]:
    out = []
    for part in re.split(r'[-–,/ ]+', str(raw or '')):
        if part.isdigit() and 5 <= int(part) <= 11:
            out.append(int(part))
    if len(out) == 2 and out[1] - out[0] > 1:
        out = list(range(out[0], out[1] + 1))
    return out


def build() -> Dict:
    titles = _load_titles()
    bank = _bank_coverage()
    result: Dict[str, Dict] = {}
    for path in sorted(glob.glob(os.path.join(CATALOG, '*.json'))):
        name = os.path.basename(path)
        if name in SKIP_FILES or name.startswith('_') or 'log' in name:
            continue
        slug = name[:-5]
        with open(path, encoding='utf-8') as f:
            tasks = json.load(f)
        per_grade: Dict[int, collections.Counter] = collections.defaultdict(collections.Counter)
        totals: Dict[int, int] = collections.Counter()
        for t in tasks:
            if t.get('garbled'):
                continue
            text = t.get('text') or ''
            for g in _grades_of(t.get('grade')):
                totals[g] += 1
                tid = classify(text, g, titles)
                if tid and bank.get((g, titles[tid]), 0) > 0:
                    per_grade[g][tid] += 1
        grades_out = {}
        for g in sorted(totals):
            cnt = per_grade[g]
            classified = sum(cnt.values())
            if not classified:
                continue
            grades_out[str(g)] = {
                'n_tasks': totals[g],
                'n_classified': classified,
                'themes': [
                    {'id': tid, 'title': titles[tid], 'count': n,
                     'share': round(n / classified, 3)}
                    for tid, n in sorted(cnt.items(),
                                         key=lambda kv: (-kv[1], int(kv[0].split('_T')[1])))
                ],
            }
        if grades_out:
            result[slug] = grades_out
    return result


def main() -> None:
    data = build()
    titles = _load_titles()
    bank = _bank_coverage()
    bank_themes = {
        str(g): [tid for tid in themes_for_grade(titles, g) if bank.get((g, titles[tid]), 0) > 0]
        for g in range(5, 12)
    }
    payload = {
        '_about': ('Частоты тем реальных задач каталога олимпиад по классам. '
                   'Генерируется scripts/build_olympiad_topic_profiles.py — руками не править.'),
        'olympiads': data,
        'bank_themes': bank_themes,
    }
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    for slug, grades in data.items():
        line = ', '.join(f"{g}кл: {v['n_classified']}/{v['n_tasks']} → {v['themes'][0]['title']}"
                         for g, v in grades.items())
        print(f'{slug}: {line}')


if __name__ == '__main__':
    main()
