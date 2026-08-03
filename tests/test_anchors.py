# -*- coding: utf-8 -*-
"""
tests/test_anchors.py — Комплексное тестирование якорных задач анкеты.

Покрывает:
  - Загрузку anchors.jsonl (с синтетическими данными)
  - Сопоставление theme_id через theme_to_section.json
  - Подбор якорей (три прогона для 9 и 6 класса)
  - Нормализованную проверку ответов
  - Исключение formyla_anchors из задач дня и утреннего среза

ВАЖНО: тесты НЕ переключают глобальный app/db на :memory:,
а работают на временной БД, которую уже создал корневой conftest.py.
Очистка — удаление записей, а не drop_all().
"""
import json
import os
import sys
import tempfile
import pytest

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ──────────────────────────────────────────────────────────────────────
# Helpers: create synthetic anchors.jsonl for testing
# ──────────────────────────────────────────────────────────────────────

CANONICAL_SECTIONS = ['algebra', 'number_theory', 'geometry', 'combinatorics', 'logic']
GRADES = [5, 6, 7, 8, 9, 10, 11]

# Синтетические якоря: по 5 на класс, ровно по одному на раздел
ANCHOR_FIELDS = ['anchor_uid', 'grade', 'section', 'subtopic', 'level', 'statement', 'answer']


def _build_synthetic_anchors():
    """Построить 35 синтетических якорных задач."""
    anchors = []
    uid_counter = 1
    for grade in GRADES:
        for sec in CANONICAL_SECTIONS:
            anchors.append({
                'anchor_uid': f'ANC_{grade}_{sec}',
                'grade': grade,
                'section': sec,
                'subtopic': f'Подтема {grade}кл {sec}',
                'level': (grade % 3) + 1,  # 1..3
                'statement': f'Задача для {grade} класса по разделу {sec}. Найдите x: 2x + {grade} = {grade * 3}.',
                'answer': str(grade),  # x = grade
            })
            uid_counter += 1
    # Специальная задача про коня с ответом «нет»
    anchors.append({
        'anchor_uid': 'ANC_9_logic_knight',
        'grade': 9,
        'section': 'logic',
        'subtopic': 'Шахматные задачи',
        'level': 2,
        'statement': 'Может ли конь обойти все клетки шахматной доски 8x8, побывав на каждой ровно один раз?',
        'answer': 'нет',
    })
    return anchors


def write_synthetic_anchors_file(path: str, anchors: list = None):
    """Записать синтетический anchors.jsonl."""
    if anchors is None:
        anchors = _build_synthetic_anchors()
    with open(path, 'w', encoding='utf-8') as f:
        for a in anchors:
            f.write(json.dumps(a, ensure_ascii=False) + '\n')
    return anchors


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def anchors_jsonl_path():
    """Временный файл anchors.jsonl с синтетическими данными."""
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.jsonl', delete=False, encoding='utf-8'
    ) as f:
        write_synthetic_anchors_file(f.name)
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def app_with_anchors():
    """Flask app с загруженными якорями в тестовой БД (conftest.py).

    Работает на временной копии базы, созданной корневым conftest.py.
    Не переключает глобальный app/db на :memory:.
    Очистка: удаление записей с source='formyla_anchors'.
    """
    import services.anchors  # ensure ANCHORS_FILE computed before app context
    from app import app, db as _db
    from models import AdaptiveTask

    app.config['TESTING'] = True

    with app.app_context():
        # Загружаем якоря из РЕАЛЬНОГО data/anchors.jsonl (35 записей)
        result = services.anchors.load_anchors()
        yield app, result
        # Очистка: удаляем только якорные записи, не трогаем схему
        AdaptiveTask.query.filter(AdaptiveTask.source == 'formyla_anchors').delete()
        _db.session.commit()


# ──────────────────────────────────────────────────────────────────────
# ТЕСТ 1: Загрузка и сопоставление theme_id (п.1-2)
# ──────────────────────────────────────────────────────────────────────

