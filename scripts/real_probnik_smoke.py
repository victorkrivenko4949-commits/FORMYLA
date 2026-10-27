# -*- coding: utf-8 -*-
"""REAL_PROBNIK_V1 — smoke-тест (28.10.2026, ревью-патч 2).

Проверяет контракт «занятие-пробник = реальный вариант выбранной
олимпиады из каталога задач олимпиад»:
  1) коды вариантов уникальны во всех 8 каталогах пользователя
     (включая туры Турнира городов), этап — слаг+хеш названия+хеш
     состава, длина <= 50, СТАБИЛЬНЫ при добавлении в каталог нового
     (более свежего) года; «Ломоносов» исключён — каталог недостоверен;
  2) порядок выдачи: свежий год -> старый, внутри года простой ->
     сложный; класс — ТОЛЬКО точный (нет класса — нет пробника);
  3) НЕДЕЛЯ ДИАГНОСТИКИ (по ДАТЕ начала premium, 7 календарных дней)
     не занимает слоты: после 7 диагностических уроков следующий —
     слот 1 (метод), пробник — слот 6; граница дня 7 корректна и при
     подписке, начатой среди дня; пропуски, пересекающие границу
     недели, разносятся правильно (долги недели 1 — практика);
  4) сценарий: неделя диагностики -> блок -> пробник открывается с
     задачами каталога -> сдача завершает занятие (maybe_complete_probnik);
  5) ЧЕРТЕЖИ: figures_for_task возвращает URL /static/olymp_figures/...,
     файлы существуют, нумерация совпадает с БД (включая дубли номеров);
     отрендеренный onclick передаёт путь строкой; peek не пишет в БД;
  6) БЕЗ ЗАМЕЩЕНИЙ: нет prep-плана -> занятие-пробник без кода
     (CTA на выбор олимпиады), закрывается сдачей; несуществующий
     каталог -> None; сбой создания не «перепрыгивает» на следующий
     вариант (порядок = peek);
  7) несколько пропущенных занятий-пробников -> разные варианты;
  8) длительность: только подтверждённый регламент ВсОШ (60/90/120),
     двухдневные этапы — None (без таймера); сбой посреди начисления
     долгов не оставляет «наполовину начисленных» записей (rollback).

Запуск из корня репозитория: python scripts/real_probnik_smoke.py
"""
import os
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

FAILURES = []


def check(name, cond, extra=''):
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}"
          + (f' — {extra}' if extra and not cond else ''))
    if not cond:
        FAILURES.append(name)


class FakeDate(date):
    """date с подменяемым today(): экземпляры адаптируются для sqlite3."""

    _today = None

    @classmethod
    def today(cls):
        return cls._today

    def __conform__(self, protocol):
        if protocol is sqlite3.PrepareProtocol:
            return self.isoformat()


