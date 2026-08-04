# -*- coding: utf-8 -*-
"""
tests/conftest.py — FORMYLA pytest fixtures (F0 block).

Contains:
  - Preserved raw-sqlite3 fixtures for subscription tests (renamed):
    db, service, sub_test_user, sub_premium_user
  - New ORM fixtures for acceptance testing:
    app, client, test_user, five_anchor_tasks,
    figure_build_job, daily_set_with_items,
    test_svg_files, auth_client

ALL new ORM fixtures use tmp_path — the production database under
instance/ is NEVER opened for write.  App context is pushed once in
'app' and stays alive for the whole test duration so that ORM objects
returned by dependent fixtures remain attached to their session.
"""

import sqlite3
import pytest


# ══════════════════════════════════════════════════════════════════════
# Preserved raw-sqlite3 fixtures (subscription tests)
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def db():
    """In-memory SQLite connection with subscription tables."""
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            current_plan TEXT DEFAULT 'free',
            plan_expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL DEFAULT 'free',
            status TEXT NOT NULL DEFAULT 'active',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            payment_method TEXT,
            payment_id TEXT,
            amount_rub INTEGER,
            is_trial INTEGER DEFAULT 0,
            is_beta_access INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE usage_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date DATE NOT NULL,
            tasks_completed INTEGER DEFAULT 0,
            ai_explanations_used INTEGER DEFAULT 0,
            tokens_consumed INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0,
            UNIQUE(user_id, date),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX idx_sub_user ON subscriptions(user_id);
        CREATE INDEX idx_sub_status ON subscriptions(status);
        CREATE INDEX idx_usage_user_date ON usage_daily(user_id, date);
    """)
    conn.commit()

    yield conn
    conn.close()


@pytest.fixture
def service(db):
    """SubscriptionService backed by in-memory sqlite3."""
    from services.subscription import SubscriptionService
    return SubscriptionService(db)


@pytest.fixture
def sub_test_user(db):
    """Creates a test user in raw sqlite3, returns user_id (int).

    Renamed from 'test_user' to avoid collision with the ORM 'test_user'
    fixture introduced in block F0.
    """
    cursor = db.execute(
        "INSERT INTO users (email, current_plan) VALUES (?, 'free')",
        ('test@example.com',)
    )
    db.commit()
    return cursor.lastrowid


@pytest.fixture
def sub_premium_user(db, service):
    """User with active Premium subscription (raw sqlite3, returns user_id).

    Renamed from 'premium_user' to match the sub_ prefix convention.
    """
    cursor = db.execute(
        "INSERT INTO users (email, current_plan) VALUES (?, 'free')",
        ('premium@example.com',)
    )
    db.commit()
    user_id = cursor.lastrowid
    service.activate_premium(user_id, plan='premium_monthly', is_beta=True)
    return user_id


# ══════════════════════════════════════════════════════════════════════
# F0 — ORM fixtures on temporary SQLite via tmp_path
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def app(tmp_path):
    """Flask app configured with a temporary SQLite database.

    Uses tmp_path (file-based) so that multiple connections can share
    the same database (e.g. background queue processors).  In-memory
    SQLite is NOT used because each connection gets its own empty DB
    with ``:memory:``.

    The app context is pushed for the entire fixture lifetime so that
    ORM objects returned by dependent fixtures stay attached.  After
    the test, db.drop_all() is called and the context is popped.
    """
    from flask import Flask
    from flask_login import LoginManager
    from models import db as _db, User
    import models              # noqa: F401 ensure all models loaded
    import daily_tasks.models  # noqa: F401 ensure DailyTaskSet/Item
    import models_curator      # noqa: F401 curator models

    db_path = tmp_path / "test_formyla.db"
    uri = 'sqlite:///' + db_path.as_posix()

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.config['SQLALCHEMY_DATABASE_URI'] = uri
    test_app.config['SECRET_KEY'] = 'test-f0-secret-key'
    test_app.config['WTF_CSRF_ENABLED'] = False
    test_app.config['SERVER_NAME'] = 'localhost'

    _db.init_app(test_app)
    for ep in ['profile','logout','misc','about','pricing','welcome','leaderboard','secrets','probniks','figures','topics','friends','chat','daily','problems','matstat','subscription','social','onboarding','privacy','register','login','verify_code','olympiads']: test_app.add_url_rule('/'+ep, ep, lambda e=ep: e)
    test_app.add_url_rule('/', 'index', lambda: 'index')

    # Set up Flask-Login for @login_required decorators
    login_manager = LoginManager()
    login_manager.init_app(test_app)

    @login_manager.user_loader
    def _load_user(user_id):
        return _db.session.get(User, int(user_id))

    # Register blueprints needed for route tests
    from daily_tasks import daily_tasks_bp
    test_app.register_blueprint(daily_tasks_bp)
    from routes.prep import prep_bp
    test_app.register_blueprint(prep_bp)
    from routes.figures import figures_bp
    test_app.register_blueprint(figures_bp)
    from routes.figures_generator import figures_gen_bp
    test_app.register_blueprint(figures_gen_bp)
    from routes.parent_teacher import parent_teacher_bp
    test_app.register_blueprint(parent_teacher_bp)
    from routes.dashboard_settings import dashboard_settings_bp
    test_app.register_blueprint(dashboard_settings_bp)
    try:
        from routes.olympiad import olympiad_bp
        test_app.register_blueprint(olympiad_bp)
    except Exception:
        pass
    try:
        from routes.olympiad_prep import olympiad_prep_bp
        test_app.register_blueprint(olympiad_prep_bp)
    except Exception:
        pass
    try:
        from routes.account import account_bp
        test_app.register_blueprint(account_bp)
    except Exception:
        pass

    # Push context once and keep it for all dependent fixtures and the test.
    ctx = test_app.app_context()
    ctx.push()
    _db.create_all()

    yield test_app

    _db.session.remove()
    _db.drop_all()
    ctx.pop()


@pytest.fixture
def client(app):
    """Flask test client for the temporary app."""
    return app.test_client()


@pytest.fixture
def test_user(app):
    """Create one ORM User record in the temporary DB.

    Returns the User object after commit.  Values are synthetic and
    recognisably test-only.  The app context is still active (pushed
    by the 'app' fixture), so the object remains attached.
    """
    from models import db, User

    user = User(
        email='test_f0@example.invalid',
        nickname='test_f0_user',
        is_guest=False,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def five_anchor_tasks(app):
    """Create exactly five AdaptiveTask records, one per anchor category.

    Anchors in order: algebra, number_theory, geometry, combinatorics, logic.
    All have difficulty_level=3.  Text is synthetic and marked [TEST].
    UIDs match data/anchors.jsonl exactly (grade 5, one per section).
    """
    from models import db, AdaptiveTask

    anchors_spec = [
        ('A_G5_ALG', 'algebra'),
        ('A_G5_NT', 'number_theory'),
        ('A_G5_GEO', 'geometry'),
        ('A_G5_COMB', 'combinatorics'),
        ('A_G5_LOG', 'logic'),
    ]

    tasks = []
    for uid, section in anchors_spec:
        task = AdaptiveTask(
            class_level=5,
            difficulty_level=3,
            topic=section,
            subtopic='F0 test subtopic',
            task_text=(
                f'[TEST] Синтетическое условие для проверки якоря {uid}, '
                f'не является реальной олимпиадной задачей.'
            ),
            solution='Тестовое решение F0.',
            criteria_1_point='Критерий 1 балл (F0).',
            criteria_2_points='Критерий 2 балла (F0).',
            subject=section,
            source_id=uid,
            source=f'[TEST] anchor {uid}',
        )
        db.session.add(task)
        tasks.append(task)
    db.session.commit()
    return tasks


@pytest.fixture
def figure_build_job(app, test_user, five_anchor_tasks):
    """Create one FigureBuildJob with status='queued'.

    Linked to the first anchor task (algebra) and test_user.
    model_name is set to 'test-model' (a stub, not a real API model).
    """
    from models import db, FigureBuildJob
    from datetime import datetime

    job = FigureBuildJob(
        user_id=test_user.id,
        problem_text=f'[TEST] Figure job for {five_anchor_tasks[0].source_id}',
        status='queued',
        model_name='test-model',
        credit_charged=False,
        has_aux=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()
    return job


@pytest.fixture
def daily_set_with_items(app, test_user, five_anchor_tasks):
    """Create one DailyTaskSet with five DailyTaskItems.

    One item per anchor, preserved order: algebra, number_theory,
    geometry, combinatorics, logic.
    """
    from models import db
    from daily_tasks.models import DailyTaskSet, DailyTaskItem
    from datetime import date

    dset = DailyTaskSet(
        user_id=test_user.id,
        target_date=date.today(),
        status='ready',
        total_cost_usd=0.0,
    )
    db.session.add(dset)
    db.session.flush()  # get dset.id

    items = []
    for pos, task in enumerate(five_anchor_tasks, 1):
        item = DailyTaskItem(
            daily_set_id=dset.id,
            position=pos,
            task_text=task.task_text,
            subject=task.subject,
            topic=task.topic,
            figure_status='no_description',
            has_aux=False,
            is_calibration=False,
            opus_iterations=0,
            is_flagged=False,
            status='pending',
        )
        db.session.add(item)
        items.append(item)

    db.session.commit()
    return dset


@pytest.fixture
def test_svg_files(tmp_path):
    """Create two synthetic SVG files for CH6 layer testing.

    Returns (base_path, aux_path) as pathlib.Path objects.
    base: no stroke-dasharray.  aux: contains stroke-dasharray.
    Both are synthetic stubs, NOT output of the real geometry engine.
    """
    base_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg"'
        ' viewBox="0 0 620 620" width="620" height="620">\n'
        '  <rect width="620" height="620" fill="#070C18"/>\n'
        '  <g transform="translate(60,60)">\n'
        '    <line x1="50" y1="50" x2="250" y2="250"'
        ' stroke="#4C7DFF" stroke-width="2"/>\n'
        '    <text x="100" y="100" fill="#E6EBF7"'
        ' font-family="Satoshi, system-ui" font-size="14">A</text>\n'
        '    <text x="200" y="200" fill="#E6EBF7"'
        ' font-family="Satoshi, system-ui" font-size="14">B</text>\n'
        '  </g>\n'
        '</svg>'
    )

    aux_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg"'
        ' viewBox="0 0 620 620" width="620" height="620">\n'
        '  <rect width="620" height="620" fill="#070C18"/>\n'
        '  <g transform="translate(60,60)">\n'
        '    <line x1="50" y1="50" x2="250" y2="250"'
        ' stroke="#4C7DFF" stroke-width="2"/>\n'
        '    <line x1="150" y1="50" x2="150" y2="250"'
        ' stroke="#E5AC3A" stroke-width="1.5" stroke-dasharray="6,4"/>\n'
        '    <text x="100" y="100" fill="#E6EBF7"'
        ' font-family="Satoshi, system-ui" font-size="14">A</text>\n'
        '    <text x="200" y="200" fill="#E6EBF7"'
        ' font-family="Satoshi, system-ui" font-size="14">B</text>\n'
        '  </g>\n'
        '</svg>'
    )

    base_path = tmp_path / "test_figure.svg"
    aux_path = tmp_path / "test_figure_aux.svg"
    base_path.write_text(base_svg, encoding='utf-8')
    aux_path.write_text(aux_svg, encoding='utf-8')
    return (base_path, aux_path)


@pytest.fixture
def three_import_tasks(app):
    """Create three AdaptiveTask records for I1 import tests.

    UIDs: i1_ok, i1_ok2, i1_broken — match synthetic SVG files
    created in the test (ok.svg, ok2.svg + ok2_aux.svg, broken.svg).
    All have difficulty_level=3. Text is synthetic and marked [TEST].
    """
    from models import db, AdaptiveTask

    spec = [
        ('i1_ok', 'algebra'),
        ('i1_ok2', 'geometry'),
        ('i1_broken', 'combinatorics'),
    ]

    tasks = []
    for uid, section in spec:
        task = AdaptiveTask(
            class_level=5,
            difficulty_level=3,
            topic=section,
            subtopic='I1 test subtopic',
            task_text=(
                f'[TEST] Synthetic figure import test task {uid}, '
                f'not a real olympiad problem.'
            ),
            solution='Test solution I1.',
            criteria_1_point='Criterion 1 point (I1).',
            criteria_2_points='Criterion 2 points (I1).',
            subject=section,
            source_id=uid,
            source=f'[TEST] import I1 {uid}',
        )
        db.session.add(task)
        tasks.append(task)
    db.session.commit()
    return tasks


@pytest.fixture
def auth_client(client, test_user):
    """Authorised test client — _user_id is set to test_user.id.

    Ready for GET/POST without repeated login in every test.
    """
    with client.session_transaction() as sess:
        sess['_user_id'] = str(test_user.id)
    return client


# ══════════════════════════════════════════════════════════════════════
# T4 — Trial access fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def user_trial_active(app):
    """User with trial_started_at = 1 hour ago, no subscription."""
    from models import db, User
    from datetime import datetime, timedelta, timezone

    user = User(
        email='trial_active@test.invalid',
        nickname='trial_active',
        is_guest=False,
        trial_started_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def user_trial_expired(app):
    """User with trial_started_at = 2 days ago, no subscription."""
    from models import db, User
    from datetime import datetime, timedelta, timezone

    user = User(
        email='trial_expired@test.invalid',
        nickname='trial_expired',
        is_guest=False,
        trial_started_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def user_subscribed(app):
    """User with plan_expires_at = 30 days in future, trial may be expired."""
    from models import db, User
    from datetime import datetime, timedelta, timezone

    user = User(
        email='subscribed@test.invalid',
        nickname='subscribed_user',
        is_guest=False,
        trial_started_at=datetime.now(timezone.utc) - timedelta(days=2),
        plan_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        current_plan='premium_monthly',
    )
    db.session.add(user)
    db.session.commit()
    return user


# ══════════════════════════════════════════════════════════════════════
# T9 — Priority queue fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def user_free(app):
    """User without any subscription or trial."""
    from models import db, User

    user = User(
        email='free@test.invalid',
        nickname='free_user',
        is_guest=False,
        trial_started_at=None,
        plan_expires_at=None,
        current_plan='free',
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def five_priority_jobs(app, user_subscribed, user_free):
    """Five FigureBuildJob records in 'queued' status.

    Three from user_subscribed (priority=1) and two from user_free
    (priority=0), with staggered created_at timestamps.
    """
    from models import db, FigureBuildJob
    from datetime import datetime, timedelta

    base = datetime.utcnow() - timedelta(minutes=30)
    jobs = []

    # 3 subscriber jobs (priority=1) — created first
    for i in range(3):
        job = FigureBuildJob(
            user_id=user_subscribed.id,
            problem_text=f'[TEST] T9 subscriber job {i + 1}',
            status='queued',
            model_name='test-model',
            credit_charged=False,
            has_aux=False,
            priority=1,
            created_at=base + timedelta(seconds=i * 10),
            updated_at=base + timedelta(seconds=i * 10),
        )
        db.session.add(job)
        jobs.append(job)

    # 2 free user jobs (priority=0) — created after
    for i in range(2):
        job = FigureBuildJob(
            user_id=user_free.id,
            problem_text=f'[TEST] T9 free job {i + 1}',
            status='queued',
            model_name='test-model',
            credit_charged=False,
            has_aux=False,
            priority=0,
            created_at=base + timedelta(seconds=30 + i * 10),
            updated_at=base + timedelta(seconds=30 + i * 10),
        )
        db.session.add(job)
        jobs.append(job)

    db.session.commit()
    return jobs


# user_trial_expired_no_sub is identical to user_trial_expired;
# use user_trial_expired directly.


# ══════════════════════════════════════════════════════════════════════
# T10 — Parent / Teacher fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def teacher_user(app):
    """User with role='teacher'."""
    from models import db, User

    user = User(
        email='teacher_t10@example.invalid',
        nickname='teacher_t10',
        role='teacher',
        is_guest=False,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def student_users(app):
    """Three users with role='student'."""
    from models import db, User

    users = []
    for i in range(1, 4):
        user = User(
            email=f'student_t10_{i}@example.invalid',
            nickname=f'student_t10_{i}',
            role='student',
            is_guest=False,
        )
        db.session.add(user)
        users.append(user)
    db.session.commit()
    return users


@pytest.fixture
def parent_user(app, student_users):
    """User with role='parent', child_email pointing to first student."""
    from models import db, User

    user = User(
        email='parent_t10@example.invalid',
        nickname='parent_t10',
        role='parent',
        child_email=student_users[0].email,
        is_guest=False,
    )
    db.session.add(user)
    db.session.commit()
    return user


@pytest.fixture
def group_with_students(app, teacher_user, student_users):
    """One T10Group with three T10GroupMember rows."""
    from models import db, T10Group, T10GroupMember

    g = T10Group(
        name='T10 Test Group',
        teacher_id=teacher_user.id,
        invite_code='ABCDEF',
    )
    db.session.add(g)
    db.session.flush()

    for s in student_users:
        gm = T10GroupMember(group_id=g.id, user_id=s.id, role='student')
        db.session.add(gm)
    db.session.commit()
    return g