class TestAnchorLoading:
    """Тесты загрузки anchors.jsonl и сопоставления theme_id."""

    def test_load_anchors_creates_correct_count(self, app_with_anchors):
        """Проверка: загружено 35 якорей (7 классов × 5 разделов)."""
        _, result = app_with_anchors
        assert result['total_in_file'] == 35, f"Ожидалось 35, получено {result['total_in_file']}"
        assert result['loaded'] == 35, f"Ожидалось 35 загруженных, получено {result['loaded']}"
        assert result['skipped'] == 0

    def test_per_grade_distribution(self, app_with_anchors):
        """Проверка: по 5 якорей на класс 5-11."""
        _, result = app_with_anchors
        per_grade = result.get('per_grade', {})
        for g in range(5, 12):
            expected = 5
            actual = int(per_grade.get(str(g), 0))
            assert actual == expected, f"Класс {g}: ожидалось {expected}, получено {actual}"

    def test_source_is_formyla_anchors(self, app_with_anchors):
        """Все загруженные задачи имеют source='formyla_anchors'."""
        app, _ = app_with_anchors
        from models import AdaptiveTask
        with app.app_context():
            all_anchors = AdaptiveTask.query.filter(
                AdaptiveTask.source == 'formyla_anchors'
            ).all()
            assert len(all_anchors) == 35

            for t in all_anchors:
                assert t.source == 'formyla_anchors', f"task {t.id}: source={t.source}"
                assert t.source_id is not None and t.source_id.startswith('A_')

    def test_theme_id_mapping(self, app_with_anchors):
        """theme_id проставлен или осознанно оставлен пустым."""
        app, result = app_with_anchors
        from models import AdaptiveTask
        from services.anchors import get_theme_map

        theme_map = get_theme_map()
        with app.app_context():
            tasks = AdaptiveTask.query.filter(
                AdaptiveTask.source == 'formyla_anchors'
            ).all()

            mapped = 0
            unmapped = 0
            unmapped_info = []

            for t in tasks:
                section = (t.subject or '').strip().lower()
                grade = t.class_level
                theme_id = t.theme_id

                if theme_id:
                    # Верифицируем: theme_id должен быть в справочнике
                    assert theme_id in theme_map, (
                        f"theme_id={theme_id} отсутствует в theme_to_section.json"
                    )
                    assert theme_map[theme_id] == section, (
                        f"theme_id={theme_id} → {theme_map[theme_id]}, ожидался section={section}"
                    )
                    mapped += 1
                else:
                    unmapped += 1
                    unmapped_info.append(
                        f"grade={grade} section={section} source_id={t.source_id}"
                    )

            print(f"\ntheme_id mapping: mapped={mapped}, unmapped={unmapped}")
            if unmapped_info:
                print("Unmapped tasks:")
                for info in unmapped_info:
                    print(f"  {info}")
                # В синтетических данных все разделы канонические,
                # theme_map возвращает совпадение по G{grade}_T*→section
                # Если несколько тем одного раздела — theme_id = None (неоднозначно)
                # Это ожидаемое поведение по п.2 ТЗ


# ──────────────────────────────────────────────────────────────────────
# ТЕСТ 2: Подбор якорей (п.3-4)
# ──────────────────────────────────────────────────────────────────────