def main() -> int:
    from flask import Flask
    from models import db

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        import models  # noqa: F401 — регистрирует все таблицы
        import models_curator  # noqa: F401
        import models_olympiad  # noqa: F401
        from models import OlympiadPrep, PrepPlan, Subscription, User
        from models_curator import CuratorState
        from models_olympiad import OlympiadTask, Probnik

        db.create_all()
        import curator.session_plan as sp
        import services.real_probnik as rp
        from services.real_probnik import (
            ensure_real_probnik, figures_for_task, next_real_probnik,
            ordered_variants, peek_next_probnik, variant_codes,
        )

        today = date.today()

        def set_fake_day(d):
            FakeDate._today = FakeDate(d.year, d.month, d.day)
            sp.date = FakeDate

        # ── Данные пользователя 1: prep-план vsosh, 9 класс, premium ────
        db.session.add(User(id=1, email='smoke1@formyla.test', name='S1'))
        db.session.add(User(id=5, email='smoke5@formyla.test', name='S5'))
        db.session.add(User(id=7452, email='smoke7452@formyla.test', name='S7'))
        op = OlympiadPrep(slug='vsosh', name='ВсОШ', short_name='ВсОШ')
        db.session.add(op)
        db.session.flush()
        db.session.add(PrepPlan(user_id=1, olympiad_id=op.id,
                                 start_date=today - timedelta(days=8),
                                 target_date=today + timedelta(days=180)))
        db.session.add(CuratorState(user_id=1, grade=9))
        # premium начат 7 дней назад СРЕДИ ДНЯ (14:30): неделя диагностики —
        # 7 календарных дней по ДАТЕ начала (today-7 .. today-1);
        # today — первый день блока (метод)
        started = datetime.combine(today - timedelta(days=7),
                                   datetime.min.time()).replace(hour=14, minute=30)
        db.session.add(Subscription(user_id=1, plan='premium_intense',
                                    status='active', started_at=started))
        db.session.commit()
        set_fake_day(today)
        sp.ensure_tables()  # curator_lessons (SQLite для теста)

        # ── 1) Коды вариантов: уникальность и стабильность ────────────
        print('\n1) Коды вариантов (8 олимпиад пользователя)')
        SLUGS = ['vsosh', 'turnir-gorodov', 'euler', 'kurchatov',
                 'vysshaya-proba', 'matprazdnik', 'mmo',
                 'pokori-vorobievy-gory']
        rx = re.compile(r'^real-[a-z0-9]+(-[a-z0-9]+)*-\d{4}-[a-z0-9]+(-[a-z0-9]+)*-g\d+$')
        for slug in SLUGS:
            pairs = variant_codes(slug, None)  # ближайший класс из каталога
            check(f'{slug}: есть варианты', len(pairs) > 0)
            codes = [c for c, _ in pairs]
            check(f'{slug}: коды уникальны', len(set(codes)) == len(codes),
                  str(codes[:6]))
            check(f'{slug}: коды <= 50 симв.', all(len(c) <= 50 for c in codes))
            check(f'{slug}: формат кода (однословный этап)',
                  all(rx.match(c) for c in codes), str(codes[:3]))
        # «Ломоносов»: каталог недостоверен (задачи 9 класса приписаны
        # к чужим PDF, группы — неполные фрагменты; проверено по
        # официальным работам 2023/24 и 2024/25) — выдача приостановлена
        check('lomonosov: исключён из выдачи (каталог недостоверен)',
              variant_codes('lomonosov', None) == []
              and ordered_variants('lomonosov', 9) == [])
        # класс — ТОЛЬКО точный: класса нет в каталоге — пробника нет
        check('vsosh: нет 6-х классов — нет пробника (без подмены)',
              ordered_variants('vsosh', 6) == [])
        tg = [c for c, _ in variant_codes('turnir-gorodov', None)]
        check('turnir-gorodov: туры не схлопываются в один код',
              len(set(tg)) == len(tg))
        # уникальность по ВСЕМ каталогам индекса (не только SLUGS; ревю
        # 28.10.2026, раунд 7) и ВСЕМ фактически выдаваемым классам;
        # карантинный lomonosov должен давать ПУСТУЮ выдачу
        import json as _json
        with open(os.path.join(HERE, 'data', 'olymp_catalog',
                               '_index.json'), encoding='utf-8') as fh:
            all_slugs = [e['slug'] for e in _json.load(fh)]
        check('все каталоги индекса покрыты проверкой',
              {rp._file_slug(s) for s in SLUGS} <= set(all_slugs),
              str({rp._file_slug(s) for s in SLUGS} - set(all_slugs)))
        for slug in all_slugs:
            if slug == 'lomonosov':
                check('lomonosov: выдача пуста (карантин каталога)',
                      variant_codes(slug, 9) == [])
                continue
            tasks_all = rp._load_catalog(slug) or []
            grades_all = sorted({rp._as_int(t.get('grade'))
                                 for t in tasks_all
                                 if isinstance(t, dict)
                                 and rp._as_int(t.get('grade'))})
            for g in grades_all:
                codes_g = [c for c, _ in variant_codes(slug, g)]
                check(f'{slug} g{g}: коды уникальны',
                      len(set(codes_g)) == len(codes_g),
                      str(codes_g[:6]))

        # стабильность: добавление нового (свежего) года НЕ меняет коды
        # старых — сохранённые real-* в curator_lessons остаются валидными
        vsosh_codes_before = {c for c, _ in variant_codes('vsosh', 9)}
        orig_load = rp._load_catalog

        def _load_with_new_year(slug):
            data = orig_load(slug)
            if slug != 'vsosh' or not data:
                return data
            fresh = datetime.now().year + 1
            extra = [dict(t, year=fresh) for t in data
                     if t.get('year') == max(x.get('year') or 0 for x in data)]
            return data + extra

        rp._load_catalog = _load_with_new_year
        try:
            vsosh_codes_after = {c for c, _ in variant_codes('vsosh', 9)}
        finally:
            rp._load_catalog = orig_load
        check('добавление свежего года не меняет коды старых лет',
              vsosh_codes_before <= vsosh_codes_after
              and len(vsosh_codes_after) > len(vsosh_codes_before))

        # стабильность при КОЛЛИЗИИ: новый этап в ТОМ ЖЕ году с тем же
        # нормализованным слогом НЕ меняет код уже выданного варианта
        # (ревью 28.10.2026: «тег только при коллизии» это ломал —
        # старый код получал суффикс и история назначений рвалась)
        school_codes_before = {
            c for c, v in variant_codes('vsosh', 9) if 'кольн' in v['round']}
        school_variant_before = [
            v for _, v in variant_codes('vsosh', 9) if 'кольн' in v['round']][0]

        def _load_with_colliding_stage(slug):
            data = orig_load(slug)
            if slug != 'vsosh' or not data:
                return data
            base_year = school_variant_before['year']
            dup = [dict(t, round='Школьный этап (параллельный вариант)')
                   for t in data
                   if t.get('year') == base_year
                   and 'кольн' in str(t.get('round') or '')
                   and str(t.get('grade')) == '9']
            return data + dup

        rp._load_catalog = _load_with_colliding_stage
        try:
            pairs_after = variant_codes('vsosh', 9)
            codes_after = {c for c, _ in pairs_after}
            school_after = {
                c for c, v in pairs_after if 'кольн' in v['round']}
        finally:
            rp._load_catalog = orig_load
        check('новый этап с тем же слогом не меняет старые коды',
              school_codes_before <= school_after
              and school_codes_before <= codes_after,
              f'было: {sorted(school_codes_before)}, '
              f'стало: {sorted(school_after)}')
        check('коллизия разрешается тегами: оба варианта в выдаче',
              len(school_after) >= len(school_codes_before) + 1
              and len(school_after) == len(set(school_after)),
              str(sorted(school_after)))

        # ── 2) Порядок выдачи: свежий год, простой этап раньше ──────────
        print('\n2) Порядок выдачи (vsosh, 9 класс)')
        variants = ordered_variants('vsosh', 9)
        check('vsosh: есть варианты для 9 класса', len(variants) > 0)
        years = [v['year'] for v in variants]
        check('годы по убыванию (свежий -> старый)',
              years == sorted(years, reverse=True), str(years))
        ranks = []
        for v in (x for x in variants if x['year'] == years[0]):
            name = v['round'].lower()
            for key, rank in (('школьн', 1), ('муниципальн', 3),
                              ('региональн', 6), ('заключительн', 8)):
                if key in name:
                    ranks.append(rank)
                    break
            else:
                ranks.append(4)
        check('внутри года: этапы от простого к сложному',
              ranks == sorted(ranks), str(ranks))

        # ── 3) Неделя диагностики: слоты и границы ──────────────────────
        print('\n3) Неделя диагностики (по дате, граница дня 7)')
        check('день 7 (today-1) — диагностический',
              sp._is_diag_date(1, today - timedelta(days=1)))
        check('день 8 (today) — НЕ диагностический (подписка среди дня)',
              not sp._is_diag_date(1, today))
        # 7 диагностических уроков недели 1: today-7 .. today-1
        diag_lessons = [{'seq': i,
                         'assigned_date': sp.date(today.year, today.month, today.day)
                         - timedelta(days=8 - i)}
                        for i in range(1, 8)]
        check('после недели 1: seq 8 -> слот 1 (метод)',
              sp._eff_slot(1, diag_lessons, 8) == 1,
              str(sp._eff_slot(1, diag_lessons, 8)))
        check('seq 12 -> слот 5', sp._eff_slot(1, diag_lessons, 12) == 5)
        check('seq 13 -> слот 6 (пробник)',
              sp._eff_slot(1, diag_lessons, 13) == 6)
        check('seq 14 -> слот 1 (новый блок)',
              sp._eff_slot(1, diag_lessons, 14) == 1)
        check('урок на today (первый день блока) не считается диагностикой',
              sp._diag_count(diag_lessons + [
                  {'seq': 8, 'assigned_date': sp.date(today.year, today.month,
                                                       today.day)}],
                  sp._week1_end_date(1)) == 7)

        # ── 4) Полный сценарий: диагностика -> блок -> пробник ──────────
        print('\n4) Сценарий «неделя диагностики -> блок -> пробник»')
        for i in range(1, 8):  # неделя 1: 7 уроков практики (тест+задачи дня)
            db.session.execute(sp.text(
                f"INSERT INTO {sp.TABLE_NAME} (user_id, seq, lesson_type, "
                f"status, assigned_date) VALUES (1, :seq, 'practice', "
                f"'completed', :d)"),
                {'seq': i, 'd': today - timedelta(days=8 - i)})
        db.session.commit()

        lesson = sp.current_lesson(1)
        check('после недели 1 первое занятие — МЕТОД (слот 1)',
              lesson and lesson['lesson_type'] == 'method',
              str(lesson and lesson['lesson_type']))
        # проходим метод + 3 практики: слоты 2..5 (seq 9..12)
        for _ in range(4):
            sp.complete_current_lesson(1)
            cur = sp._to_date(sp._lessons(1)[-1]['assigned_date'])
            set_fake_day(cur + timedelta(days=1))
            lesson = sp.current_lesson(1)
        check('пятое занятие блока — практика (слот 5)',
              lesson and lesson['lesson_type'] == 'practice',
              str(lesson and lesson['lesson_type']))
        # следующий день — занятие-пробник (слот 6, seq 13)
        sp.complete_current_lesson(1)
        cur = sp._to_date(sp._lessons(1)[-1]['assigned_date'])
        set_fake_day(cur + timedelta(days=1))
        lesson = sp.current_lesson(1)
        check('занятие 6 блока — ПРОБНИК',
              lesson and lesson['lesson_type'] == 'probnik',
              str(lesson and lesson['lesson_type']))
        # код всегда содержит тег названия (ревью 28.10.2026) — берём
        # из генератора, а не хардкодим
        first_code = [c for c, v in variant_codes('vsosh', 9)
                     if v['year'] == years[0] and 'кольн' in v['round']][0]
        check('пробник — реальный вариант каталога (свежий год, школьный этап)',
              lesson and lesson.get('probnik_code') == first_code,
              f"{lesson and lesson.get('probnik_code')} != {first_code}")

        p = Probnik.query.filter_by(code=first_code).first()
        check('Probnik создан (type=stage, published)',
              p is not None and p.type == 'stage' and p.is_published)
        tasks = OlympiadTask.query.filter_by(probnik_id=p.id).all()
        check('в пробнике есть задачи каталога (>= 3)',
              len(tasks) >= 3, f'{len(tasks)} задач')
        check('длительность школьного этапа ВсОШ (9 класс) — 120 минут',
              p.duration_minutes == 120, str(p.duration_minutes))
        # в каталоге ВсОШ нет 6-х классов: вариант 9-го класса
        # используем как синтетический (создание напрямую) — проверяем
        # регламент длительности 5-6 классов
        c9, v9 = variant_codes('vsosh', 9)[0]
        code6 = c9.rsplit('-g', 1)[0] + '-g6'
        g6 = ensure_real_probnik(code6, dict(v9, grade=6), 'vsosh')
        g6_p = Probnik.query.filter_by(code=code6).first()
        check('длительность школьного этапа (5–6 класс) — 90 минут',
              g6_p.duration_minutes == 90, str(g6_p.duration_minutes))
        check('пороги НЕ выдуманы (None)',
              p.threshold_prize is None and p.threshold_winner is None)
        check('сдача пробника завершает занятие',
              sp.maybe_complete_probnik(1, first_code) is True)

        # порядок не «перепрыгивается»: next и peek дают один вариант
        peek_a = peek_next_probnik('vsosh', 9, {first_code})
        made_a = next_real_probnik('vsosh', 9, {first_code})
        check('next == peek (порядок не расходится)',
              peek_a and made_a and peek_a['code'] == made_a['code'],
              f"{peek_a} vs {made_a}")

        # ── 5) Чертежи, нумерация и peek ────────────────────────────────
        print('\n5) Чертежи и нумерация')
        fig_task = None
        for t in tasks:
            figs = figures_for_task(first_code, t.number)
            if figs.get('condition'):
                fig_task = (t.number, figs)
                break
        if fig_task is None:
            # региональный этап 2025, 9 класс: задача 6 с чертежом.
            # (code, variant) берём из ОДНОГО вызова генератора — объекты
            # ordered_variants пересоздаются, identity-сравнение неверно;
            # ревю 28.10.2026, раунд 6)
            reg = [(c, v) for c, v in variant_codes('vsosh', 9)
                   if v['year'] == 2025 and 'егион' in v['round']]
            check('есть вариант с чертежами для проверки', bool(reg))
            if reg:
                reg_code, reg_v = reg[0]
                made = ensure_real_probnik(reg_code, reg_v, 'vsosh')
                check('создан региональный вариант (номер слота без коллизии)',
                      made is not None)
                reg_p = Probnik.query.filter_by(code=reg_code).first()
                check('двухдневный этап: БЕЗ таймера (duration=None)',
                      reg_p.duration_minutes is None,
                      str(reg_p.duration_minutes))
                figs = figures_for_task(reg_code, '6')
                if figs.get('condition'):
                    fig_task = ('6', figs)
        check('у задач каталога есть чертежи (fig_statement)',
              fig_task is not None)
        if fig_task:
            _, figs = fig_task
            f = figs['condition'][0]
            check('URL чертежа — /static/olymp_figures/...',
                  f['url'].startswith('/static/olymp_figures/'), f['url'])
            fs_path = os.path.join(HERE, 'static', 'olymp_figures', f['file'])
            check('файл чертежа существует на диске',
                  os.path.isfile(fs_path), fs_path)

        # разбивка по документам + хеш состава: синтетический каталог с
        # двумя параллельными комплектами (одни и те же номера в разных
        # PDF) — оба варианта выдаются с РАЗНЫМИ кодами, чертежи
        # находятся по коду (ревю 28.10.2026; «Ломоносов» для этого
        # исключён — его каталог недостоверен)
        synth = []
        for doc, tag in (('a.pdf', 'A'), ('b.pdf', 'B')):
            for num in (1, 2, 3):
                synth.append({
                    'uid': f'syn-{tag}-{num}', 'year': 2024,
                    'round': 'Финал', 'grade': '9', 'num': num,
                    'source': f'https://example.org/{doc}',
                    'text': f'Условие {tag}{num}', 'solution': '',
                    'fig_statement': ([f'FINAL_FIGURES/syn-{tag}.png']
                                      if num == 2 else []),
                })
        orig_load = rp._load_catalog

        def _load_synth(slug):
            return synth if slug == 'synthetic' else orig_load(slug)

        # стабильность при добавлении параллельного комплекта: сначала
        # в каталоге только документ A — сохраняем его код; затем
        # добавляем B (тот же год/этап/класс/номера, другие uid):
        # код A НЕ меняется, код B отличается (ревю 28.10.2026, раунд 6)
        synth_a_only = [t for t in synth if 'A' in str(t.get('uid'))]

        def _load_synth_a(slug):
            return synth_a_only if slug == 'synthetic' else orig_load(slug)

        rp._load_catalog = _load_synth_a
        try:
            pairs_a = variant_codes('synthetic', 9)
            check('только документ A: один вариант', len(pairs_a) == 1,
                  str([c for c, _ in pairs_a]))
            code_a_first = pairs_a[0][0]
        finally:
            rp._load_catalog = orig_load

        rp._load_catalog = _load_synth
        try:
            syn_pairs = variant_codes('synthetic', 9)
            check('параллельные комплекты: оба варианта в выдаче',
                  len(syn_pairs) == 2, str([c for c, _ in syn_pairs]))
            check('добавление комплекта B НЕ меняет код A',
                  any(c == code_a_first for c, _ in syn_pairs)
                  and code_a_first in {c for c, _ in syn_pairs},
                  f'{code_a_first} vs {[c for c, _ in syn_pairs]}')
            check('параллельные комплекты: РАЗНЫЕ коды (хеш состава)',
                  len({c for c, _ in syn_pairs}) == 2,
                  str([c for c, _ in syn_pairs]))
            code_a, v_a = next(
                (c, v) for c, v in syn_pairs
                if any('A2' in (t.get('text') or '') for t in v['tasks']))
            made = ensure_real_probnik(code_a, v_a, 'synthetic')
            check('создан вариант из разбивки по документам',
                  made is not None)
            syn_p = Probnik.query.filter_by(code=code_a).first()
            db_nums = {t.number: t for t in OlympiadTask.query.filter_by(
                probnik_id=syn_p.id).all()}
            check('нумерация БД = нумерация каталога',
                  sorted(db_nums) == ['1', '2', '3'], str(sorted(db_nums)))
            figs = figures_for_task(code_a, '2')
            check('черчежи варианта из doc-split находятся по коду',
                  figs['condition'] == [
                      {'file': 'FINAL_FIGURES/syn-A.png',
                       'url': '/static/olymp_figures/FINAL_FIGURES/syn-A.png'}],
                  str(figs))
        finally:
            rp._load_catalog = orig_load
        # дубли номеров внутри одного документа: нумерация «день.номер»
        # консистентна между БД и поиском чертежей (единая функция
        # _variant_task_numbers используется обоими путями)
        dup_tasks = [synth[0],
                     dict(synth[0], uid='syn-A1-d2', day=2,
                          text='Условие A1, второй день')]
        dup_nums = dict(rp._variant_task_numbers(dup_tasks))
        check('дубли номеров получают уникальные номера (день.номер)',
              len(dup_nums) == 2 and len(set(dup_nums)) == 2
              and sorted(dup_nums) != ['1', '1'], str(sorted(dup_nums)))
        text_match = all(
            (t.get('text') or '').strip() in {
                'Условие A1', 'Условие A1, второй день'}
            for t in dup_nums.values())
        check('дубль номера указывает на свою задачу каталога', text_match)

        # отрендеренный onclick передаёт путь СТРОКОЙ (не «голым» выражением)
        import jinja2
        fig_src = open(os.path.join(HERE, 'templates/olympiad/task.html'),
                       encoding='utf-8').read()
        m = re.search(r'\{% for fig in condition_figures %\}(.*?)\{% endfor %\}',
                     fig_src, re.S)
        block = ('{% set fig = figs[0] %}' + m.group(1))
        rendered = jinja2.Template(block).render(
            figs=[{'file': 'FINAL_FIGURES/x.png',
                   'url': '/static/olymp_figures/FINAL_FIGURES/x.png'}])
        check("onclick передаёт путь строкой: openOnBoard('...')",
              "openOnBoard('/static/olymp_figures/FINAL_FIGURES/x.png')"
              in rendered, rendered[:200])
        check('img src указывает на каталогные чертежи',
              'src="/static/olymp_figures/FINAL_FIGURES/x.png"' in rendered)

        before = Probnik.query.count()
        peek = peek_next_probnik('vsosh', 9, {first_code})
        check('peek возвращает следующий вариант',
              peek is not None and peek['code'] != first_code, str(peek))
        check('peek НЕ пишет в БД', Probnik.query.count() == before)
        preview = sp.upcoming_probnik_preview(1)
        check('upcoming_probnik_preview (контекст куратора)',
              preview is not None and preview.get('code'), str(preview))

        # ── 6) Без замещений ───────────────────────────────────────────
        print('\n6) Без замещений')
        db.session.add(CuratorState(user_id=5, grade=9))
        db.session.commit()
        # без prep-плана: 5 уроков практики вручную, 6-й — пробник без кода
        for i in range(1, 6):
            db.session.execute(sp.text(
                f"INSERT INTO {sp.TABLE_NAME} (user_id, seq, lesson_type, "
                f"status, assigned_date) VALUES (5, :seq, 'practice', "
                f"'completed', :d)"),
                {'seq': i, 'd': today - timedelta(days=6 - i)})
        db.session.commit()
        set_fake_day(today)
        lesson2 = sp.current_lesson(5)
        check('без prep-плана: пробник без кода (нет подмены)',
              lesson2 and lesson2['lesson_type'] == 'probnik'
              and not lesson2.get('probnik_code'),
              str(lesson2 and (lesson2['lesson_type'],
                               lesson2.get('probnik_code'))))
        si5 = sp.session_info(5)
        check('CTA пробника без кода — на выбор олимпиады (course-probnik)',
              si5.get('cta_url') == '/olympiads/course-probnik',
              str(si5.get('cta_url')))
        check('БЕЗ подмены: пробник без кода НЕ закрывается чужой сдачей',
              sp.maybe_complete_probnik(5, 'whatever-code') is False)
        # ротация не застревает: на следующий день занятие уходит в долг
        set_fake_day(today + timedelta(days=1))
        sp._sync(5)
        l5 = sp._lessons(5)
        skipped5 = [l for l in l5 if l['lesson_type'] == 'probnik']
        check('незакрытый пробник уходит в долг (ротация продолжается)',
              skipped5 and skipped5[0]['status'] == 'skipped',
              str([(l['seq'], l['status']) for l in l5]))
        set_fake_day(today)
        si5b = sp.session_info(5)
        check('после неудачной сдачи session_info не падает',
              si5b.get('active') in (True, False))
        check('несуществующий каталог -> None (нет подмены)',
              next_real_probnik('no-such-olympiad', 9, set()) is None)

        # длительность: только подтверждённый регламент ВсОШ
        mmo_made = next_real_probnik('mmo', 9, set())
        check('не-ВсОШ (mmo): вариант найден', mmo_made is not None)
        mmo_p = Probnik.query.filter_by(code=mmo_made['code']).first()
        check('не-ВсОШ: длительность НЕ выдумана (None, без таймера)',
              mmo_p.duration_minutes is None, str(mmo_p.duration_minutes))

        # ── 7) Несколько пропущенных пробников -> разные варианты ────────
        print('\n7) Пропущенные пробники без подмены')
        db.session.add(CuratorState(user_id=7452, grade=9))
        db.session.flush()
        db.session.add(PrepPlan(user_id=7452, olympiad_id=op.id,
                                start_date=today - timedelta(days=14),
                                target_date=today + timedelta(days=180)))
        db.session.commit()
        # один урок 14 дней назад (назначен, не закрыт) -> 13 дней долгов
        db.session.execute(sp.text(
            f"INSERT INTO {sp.TABLE_NAME} (user_id, seq, lesson_type, "
            f"status, assigned_date) VALUES (7452, 1, 'practice', "
            f"'assigned', :d)"), {'d': today - timedelta(days=14)})
        db.session.commit()
        sp._sync(7452)  # _advance_stale: seq 2..14, пробники на слотах 6 и 12
        lessons3 = sp._lessons(7452)
        probnik_lessons = [l for l in lessons3 if l['lesson_type'] == 'probnik']
        codes3 = [l['probnik_code'] for l in probnik_lessons]
        check('за пропущенные дни назначено >= 2 занятий-пробников',
              len(probnik_lessons) >= 2, str(codes3))
        check('каждому пропущенному пробнику — СВОЙ вариант',
              len(set(codes3)) == len(codes3)
              and all(c and c.startswith('real-') for c in codes3),
              str(codes3))
        check('долги вставлены одной транзакцией (seq 1..14)',
              [l['seq'] for l in lessons3] == list(range(1, 15)),
              str([l['seq'] for l in lessons3]))

        # ── 8) Пропуск, пересекающий границу недели диагностики ─────────
        print('\n8) Пропуск через границу недели 1')
        db.session.execute(sp.text(
            f"DELETE FROM {sp.TABLE_NAME} WHERE user_id = 5"))
        db.session.commit()
        # premium у ученика 5: начало 10 дней назад; урок seq 1 был на день 0,
        # дальше 9 дней пропуска: дни 1..6 — диагностика (практика),
        # день 7 — метод (слот 1), дни 8..9 — практика
        db.session.add(Subscription(
            user_id=5, plan='premium_intense', status='active',
            started_at=datetime.combine(today - timedelta(days=10),
                                        datetime.min.time())))
        db.session.execute(sp.text(
            f"INSERT INTO {sp.TABLE_NAME} (user_id, seq, lesson_type, "
            f"status, assigned_date) VALUES (5, 1, 'practice', "
            f"'assigned', :d)"), {'d': today - timedelta(days=10)})
        db.session.commit()
        sp._sync(5)
        lessons5 = sp._lessons(5)
        types5 = {l['seq']: l['lesson_type'] for l in lessons5}
        check('долги за дни 1..6 недели 1 — практика (диагностика)',
              all(types5.get(s) == 'practice' for s in range(2, 8)),
              str(types5))
        check('долг за день 7 (первый день блока) — МЕТОД',
              types5.get(8) == 'method', str(types5))
        check('долги за дни 8..9 — практика',
              all(types5.get(s) == 'practice' for s in (9, 10)), str(types5))

        # ── 9) Атомарность: сбой посреди начисления долгов ──────────────
        print('\n9) Атомарность долгов')
        db.session.execute(sp.text(
            f"DELETE FROM {sp.TABLE_NAME} WHERE user_id = 7452"))
        db.session.execute(sp.text(
            f"INSERT INTO {sp.TABLE_NAME} (user_id, seq, lesson_type, "
            f"status, assigned_date) VALUES (7452, 1, 'practice', "
            f"'assigned', :d)"), {'d': today - timedelta(days=5)})
        db.session.commit()
        orig_diag = sp._diag_count
        sp._diag_count = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError('искусственный сбой посреди начисления'))
        sp._sync(7452)  # ловит сбой и откатывает транзакцию
        sp._diag_count = orig_diag
        after_fail = sp._lessons(7452)
        check('сбой посреди долгов не оставляет полуготовых записей',
              [l['seq'] for l in after_fail] == [1],
              str([l['seq'] for l in after_fail]))
        sp._sync(7452)  # повторный запуск после сбоя — долги начисляются
        after_recover = sp._lessons(7452)
        check('после сбоя повторная синхронизация начисляет долги',
              [l['seq'] for l in after_recover] == [1, 2, 3, 4, 5],
              str([l['seq'] for l in after_recover]))

        # ── CTA ─────────────────────────────────────────────────────────
        print('\nCTA')
        si = sp.session_info(1)
        check('session_info не падает', si.get('active') in (True, False))

    print('\n' + '=' * 60)
    if FAILURES:
        print(f'ПРОВАЛЕНО: {len(FAILURES)}')
        for f in FAILURES:
            print(f'  - {f}')
        return 1
    print('ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ')
    return 0


if __name__ == '__main__':
    sys.exit(main())
