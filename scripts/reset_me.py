#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
scripts/reset_me.py — полный сброс прогресса ученика до состояния новичка.

Использование:
    python scripts/reset_me.py <email или user_id> [--yes]

Что делает:
    - Сбрасывает CuratorState (mu, sigma, level_by_section, prep_state,
      onboarding_done, все флаги)
    - Удаляет DailyTaskSet и DailyTaskItem за все даты
    - Удаляет историю ответов, показанные task_id, результаты тестов
    - Перед удалением делает бэкап в backups/ с датой и временем
    - Работает ТОЛЬКО с локальной базой (localhost/127.0.0.1)
"""

import os
import sys
import shutil
import argparse
from datetime import datetime, timezone

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app, db
from models import User, TestResult, AdaptiveTestResult
from daily_tasks.models import DailyTaskSet, DailyTaskItem
from models_curator import CuratorState

def check_local_db():
    """Проверяем, что подключение идёт к локальной базе."""
    uri = flask_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    uri_lower = uri.lower()
    if 'localhost' in uri_lower or '127.0.0.1' in uri_lower or 'sqlite' in uri_lower:
        return True
    return False


def find_user(email_or_id):
    """Найти пользователя по email или ID."""
    try:
        uid = int(email_or_id)
        user = db.session.get(User, uid)
        if user:
            return user
    except ValueError:
        pass

    user = User.query.filter_by(email=email_or_id).first()
    if user:
        return user

    return None


def create_backup():
    """Создать бэкап базы данных с датой и временем."""
    uri = flask_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if uri.startswith('sqlite:///'):
        db_path = uri.replace('sqlite:///', '')
        if not os.path.isabs(db_path):
            db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), db_path)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backups')
        os.makedirs(backup_dir, exist_ok=True)
        backup_name = f'database_before_reset_{timestamp}.db'
        backup_path = os.path.join(backup_dir, backup_name)
        shutil.copy2(db_path, backup_path)
        print(f'[OK] Бэкап создан: {backup_path}')
        return backup_path
    else:
        print('[!]️  Бэкап для не-SQLite баз не поддерживается. Пропускаем.')
        return None


def reset_user(email_or_id, auto_yes=False):
    """Основная логика сброса."""
    deleted = {}

    with flask_app.app_context():
        print(f' Ищем пользователя: {email_or_id}')
        user = find_user(email_or_id)
        if not user:
            print(f'[ERROR] Пользователь не найден: {email_or_id}')
            sys.exit(1)

        print(f' Найден: User id={user.id}, email={user.email or "нет email"}')

        if not auto_yes:
            confirm = input(f'\n[!]️  ВНИМАНИЕ! Будет ПОЛНОСТЬЮ удалён прогресс пользователя {user.email or user.id}.\n'
                            f'   Это необратимо (кроме бэкапа). Продолжить? [y/N]: ')
            if confirm.lower() != 'y':
                print('[ERROR] Отмена.')
                sys.exit(0)
        else:
            print('   -> Авто-подтверждение (--yes)')

        # ── 1. CuratorState ──────────────────────────────────────────
        cs = CuratorState.query.filter_by(user_id=user.id).first()
        if cs:
            print(f'\n CuratorState до сброса:')
            print(f'   onboarding_done={cs.onboarding_done}')
            print(f'   prep_state keys={list(cs.prep_state.keys()) if isinstance(cs.prep_state, dict) else "—"}')
            print(f'   level_by_section={cs.level_by_section}')
            print(f'   level_mu={cs.level_mu}  level_sigma={cs.level_sigma}')
            # Сброс ВСЕХ полей до дефолтов, а не удаление строки
            cs.onboarding_done = False
            cs.prep_state = {}          # очищаем onboarding, monthly_cycle и т.д.
            cs.level_mu = 3.0           # DEFAULT_MU — чтобы record_result НЕ вызывал set_prior
            cs.level_sigma = 1.5        # DEFAULT_SIGMA — и не ставил onboarding_done=True
            cs.level_by_section = None
            cs.level_by_theme = None
            cs.probe_json = None
            cs.level_updated_at = None
            cs.target_olympiads = '[]'
            cs.grade = None
            cs.goal_text = None
            cs.last_diagnostic_id = None
            cs.summary = None
            db.session.commit()
            deleted['CuratorState'] = 1
            print('   -> CuratorState сброшен (onboarding_done=False, prep_state={}, level_mu=3.0, level_sigma=1.5)')
        else:
            print('\n CuratorState: не найден — создаём пустой')
            cs = CuratorState(user_id=user.id, onboarding_done=False, prep_state={})
            db.session.add(cs)
            db.session.commit()
            deleted['CuratorState'] = 0

        # ── 2. DailyTaskSet + DailyTaskItem ──────────────────────────
        sets = DailyTaskSet.query.filter_by(user_id=user.id).all()
        set_count = len(sets)
        item_count = 0
        for s in sets:
            items = DailyTaskItem.query.filter_by(daily_set_id=s.id).all()
            item_count += len(items)
            for it in items:
                db.session.delete(it)
            db.session.delete(s)
        db.session.commit()
        deleted['DailyTaskSet'] = set_count
        deleted['DailyTaskItem'] = item_count
        print(f'\n DailyTaskSet: удалено {set_count} наборов ({item_count} задач)')

        # ── 3. TestResult ────────────────────────────────────────────
        tr_count = TestResult.query.filter_by(user_id=user.id).delete()
        db.session.commit()
        deleted['TestResult'] = tr_count
        print(f' TestResult: удалено {tr_count} записей')

        # ── 4. AdaptiveTestResult ────────────────────────────────────
        atr_count = AdaptiveTestResult.query.filter_by(user_id=user.id).delete()
        db.session.commit()
        deleted['AdaptiveTestResult'] = atr_count
        print(f' AdaptiveTestResult: удалено {atr_count} записей')

        # ── 5. ChatMessage ───────────────────────────────────────────
        from models import ChatMessage
        cm_count = ChatMessage.query.filter_by(user_id=user.id).delete()
        db.session.commit()
        deleted['ChatMessage'] = cm_count
        print(f' ChatMessage: удалено {cm_count} сообщений')

        # ── 6. UserTopicProgress ─────────────────────────────────────
        from models import UserTopicProgress
        utp_count = UserTopicProgress.query.filter_by(user_id=user.id).delete()
        db.session.commit()
        deleted['UserTopicProgress'] = utp_count
        print(f' UserTopicProgress: удалено {utp_count} записей')

        # ── 7. TaskSolution ──────────────────────────────────────────
        try:
            from models import TaskSolution
            ts_count = TaskSolution.query.filter_by(user_id=user.id).delete()
            db.session.commit()
            deleted['TaskSolution'] = ts_count
            print(f' TaskSolution: удалено {ts_count} записей')
        except Exception:
            pass

        # ── 8. DailyQuest ────────────────────────────────────────────
        try:
            from models import DailyQuest
            dq_count = DailyQuest.query.filter_by(user_id=user.id).delete()
            db.session.commit()
            deleted['DailyQuest'] = dq_count
            print(f' DailyQuest: удалено {dq_count} записей')
        except Exception:
            pass

        # ── Итог ────────────────────────────────────────────────────
        print(f'\n{"="*60}')
        print(f' ИТОГО удалено:')
        total_rows = 0
        for table, count in deleted.items():
            print(f'   {table}: {count} строк')
            total_rows += count
        print(f'   ─────────────────')
        print(f'   ВСЕГО: {total_rows} строк')
        print(f'\n[OK] Пользователь {user.email or user.id} полностью сброшен до состояния новичка.')
        print(f'   Можно заходить заново и проходить онбординг.')


def main():
    parser = argparse.ArgumentParser(
        description='Полный сброс прогресса ученика до состояния новичка.'
    )
    parser.add_argument('email_or_id', help='Email или ID пользователя для сброса')
    parser.add_argument('--yes', '-y', action='store_true', help='Пропустить подтверждение')
    args = parser.parse_args()

    if not check_local_db():
        uri = flask_app.config.get('SQLALCHEMY_DATABASE_URI', '?')
        print(f'[ERROR] ОШИБКА: скрипт работает ТОЛЬКО с локальной базой (localhost/127.0.0.1/sqlite).')
        print(f'   Текущая строка подключения: {uri}')
        print(f'   Отказываюсь работать на production!')
        sys.exit(1)

    print(f' База данных: {flask_app.config.get("SQLALCHEMY_DATABASE_URI", "?")}')
    print(f'[OK] База локальная — можно работать.\n')

    create_backup()
    reset_user(args.email_or_id, auto_yes=args.yes)


if __name__ == '__main__':
    main()