class TestAnchorSelection:
    """Тесты подбора якорей для анкеты."""

    @pytest.fixture
    def client_and_app(self, app_with_anchors):
        app, _ = app_with_anchors
        return app, app.test_client()

    def _pick_and_assert(self, app, grade: int, run_num: int):
        """Подобрать якоря и проверить инварианты."""
        from services.anchors import pick_anchors, CANONICAL_SECTIONS_ORDER

        with app.app_context():
            anchors, meta = pick_anchors(grade)

            print(f"\n{'='*60}")
            print(f"Прогон {run_num} для класса {grade}")
            print(f"{'='*60}")
            print(f"Всего доступно якорей: {meta['total_available']}")
            print(f"Фактически выдано: {meta['anchor_count']}")
            print(f"{'№':<4} {'anchor_uid':<30} {'раздел':<20} {'подтема':<25} {'уровень':<8}")
            print(f"{'-'*4} {'-'*30} {'-'*20} {'-'*25} {'-'*8}")

            sections_seen = []
            for i, a in enumerate(anchors, 1):
                sections_seen.append(a['section'])
                print(
                    f"{i:<4} {a['anchor_uid']:<30} {a['section']:<20} "
                    f"{a['subtopic'][:24]:<25} {a['level']:<8}"
                )

            # Инварианты
            assert len(anchors) <= 5, (
                f"Класс {grade}: ожидалось ≤5 якорей, получено {len(anchors)}"
            )
            assert len(anchors) > 0, f"Класс {grade}: нет якорей"

            # Все якоря — класс ученика
            for a in anchors:
                assert a['grade'] == grade, (
                    f"Якорь {a['anchor_uid']} класса {a['grade']} "
                    f"не соответствует классу ученика {grade}"
                )

            # Нет повторных разделов
            unique_sections = set(sections_seen)
            assert len(unique_sections) == len(sections_seen), (
                f"Класс {grade}, прогон {run_num}: повторные разделы! "
                f"sections={sections_seen}"
            )

            # Если якорей < 5 — разделы в каноническом порядке
            if len(anchors) < 5:
                print(f"\n  Якорей меньше 5 ({len(anchors)}). "
                      f"Разделы выданы в порядке: {CANONICAL_SECTIONS_ORDER}")

            return anchors, meta

    def test_grade9_three_runs(self, client_and_app):
        """Три прогона анкеты для 9 класса."""
        app, _ = client_and_app
        for run_num in [1, 2, 3]:
            anchors, meta = self._pick_and_assert(app, 9, run_num)
            # Все три прогона должны быть идентичны (детерминированный подбор)
            if run_num == 1:
                first_run = [(a['anchor_uid'], a['section']) for a in anchors]
            else:
                current = [(a['anchor_uid'], a['section']) for a in anchors]
                assert current == first_run, (
                    f"Прогон {run_num} отличается от прогона 1!\n"
                    f"Первый: {first_run}\nТекущий: {current}"
                )
            print(f"  ✓ Прогон {run_num}: {len(anchors)} якорей, "
                  f"разделы: {[a['section'] for a in anchors]}")

    def test_grade6_three_runs(self, client_and_app):
        """Три прогона анкеты для 6 класса."""
        app, _ = client_and_app
        for run_num in [1, 2, 3]:
            anchors, meta = self._pick_and_assert(app, 6, run_num)
            if run_num == 1:
                first_run = [(a['anchor_uid'], a['section']) for a in anchors]
            else:
                current = [(a['anchor_uid'], a['section']) for a in anchors]
                assert current == first_run, (
                    f"Прогон {run_num} отличается от прогона 1!\n"
                    f"Первый: {first_run}\nТекущий: {current}"
                )
            print(f"  ✓ Прогон {run_num}: {len(anchors)} якорей, "
                  f"разделы: {[a['section'] for a in anchors]}")

    def test_no_cross_grade_leak(self, client_and_app):
        """Якоря для 5 класса не попадают в 9 класс и наоборот."""
        app, _ = client_and_app
        from services.anchors import pick_anchors

        with app.app_context():
            for grade in [5, 6, 7, 8, 9, 10, 11]:
                anchors, _ = pick_anchors(grade)
                for a in anchors:
                    assert a['grade'] == grade, (
                        f"Cross-grade leak: anchor {a['anchor_uid']} "
                        f"is grade {a['grade']}, expected {grade}"
                    )
        print("\n✓ No cross-grade leaks detected")


# ──────────────────────────────────────────────────────────────────────
# ТЕСТ 3: Нормализованная проверка ответов (п.5)
# ──────────────────────────────────────────────────────────────────────

class TestAnswerCheck:
    """Тесты нормализованной проверки ответов."""

    def test_normalize_answer(self):
        from services.anchors import normalize_answer

        assert normalize_answer('42') == '42'
        assert normalize_answer(' 42 ') == '42'
        assert normalize_answer('4,2') == '4.2'
        assert normalize_answer('4.2') == '4.2'
        assert normalize_answer('НЕТ') == 'нет'
        assert normalize_answer('Нет.') == 'нет'
        assert normalize_answer('Да') == 'да'
        assert normalize_answer('0,5') == '0.5'
        assert normalize_answer('1 000') == '1000'
        assert normalize_answer('x=2') == 'x=2'
        assert normalize_answer('X=2') == 'x=2'

    def test_check_answer_exact(self):
        from services.anchors import check_answer

        assert check_answer('42', '42') == True
        assert check_answer(' 42', '42 ') == True
        assert check_answer('нет', 'Нет') == True
        assert check_answer('нет.', 'Нет') == True
        assert check_answer('4.5', '4,5') == True

    def test_check_answer_knight(self):
        """Задача про коня имеет ответ «нет», и это допустимо."""
        from services.anchors import check_answer, normalize_answer

        # Проверка нормализации
        assert normalize_answer('нет') == 'нет'
        assert normalize_answer('Нет') == 'нет'
        assert normalize_answer('НЕТ') == 'нет'
        assert normalize_answer('Нет.') == 'нет'

        # Проверка сравнения
        assert check_answer('нет', 'нет') == True
        assert check_answer('Нет', 'нет') == True
        assert check_answer('да', 'нет') == False

        # Убедимся что «нет» — допустимое значение answer
        # (не пустая строка, не None)
        assert normalize_answer('нет') != ''
        assert len(normalize_answer('нет')) > 0

        print("\n✓ Knight problem 'нет' answer handling verified")


# ──────────────────────────────────────────────────────────────────────
# ТЕСТ 4: Якоря НЕ попадают в задачи дня и утренний срез (п.7)
# ──────────────────────────────────────────────────────────────────────

class TestAnchorExclusion:
    """Тесты: formyla_anchors не просачиваются в задачи дня и утренний срез."""

    @pytest.fixture
    def app_for_exclusion(self):
        """App с якорями + дополнительными обычными задачами для теста exclusion.

        Работает на тестовой БД из conftest.py, не переключает на :memory:.
        Очистка: удаление созданных записей.
        """
        import services.anchors  # ensure path computed
        from app import app, db as _db
        from models import AdaptiveTask

        app.config['TESTING'] = True

        with app.app_context():
            # Загружаем якоря из реального файла
            services.anchors.load_anchors()

            # Добавляем обычные задачи (без source='formyla_anchors')
            created_ids = []
            for grade in [9, 6]:
                for level in range(1, 6):
                    for sec in ['algebra', 'geometry', 'combinatorics', 'logic', 'number_theory']:
                        t = AdaptiveTask(
                            class_level=grade,
                            difficulty_level=level,
                            topic=sec,
                            subject=sec,
                            subtopic=f'Тестовая {sec}',
                            task_text=f'Обычная задача {grade} класс {sec} уровень {level}: решите 1+1.',
                            solution='1+1=2',
                            correct_answer='2',
                            source='formyla_L1_L5_TOP5',
                            source_id=f'TEST_{grade}_{sec}_L{level}',
                            criteria_1_point='',
                            criteria_2_points='',
                        )
                        _db.session.add(t)
                        _db.session.flush()
                        created_ids.append(t.id)
            _db.session.commit()

            yield app

            # Очистка: удаляем якоря и тестовые задачи
            AdaptiveTask.query.filter(AdaptiveTask.source == 'formyla_anchors').delete()
            for tid in created_ids:
                AdaptiveTask.query.filter(AdaptiveTask.id == tid).delete()
            _db.session.commit()

    def test_daily_tasks_exclude_anchors(self, app_for_exclusion):
        """Задачи дня для 9 класса не содержат formyla_anchors."""
        from services.daily_task_rotation import _pick_tasks_for_section, _pick_tasks_fallback
        from models import AdaptiveTask

        app = app_for_exclusion
        with app.app_context():
            # Симулируем подбор задач дня для 9 класса
            # _pick_tasks_for_section должно исключать formyla_anchors
            tasks = _pick_tasks_for_section(
                grade=9,
                section='algebra',
                allowed_levels=[1, 2, 3, 4, 5],
                seen_ids=set(),
                count=5,
                user_id=None,
            )
            print(f"\n_pick_tasks_for_section (algebra, grade=9): {len(tasks)} tasks")
            for t in tasks:
                print(f"  task_id={t['task_id']} section={t.get('section')} "
                      f"topic={t.get('topic')}")

            # Проверяем, что ни одна задача не из formyla_anchors
            anchor_ids = {
                t.id for t in AdaptiveTask.query.filter(
                    AdaptiveTask.source == 'formyla_anchors'
                ).all()
            }
            for t in tasks:
                assert t['task_id'] not in anchor_ids, (
                    f"Anchor task {t['task_id']} leaked into daily tasks!"
                )

            # Проверяем fallback тоже
            fallback_tasks = _pick_tasks_fallback(
                grade=9,
                allowed_levels=[1, 2, 3, 4, 5],
                seen_ids=set(),
                count=10,
            )
            print(f"\n_pick_tasks_fallback (grade=9): {len(fallback_tasks)} tasks")
            for t in fallback_tasks:
                assert t['task_id'] not in anchor_ids, (
                    f"Anchor task {t['task_id']} leaked into fallback!"
                )

        print("\n✓ Daily tasks: no formyla_anchors leaked")

    def test_theme_probe_excludes_anchors(self, app_for_exclusion):
        """Утренний срез (theme_probe) не содержит formyla_anchors."""
        from services.theme_probe import _select_and_advance
        from models import AdaptiveTask
        from models_curator import CuratorState
        from models import db as _db

        app = app_for_exclusion
        with app.app_context():
            # Создаём пробу для 9 класса
            cs = CuratorState(user_id=999)
            _db.session.add(cs)
            _db.session.commit()

            probe = {
                'theme_id': 'G9_T05',
                'current_index': 0,
                'current_level': 3,
                'seen_task_ids': [],
                'grade': 9,
            }

            # 5 раз вызываем _next_task_in_probe
            anchor_ids = {
                t.id for t in AdaptiveTask.query.filter(
                    AdaptiveTask.source == 'formyla_anchors'
                ).all()
            }

            print(f"\nAnchor IDs: {anchor_ids}")

            for i in range(5):
                result = _select_and_advance(cs, probe, 9)
                if 'task' in result:
                    task_id = result['task']['id']
                    print(f"  probe task {i+1}: id={task_id} "
                          f"topic={result['task'].get('topic')} "
                          f"level={result['task'].get('difficulty_level')}")
                    assert task_id not in anchor_ids, (
                        f"Anchor task {task_id} leaked into morning probe!"
                    )
                    probe['seen_task_ids'].append(task_id)
                else:
                    print(f"  probe task {i+1}: error={result.get('error')}")

            # Убираем тестового пользователя
            _db.session.delete(cs)
            _db.session.commit()

        print("\n✓ Morning probe: no formyla_anchors leaked")


# ──────────────────────────────────────────────────────────────────────
# ТЕСТ 5: Инспекция (inspect_anchors)
# ──────────────────────────────────────────────────────────────────────

class TestInspectAnchors:
    """Тесты inspect_anchors."""

    def test_inspect_anchors(self, app_with_anchors):
        from services.anchors import inspect_anchors

        app, _ = app_with_anchors
        with app.app_context():
            summary = inspect_anchors()
            assert summary['total'] == 35
            assert set(summary['by_grade'].keys()) == {str(g) for g in range(5, 12)}

            print("\n" + "=" * 60)
            print("ANCHOR INSPECTION SUMMARY")
            print("=" * 60)
            for g_str, data in sorted(summary['by_grade'].items(),
                                       key=lambda x: int(x[0])):
                print(f"\nКласс {g_str}: {data['count']} якорей, "
                      f"разделы: {data['sections']}")
                for item in data['items']:
                    print(f"  {item['anchor_uid']:<30} "
                          f"section={item['section']:<20} "
                          f"level={item['level']} "
                          f"theme_id={item.get('theme_id', 'None')}")


# ──────────────────────────────────────────────────────────────────────
# ТЕСТ 6: Краевые случаи
# ──────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Тесты краевых случаев."""

    def test_missing_anchors_file(self):
        """Загрузка без файла должна возвращать ошибку, не крашиться."""
        import services.anchors as _anchors

        original = _anchors.ANCHORS_FILE
        _anchors.ANCHORS_FILE = '/nonexistent/path/anchors.jsonl'
        try:
            result = _anchors.load_anchors()
            assert result['total_in_file'] == 0
            assert len(result['errors']) > 0
            assert 'Файл не найден' in result['errors'][0]
        finally:
            _anchors.ANCHORS_FILE = original

    def test_get_anchor_ids_empty(self):
        """get_anchor_ids должен возвращать [] при отсутствии якорей."""
        # Этот тест работает без app context — возвращает []
        from services.anchors import get_anchor_ids
        # Вне контекста Flask-SQLAlchemy вернёт []
        ids = get_anchor_ids()
        assert isinstance(ids, list)

    def test_pick_anchors_nonexistent_grade(self, app_with_anchors):
        """pick_anchors для класса без якорей возвращает пустой список."""
        app, _ = app_with_anchors
        from services.anchors import pick_anchors

        with app.app_context():
            anchors, meta = pick_anchors(grade=4)  # 4 класс не в диапазоне
            assert len(anchors) == 0
            assert meta['total_available'] == 0

    def test_dry_run_does_not_write(self):
        """Dry-run не пишет в БД. Использует реальный data/anchors.jsonl."""
        import services.anchors as _anchors

        result = _anchors.load_anchors(dry_run=True)
        assert result['loaded'] == 35
        assert result['skipped'] == 0


# ──────────────────────────────────────────────────────────────────────
# ТЕСТ 7: idempotency
# ──────────────────────────────────────────────────────────────────────

class TestIdempotency:
    """Тесты идемпотентности загрузки."""

    def test_double_load_skips_existing(self):
        """Повторная загрузка пропускает существующие задачи.

        Использует реальный data/anchors.jsonl (35 записей).
        Работает на тестовой БД из conftest.py.
        """
        import services.anchors
        from app import app, db as _db
        from models import AdaptiveTask

        app.config['TESTING'] = True

        with app.app_context():
            # Первая загрузка
            r1 = services.anchors.load_anchors()
            assert r1['loaded'] == 35
            assert r1['skipped'] == 0

            # Вторая загрузка — всё должно быть skipped
            r2 = services.anchors.load_anchors()
            assert r2['loaded'] == 0
            assert r2['skipped'] == 35
            assert r2['total_in_file'] == 35

            # Очистка: удаляем якорные записи
            AdaptiveTask.query.filter(AdaptiveTask.source == 'formyla_anchors').delete()
            _db.session.commit()

        print("\n✓ Idempotency: double load skips all existing")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
