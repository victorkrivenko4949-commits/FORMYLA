# -*- coding: utf-8 -*-
"""
Модели базы данных для FORMYLA
"""
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Модель пользователя (Passwordless Auth + OAuth)"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200))  # Имя пользователя
    nickname = db.Column(db.String(50), unique=True, nullable=True, index=True)  # Уникальный никнейм
    avatar_url = db.Column(db.String(500))  # URL аватарки
    
    # Passwordless Auth
    auth_code = db.Column(db.String(6))  # 6-значный код
    code_expires = db.Column(db.DateTime)  # Срок действия кода
    
    # AI Онбординг
    math_level = db.Column(db.String(20))  # beginner, intermediate, advanced
    ai_report = db.Column(db.Text)  # Персональный отчет от AI
    recommended_topics = db.Column(db.String(200))  # JSON строка с темами
    onboarding_completed = db.Column(db.Boolean, default=False)
    
    # Leaderboard Statistics
    total_problems_solved = db.Column(db.Integer, default=0)  # Всего решено задач
    current_level = db.Column(db.Integer, default=1)  # Текущий уровень (1-10)
    experience_points = db.Column(db.Integer, default=0)  # Очки опыта
    mock_exams_passed = db.Column(db.Integer, default=0)  # Пробников пройдено с >80%
    adaptive_tests_completed = db.Column(db.Integer, default=0)  # Адаптивных тестов завершено
    highest_difficulty_solved = db.Column(db.Integer, default=0)  # Максимальная сложность решенной задачи
    
    # Subscription / Plan
    current_plan = db.Column(db.Text, default='free', server_default='free')
    plan_expires_at = db.Column(db.DateTime, nullable=True)
    
    # Generation limits (free mock / exam generation)
    generation_count_today = db.Column(db.Integer, default=0, server_default='0')
    generation_reset_date = db.Column(db.Date, nullable=True)  # which day the counter belongs to
    gens_extra_purchased = db.Column(db.Integer, default=0, server_default='0')  # extra generations bought (500₽/10)
    gens_unlimited = db.Column(db.Boolean, default=False, server_default='0')  # unlimited flag (1500₽)

    # Figure credits (D4 — geometric figure generation)
    figure_credits = db.Column(db.Integer, default=3, server_default='3')
    # Total figures built by this user (for zero-balance display)
    figures_built = db.Column(db.Integer, default=0, server_default='0')
    
    # Guest access
    is_guest = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    device_id = db.Column(db.String(64), nullable=True, index=True)
    
    # Daily Quest — preferred grade (5-11)
    preferred_grade = db.Column(db.Integer, nullable=True, default=None)

    # ML training consent (152-FZ): user opted in to share solutions for ML
    ml_training_consent = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    
    # Relationships
    topic_progress = db.relationship('UserTopicProgress', backref='user', lazy=True, cascade='all, delete-orphan')
    test_results = db.relationship('AdaptiveTestResult', backref='user', lazy=True, cascade='all, delete-orphan')
    
    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    # Onboarding flag: NULL = user hasn't seen the /about onboarding yet.
    # Set to utcnow() on first visit to /about (or first manual dismissal).
    onboarded_at = db.Column(db.DateTime, nullable=True)

    # Telegram Login Widget — связка с Telegram-аккаунтом
    telegram_id = db.Column(db.String(64), unique=True, nullable=True, index=True)
    telegram_username = db.Column(db.String(64), nullable=True)

    # Состояние диагностической анкеты (JSON), чтобы не хранить в cookie-сессии
    questionnaire_state = db.Column(db.Text, nullable=True)

    # CH10: Kimi review toggles per surface
    kimi_review_probe = db.Column(db.Boolean, default=False, server_default='0')
    kimi_review_daily = db.Column(db.Boolean, default=False, server_default='0')
    kimi_review_method = db.Column(db.Boolean, default=False, server_default='0')

    @property
    def is_admin(self):
        """Админ — user_id == 1 (Victor), email в whitelist или nickname в whitelist.
        Используется в daily_tasks/routes.py для bypass лимита 1 регенерация/день
        и в routes/admin_support.py для доступа к /admin/support.
        """
        if self.id == 1:
            return True
        admin_emails = {
            'kr1venkovictor@yandex.ru',
            'victor.krivenko.4949@gmail.com',
        }
        if (self.email or '').lower() in admin_emails:
            return True
        # Whitelist по nickname — для друзей-модераторов поддержки.
        # Case-insensitive: Lavrik / lavrik / LAVRIK все подходят.
        admin_nicknames = {
            'lavrik',
        }
        return (self.nickname or '').lower() in admin_nicknames

    @property
    def display_name(self):
        """Отображаемое имя: nickname (если не Гость-*) -> name -> email username -> Аноним"""
        # If user has a real nickname (not auto-generated guest)
        if self.nickname and not self.nickname.startswith('Гость-'):
            return self.nickname
        # Yandex display name or real name
        if self.name:
            return self.name
        # Email username (before @)
        if self.email and '@' in self.email and not self.email.startswith('guest_'):
            return self.email.split('@')[0]
        # Fallback to nickname (Гость-XXXX) or Аноним
        return self.nickname or 'Аноним'
    
    def generate_auth_code(self):
        """Генерировать 6-значный код авторизации"""
        import random
        self.auth_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        # Код действителен 10 минут
        from datetime import timedelta
        self.code_expires = datetime.utcnow() + timedelta(minutes=10)
        return self.auth_code
    
    def verify_auth_code(self, code):
        """Проверить код авторизации"""
        if not self.auth_code or not self.code_expires:
            return False
        
        # Проверка срока действия
        if datetime.utcnow() > self.code_expires:
            return False
        
        # Проверка кода
        return self.auth_code == code
    
    def clear_auth_code(self):
        """Очистить код после успешной авторизации"""
        self.auth_code = None
        self.code_expires = None
    
    def complete_onboarding(self, level, report, topics):
        """Сохранить результаты онбординга"""
        self.math_level = level
        self.ai_report = report
        self.recommended_topics = ','.join(topics) if isinstance(topics, list) else topics
        self.onboarding_completed = True
    
    def get_recommended_topics_list(self):
        """Получить список рекомендуемых тем"""
        if self.recommended_topics:
            return self.recommended_topics.split(',')
        return []
    
    def update_stats_after_problem(self, is_correct, difficulty):
        """Обновить статистику после решения задачи"""
        if is_correct:
            self.total_problems_solved += 1
            self.experience_points += difficulty * 10  # 10 XP за каждый уровень сложности
            
            # Обновить максимальную сложность
            if difficulty > self.highest_difficulty_solved:
                self.highest_difficulty_solved = difficulty
            
            # Повышение уровня (каждые 100 XP = новый уровень)
            self.current_level = min(10, 1 + (self.experience_points // 100))
    
    def update_stats_after_mock_exam(self, score):
        """Обновить статистику после пробника"""
        if score >= 80:
            self.mock_exams_passed += 1
            self.experience_points += 50  # Бонус за успешный пробник
            self.current_level = min(10, 1 + (self.experience_points // 100))
    
    def update_stats_after_adaptive_test(self):
        """Обновить статистику после адаптивного теста"""
        self.adaptive_tests_completed += 1
        self.experience_points += 30  # Бонус за завершение адаптивного теста
        self.current_level = min(10, 1 + (self.experience_points // 100))
    
    def get_leaderboard_score(self):
        """Вычислить общий рейтинг для leaderboard"""
        # Формула рейтинга: XP + бонусы за достижения
        score = self.experience_points or 0
        score += (self.mock_exams_passed or 0) * 100  # Большой бонус за пробники
        score += (self.adaptive_tests_completed or 0) * 50
        score += (self.highest_difficulty_solved or 0) * 20
        return score
    
    def get_friends(self):
        """Все принятые друзья (с двух сторон)."""
        sent = Friendship.query.filter_by(requester_id=self.id, status='accepted').all()
        received = Friendship.query.filter_by(addressee_id=self.id, status='accepted').all()
        friend_ids = [f.addressee_id for f in sent] + [f.requester_id for f in received]
        return User.query.filter(User.id.in_(friend_ids)).all() if friend_ids else []

    def is_friend_with(self, other_id):
        return Friendship.query.filter(
            db.or_(
                db.and_(Friendship.requester_id == self.id,
                        Friendship.addressee_id == other_id,
                        Friendship.status == 'accepted'),
                db.and_(Friendship.requester_id == other_id,
                        Friendship.addressee_id == self.id,
                        Friendship.status == 'accepted'),
            )
        ).first() is not None

    def friendship_status_with(self, other_id):
        """Returns: none | pending_sent | pending_received | friends | declined | blocked"""
        f = Friendship.query.filter(
            db.or_(
                db.and_(Friendship.requester_id == self.id, Friendship.addressee_id == other_id),
                db.and_(Friendship.requester_id == other_id, Friendship.addressee_id == self.id),
            )
        ).first()
        if not f:
            return 'none'
        if f.status == 'accepted':
            return 'friends'
        if f.status in ('declined', 'blocked'):
            return f.status
        return 'pending_sent' if f.requester_id == self.id else 'pending_received'

    def incoming_friend_requests(self):
        return Friendship.query.filter_by(
            addressee_id=self.id, status='pending'
        ).order_by(Friendship.created_at.desc()).all()

    def outgoing_friend_requests(self):
        return Friendship.query.filter_by(
            requester_id=self.id, status='pending'
        ).order_by(Friendship.created_at.desc()).all()

    def friends_count(self):
        return Friendship.query.filter(
            db.or_(
                db.and_(Friendship.requester_id == self.id, Friendship.status == 'accepted'),
                db.and_(Friendship.addressee_id == self.id, Friendship.status == 'accepted'),
            )
        ).count()

    def unread_notifications_count(self):
        return Notification.query.filter_by(user_id=self.id, read=False).count()

    def today_quest(self):
        """Получить Daily Quest на сегодня (для navbar)"""
        from datetime import date
        try:
            return DailyQuest.query.filter_by(
                user_id=self.id,
                date=date.today()
            ).first()
        except Exception:
            return None

    def __repr__(self):
        return f'<User {self.email}>'


class OAuthAccount(db.Model):
    """Связь пользователя с внешними OAuth провайдерами"""
    __tablename__ = 'oauth_accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)  # 'yandex', 'google', etc.
    provider_user_id = db.Column(db.String(200), nullable=False)  # ID от провайдера
    
    # Уникальность: один аккаунт провайдера = один пользователь
    __table_args__ = (db.UniqueConstraint('provider', 'provider_user_id', name='_provider_user_uc'),)
    
    # Связь
    user = db.relationship('User', backref=db.backref('oauth_accounts', lazy='dynamic'))
    
    def __repr__(self):
        return f'<OAuthAccount {self.provider}:{self.provider_user_id}>'


class ChatMessage(db.Model):
    """История переписки с AI-тьютором"""
    __tablename__ = 'chat_messages'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_type = db.Column(db.String(50), nullable=False, default='general', index=True)  # algebra, geometry, number_theory, combinatorics, movement, logic, mentor
    role = db.Column(db.String(20), nullable=False)  # 'user' или 'assistant'
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    # Связь с пользователем
    user = db.relationship('User', backref=db.backref('chat_history', lazy='dynamic', order_by='ChatMessage.timestamp'))
    
    def to_dict(self):
        """Конвертация в словарь для JSON"""
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }
    
    def __repr__(self):
        return f'<ChatMessage {self.id} from User {self.user_id}>'


class MockExam(db.Model):
    """Пробник (Mock Exam)"""
    __tablename__ = 'mock_exams'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='in_progress')  # in_progress, checking, graded
    ai_feedback = db.Column(db.Text)  # Общий анализ от ИИ
    score = db.Column(db.Integer)  # Итоговый балл (0-100)
    
    # Связи
    user = db.relationship('User', backref=db.backref('exams', lazy='dynamic'))
    tasks = db.relationship('MockExamTask', backref='exam', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<MockExam {self.id} for User {self.user_id}>'


class MockExamTask(db.Model):
    """Задача в пробнике"""
    __tablename__ = 'mock_exam_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('mock_exams.id'), nullable=False)
    problem_id = db.Column(db.Integer, nullable=False)  # ID задачи из PROBLEMS_DB
    user_answer = db.Column(db.String(500))  # Ответ пользователя
    user_solution_text = db.Column(db.Text)  # Ход решения
    is_correct = db.Column(db.Boolean)  # Правильно ли
    ai_comment = db.Column(db.Text)  # Комментарий ИИ
    
    def __repr__(self):
        return f'<MockExamTask {self.id} in Exam {self.exam_id}>'


class SecretTopic(db.Model):
    """Кэш теоретических материалов"""
    __tablename__ = 'secret_topics'
    
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text)  # AI-сгенерированный контент
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<SecretTopic {self.slug}>'


class AdaptiveTest(db.Model):
    """Адаптивное тестирование"""
    __tablename__ = 'adaptive_tests'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(50))  # Предмет (algebra, geometry, etc.)
    grade = db.Column(db.Integer)  # Класс
    
    # Параметры теста
    num_problems = db.Column(db.Integer, default=10)
    initial_ability = db.Column(db.Float, default=3.5)
    current_ability = db.Column(db.Float, default=3.5)
    
    # Статус
    status = db.Column(db.String(20), default='in_progress')  # in_progress, completed, analyzing
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    # Результаты
    final_ability = db.Column(db.Float)
    total_correct = db.Column(db.Integer)
    accuracy = db.Column(db.Float)
    ai_analysis = db.Column(db.Text)  # AI анализ результатов
    
    # Связи
    user = db.relationship('User', backref=db.backref('adaptive_tests', lazy='dynamic'))
    problems = db.relationship('AdaptiveTestProblem', backref='test', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<AdaptiveTest {self.id} for User {self.user_id}>'


class AdaptiveTestProblem(db.Model):
    """Задача в адаптивном тесте"""
    __tablename__ = 'adaptive_test_problems'
    
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('adaptive_tests.id'), nullable=False)
    problem_id = db.Column(db.Integer, nullable=False)  # ID из PROBLEMS_DB
    sequence_number = db.Column(db.Integer, nullable=False)  # Порядковый номер в тесте
    
    # Параметры на момент выбора задачи
    user_ability_before = db.Column(db.Float)  # Способность до ответа
    problem_difficulty = db.Column(db.Float)  # Сложность задачи
    
    # Ответ пользователя
    user_answer = db.Column(db.String(500))
    user_solution_text = db.Column(db.Text)
    is_correct = db.Column(db.Boolean)
    answered_at = db.Column(db.DateTime)
    
    # Обновленная способность после ответа
    user_ability_after = db.Column(db.Float)
    
    # AI комментарий
    ai_feedback = db.Column(db.Text)
    
    def to_dict(self, include_problem_data=False):
        """Конвертация в словарь для JSON"""
        result = {
            'id': self.id,
            'test_id': self.test_id,
            'problem_id': self.problem_id,
            'sequence_number': self.sequence_number,
            'user_ability_before': self.user_ability_before,
            'problem_difficulty': self.problem_difficulty,
            'user_answer': self.user_answer,
            'user_solution_text': self.user_solution_text,
            'is_correct': self.is_correct,
            'answered_at': self.answered_at.isoformat() if self.answered_at else None,
            'user_ability_after': self.user_ability_after,
            'ai_feedback': self.ai_feedback
        }
        
        # Добавляем данные задачи из PROBLEMS_DB если запрошено
        if include_problem_data:
            try:
                from problems import PROBLEMS_DB
                problem = next((p for p in PROBLEMS_DB if p.get('id') == self.problem_id), None)
                if problem:
                    result['problem_text'] = problem.get('text', '')
                    result['problem_subject'] = problem.get('subject', '')
                    result['problem_subtopic'] = problem.get('subtopic', '')
                    result['problem_answer'] = problem.get('answer', '')
            except:
                pass
        
        return result
    
    def __repr__(self):
        return f'<AdaptiveTestProblem {self.id} in Test {self.test_id}>'


class Friendship(db.Model):
    """Двусторонняя дружба с подтверждением (как ВКонтакте)"""
    __tablename__ = 'friendships'
    
    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    addressee_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    # Статусы: pending | accepted | declined | blocked
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    accepted_at = db.Column(db.DateTime, nullable=True)
    
    requester = db.relationship('User', foreign_keys=[requester_id],
                                backref='sent_friend_requests')
    addressee = db.relationship('User', foreign_keys=[addressee_id],
                                backref='received_friend_requests')
    
    __table_args__ = (
        db.UniqueConstraint('requester_id', 'addressee_id', name='_friendship_unique'),
    )
    
    def accept(self):
        self.status = 'accepted'
        self.accepted_at = datetime.utcnow()
    
    def decline(self):
        self.status = 'declined'
    
    def __repr__(self):
        return f'<Friendship {self.requester_id}->{self.addressee_id} ({self.status})>'


def _aggregate_reactions(message_id, viewer_id=None):
    """Return list of {'emoji': str, 'count': int, 'mine': bool} for a message.

    Defined as a module-level helper so DirectMessage.to_dict() can call it
    without triggering circular-import issues.
    """
    try:
        rows = MessageReaction.query.filter_by(message_id=message_id).all()
    except Exception:
        return []
    buckets = {}
    for r in rows:
        b = buckets.setdefault(r.emoji, {'emoji': r.emoji, 'count': 0, 'mine': False})
        b['count'] += 1
        if viewer_id is not None and r.user_id == viewer_id:
            b['mine'] = True
    return sorted(buckets.values(), key=lambda x: (-x['count'], x['emoji']))


class DirectMessage(db.Model):
    """Личное сообщение между друзьями (1:1 чат).

    Содержит либо обычный текст, либо «карточку задачи» (kind='task_share').
    Для шаринга задач — `task_id` (AdaptiveTask.id) и опционально
    `task_topic`, `task_grade`, `task_difficulty`, `note` (комментарий
    отправителя). Это позволяет показать красивую карточку в чате
    без отдельной таблицы share-events.
    """
    __tablename__ = 'direct_messages'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    recipient_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    # 'text' — обычное сообщение, 'task_share' — карточка задачи
    kind = db.Column(db.String(20), nullable=False, default='text')
    body = db.Column(db.Text, nullable=True)

    # Поля для task_share (могут быть NULL для kind='text')
    task_id = db.Column(db.Integer, nullable=True, index=True)
    task_topic = db.Column(db.String(120), nullable=True)
    task_grade = db.Column(db.Integer, nullable=True)
    task_difficulty = db.Column(db.Integer, nullable=True)
    task_source = db.Column(db.String(40), nullable=True)
    # 'adaptive' | 'olympiad' | 'mock' | 'daily' | 'problem' …
    task_url = db.Column(db.String(400), nullable=True)
    task_preview = db.Column(db.Text, nullable=True)  # короткий текст условия

    # CHAT_ATTACH_V1 — вложения (картинка / pdf)
    attachment_url = db.Column(db.String(400), nullable=True)
    attachment_kind = db.Column(db.String(16), nullable=True)   # 'image' | 'pdf'
    attachment_name = db.Column(db.String(255), nullable=True)
    attachment_size = db.Column(db.Integer, nullable=True)      # bytes

    # WA-style chat (DM_WA_V1)
    reply_to_id = db.Column(db.Integer, nullable=True, index=True)
    edited_at = db.Column(db.DateTime, nullable=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    forwarded_from_id = db.Column(db.Integer, nullable=True, index=True)

    # Delivery / read receipts (DM_RECEIPTS_V1).  In a 1:1 chat with no
    # offline queue, "delivered" is set the moment the row is persisted.
    # "read_at" is set the first time the recipient hits the messages
    # endpoint for this conversation.  These coexist with `is_read` for
    # backwards compatibility with older API consumers.
    delivered_at = db.Column(db.DateTime, nullable=True)
    read_at = db.Column(db.DateTime, nullable=True)

    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    sender = db.relationship('User', foreign_keys=[sender_id],
                             backref=db.backref('sent_messages', lazy='dynamic'))
    recipient = db.relationship('User', foreign_keys=[recipient_id],
                                backref=db.backref('received_messages', lazy='dynamic'))

    def to_dict(self, viewer_id=None):  # DM_WA_V1
        is_deleted = getattr(self, 'deleted_at', None) is not None
        is_edited = getattr(self, 'edited_at', None) is not None
        reply_obj = None
        reply_to_id = getattr(self, 'reply_to_id', None)
        if reply_to_id:
            try:
                r = DirectMessage.query.get(reply_to_id)
                if r is not None:
                    reply_obj = {
                        'id': r.id,
                        'sender_id': r.sender_id,
                        'kind': r.kind,
                        'body': ('' if getattr(r, 'deleted_at', None) else (r.body or '')),
                        'deleted': getattr(r, 'deleted_at', None) is not None,
                    }
            except Exception:
                reply_obj = None
        return {
            'id': self.id,
            'sender_id': self.sender_id,
            'recipient_id': self.recipient_id,
            'mine': (viewer_id is not None and self.sender_id == viewer_id),
            'kind': self.kind,
            'body': ('' if is_deleted else self.body),
            'deleted': is_deleted,
            'edited': is_edited,
            'edited_at': self.edited_at.isoformat() if (is_edited and self.edited_at) else None,
            'reply_to_id': reply_to_id,
            'reply': reply_obj,
            'forwarded_from_id': getattr(self, 'forwarded_from_id', None),
            'forwarded': getattr(self, 'forwarded_from_id', None) is not None,
            'task': ({
                'id': self.task_id,
                'topic': self.task_topic,
                'grade': self.task_grade,
                'difficulty': self.task_difficulty,
                'source': self.task_source,
                'url': self.task_url,
                'preview': self.task_preview,
            } if self.kind == 'task_share' and not is_deleted else None),
            'is_read': self.is_read,
            'delivered_at': (self.delivered_at.isoformat()
                             if getattr(self, 'delivered_at', None) else None),
            'read_at': (self.read_at.isoformat()
                        if getattr(self, 'read_at', None) else None),
            'reactions': _aggregate_reactions(self.id, viewer_id),
            'attachment': ({
                'url':  self.attachment_url,
                'kind': self.attachment_kind,
                'name': self.attachment_name,
                'size': self.attachment_size,
            } if getattr(self, 'attachment_url', None) and not is_deleted else None),
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return (
            f'<DirectMessage {self.id} '
            f'{self.sender_id}->{self.recipient_id} ({self.kind})>'
        )


class Notification(db.Model):
    """Уведомления пользователей"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)  # friend_request | friend_accepted | ...
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                             nullable=True)
    data = db.Column(db.Text, nullable=True)  # JSON extra data
    read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user = db.relationship('User', foreign_keys=[user_id],
                           backref=db.backref('notifications', lazy='dynamic'))
    from_user = db.relationship('User', foreign_keys=[from_user_id])
    
    def __repr__(self):
        return f'<Notification {self.type} for user {self.user_id}>'


class PushSubscription(db.Model):
    """Web Push subscription for browser push notifications."""
    __tablename__ = 'push_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    endpoint = db.Column(db.Text, nullable=False)
    p256dh_key = db.Column(db.String(256), nullable=False)
    auth_key = db.Column(db.String(64), nullable=False)
    user_agent = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id],
                           backref=db.backref('push_subscriptions', lazy='dynamic',
                                               cascade='all, delete-orphan'))

    def to_dict(self):
        return {
            'endpoint': self.endpoint,
            'keys': {
                'p256dh': self.p256dh_key,
                'auth': self.auth_key
            }
        }

    def __repr__(self):
        return f'<PushSubscription user={self.user_id} endpoint={self.endpoint[:50]}...>'


class UserPresence(db.Model):
    """Онлайн-статус и typing-индикатор пользователя (CHAT_PRESENCE_V1).

    Одна строка на пользователя. ``last_seen`` обновляется при любой
    активности; ``typing_to_id`` + ``typing_at`` — пока человек печатает.
    Используется для индикаторов «в сети» и «печатает…» в чате.
    """
    __tablename__ = 'user_presence'

    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        primary_key=True)
    last_seen = db.Column(db.DateTime, default=datetime.utcnow,
                          nullable=False, index=True)
    typing_to_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'),
                             nullable=True)
    typing_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])

    def is_online(self, threshold_seconds: int = 60) -> bool:
        if not self.last_seen:
            return False
        return (datetime.utcnow() - self.last_seen).total_seconds() < threshold_seconds

    def is_typing_to(self, other_id: int, window_seconds: int = 6) -> bool:
        if self.typing_to_id != other_id or not self.typing_at:
            return False
        return (datetime.utcnow() - self.typing_at).total_seconds() < window_seconds

    def __repr__(self):
        return f'<UserPresence u={self.user_id} seen={self.last_seen}>'


class MessageReaction(db.Model):
    """Эмодзи-реакции на сообщения в личке (CHAT_REACTIONS_V1).

    Одна строка на «один эмодзи от одного пользователя на одно сообщение».
    Уникальный ключ (message_id, user_id, emoji) гарантирует, что повторное
    нажатие на уже поставленный эмодзи приведёт к его снятию (toggle).
    """
    __tablename__ = 'message_reactions'

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('direct_messages.id', ondelete='CASCADE'),
                           nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
                        nullable=False, index=True)
    emoji = db.Column(db.String(16), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('message_id', 'user_id', 'emoji',
                            name='uq_message_reaction'),
    )

    user = db.relationship('User', foreign_keys=[user_id])

    def __repr__(self):
        return (
            f'<MessageReaction m={self.message_id} u={self.user_id} '
            f'e={self.emoji!r}>'
        )


class Mentorship(db.Model):
    """Модель отношений учитель-ученик"""
    __tablename__ = 'mentorships'
    
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Уникальность: один учитель не может дважды добавить одного ученика
    # Проверка: нельзя добавить самого себя
    __table_args__ = (
        db.UniqueConstraint('teacher_id', 'student_id', name='_mentorship_unique'),
        db.CheckConstraint('teacher_id != student_id', name='_no_self_mentorship'),
    )
    
    # Связи
    teacher = db.relationship('User', foreign_keys=[teacher_id], backref=db.backref('students', lazy='dynamic'))
    student = db.relationship('User', foreign_keys=[student_id], backref=db.backref('teachers', lazy='dynamic'))
    
    @staticmethod
    def create_mentorship_request(teacher_id, student_id):
        """Создать заявку учитель-ученик"""
        if teacher_id == student_id:
            raise ValueError("Cannot add yourself as a student")
        
        # Проверяем существующую связь
        existing = Mentorship.query.filter_by(teacher_id=teacher_id, student_id=student_id).first()
        if existing:
            raise ValueError(f"Mentorship already exists with status: {existing.status}")
        
        mentorship = Mentorship(teacher_id=teacher_id, student_id=student_id, status='pending')
        return mentorship
    
    def accept(self):
        """Принять заявку"""
        self.status = 'accepted'
        self.updated_at = datetime.utcnow()
    
    def reject(self):
        """Отклонить заявку"""
        self.status = 'rejected'
        self.updated_at = datetime.utcnow()
    
    def __repr__(self):
        return f'<Mentorship Teacher:{self.teacher_id} -> Student:{self.student_id} ({self.status})>'


class OlympiadSecret(db.Model):
    """Модель для базы знаний олимпиадной математики"""
    __tablename__ = 'olympiad_secrets'
    
    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(100), nullable=False, index=True)  # Категория
    title = db.Column(db.String(200), nullable=False)  # Название метода
    content = db.Column(db.Text, nullable=False)  # Markdown статья
    difficulty_level = db.Column(db.Integer, nullable=False)  # 1-3
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<OlympiadSecret {self.topic}: {self.title}>'


class AdaptiveTask(db.Model):
    """Модель для задач Адаптивного теста (отдельная таблица от олимпиад)"""
    __tablename__ = 'adaptive_tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    class_level = db.Column(db.Integer, nullable=False, index=True)  # Класс (5, 6, 7, etc.)
    difficulty_level = db.Column(db.Integer, nullable=False, index=True)  # Уровень сложности 1-5
    topic = db.Column(db.String(200), nullable=False, index=True)  # Тема из матрицы 25 тем
    subtopic = db.Column(db.String(100), nullable=True, index=True)  # Подтема для уникальности в пробнике
    task_text = db.Column(db.Text, nullable=False)  # Условие задачи (с LaTeX)
    solution = db.Column(db.Text, nullable=False)  # Полное авторское решение
    criteria_1_point = db.Column(db.Text, nullable=False)  # Критерий на 1 балл
    criteria_2_points = db.Column(db.Text, nullable=False)  # Критерий на 2 балла
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    correct_answer = db.Column(db.Text)  # Правильный ответ для автопроверки
    
    # СИСТЕМА КОНТРОЛЯ КАЧЕСТВА
    is_flagged = db.Column(db.Boolean, default=False, index=True)  # Помечена как некорректная
    reports_count = db.Column(db.Integer, default=0)  # Количество жалоб от пользователей
    flagged_reason = db.Column(db.Text)  # Причина пометки (от AI или пользователя)
    
    # АДАПТИВНАЯ КАЛИБРОВКА СЛОЖНОСТИ
    attempts_count = db.Column(db.Integer, default=0)  # Всего попыток решения
    solves_count = db.Column(db.Integer, default=0)  # Успешных решений
    actual_solve_rate = db.Column(db.Float, default=None)  # Реальный % решивших (обновляется еженедельно)
    suggested_level = db.Column(db.Integer, default=None)  # Предложенный уровень (если расходится с difficulty_level)
    needs_reclassification = db.Column(db.Boolean, default=False, index=True)  # Требует переклассификации
    last_calibrated_at = db.Column(db.DateTime, default=None)  # Когда последний раз калибровалась

    # FORMYLA-импорт: канонический предмет и стабильный source-id из JSON-датасета.
    # Эти колонки добавляются в БД через ALTER TABLE в app.py при первом старте
    # (см. AUTO-MIGRATION блоки) — здесь они объявлены в ORM, чтобы запросы
    # типа `AdaptiveTask.subject == 'algebra'` работали и в тестовом контексте
    # in-memory SQLite, где автомиграция не запускается.
    subject = db.Column(db.String(20), index=True)
    source_id = db.Column(db.String(120), index=True)

    # Тип задачи и источник датасета (для идемпотентности сидера).
    # Колонки уже существуют в БД (ALTER TABLE при первом запуске).
    task_type = db.Column(db.Text)
    source = db.Column(db.Text, index=True)

    # Происхождение задачи: 'generated' | 'olympiad'
    origin = db.Column(db.String(16), nullable=True)
    # JSON-сериализованные методы решения (список строк)
    methods_json = db.Column(db.Text, nullable=True)

    # AI-тьютор self-check (см. auto-migration в app.py)
    theme_id = db.Column(db.String(50), nullable=True, index=True)
    needs_review = db.Column(db.Boolean, default=False, index=True)
    llm_suggested_answer = db.Column(db.Text)
    llm_suggested_solution = db.Column(db.Text)
    review_reason = db.Column(db.Text)
    review_flagged_at = db.Column(db.DateTime, default=None)

    # D3 PIPELINE: описание геометрических построений и статус чертежа
    figure_json = db.Column(db.Text, nullable=True)
    # Статусы: no_description, has_description, figure_built,
    #          engine_rejected, human_verified, human_rejected
    figure_status = db.Column(db.String(32), nullable=False, default='no_description', index=True)
    # CH8: aux figure (чертёж с дополнительными построениями)
    svg_path = db.Column(db.Text, nullable=True)
    aux_svg_path = db.Column(db.Text, nullable=True)
    has_aux = db.Column(db.Boolean, nullable=False, default=False)
    aux_reason = db.Column(db.Text, nullable=True)

    def to_dict(self):
        """Конвертация в словарь для JSON"""
        return {
            'id': self.id,
            'class_level': self.class_level,
            'difficulty_level': self.difficulty_level,
            'topic': self.topic,
            'task_text': self.task_text,
            'solution': self.solution,
            'criteria_1_point': self.criteria_1_point,
            'criteria_2_points': self.criteria_2_points
        }
    
    def __repr__(self):
        return f'<AdaptiveTask {self.id}: Class {self.class_level}, Difficulty {self.difficulty_level}, Topic: {self.topic[:30]}>'


class UserTopicProgress(db.Model):
    """Прогресс пользователя по конкретной теме"""
    __tablename__ = 'user_topic_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Тема
    topic = db.Column(db.String(50), nullable=False, index=True)  # 'algebra', 'geometry', etc.
    topic_name_ru = db.Column(db.String(100))  # 'Алгебра', 'Геометрия'
    
    # Текущий уровень по IRT (1-7)
    current_level = db.Column(db.Integer, default=3)  # Начальный уровень = 3
    
    # Статистика
    tasks_attempted = db.Column(db.Integer, default=0)
    tasks_correct = db.Column(db.Integer, default=0)
    last_test_date = db.Column(db.DateTime)
    
    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<UserTopicProgress user_id={self.user_id}, topic={self.topic}, level={self.current_level}>'


class AdaptiveTestResult(db.Model):
    """История прохождения адаптивных тестов"""
    __tablename__ = 'adaptive_test_results'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Параметры теста
    topic = db.Column(db.String(50))  # Тема теста
    class_level = db.Column(db.Integer)  # Класс
    
    # Результаты
    final_level = db.Column(db.Integer)  # Финальный уровень IRT (1-7)
    tasks_correct = db.Column(db.Integer)  # Правильных ответов
    tasks_total = db.Column(db.Integer, default=25)  # Всего задач
    
    # Детали (JSON)
    answers_history = db.Column(db.Text)  # JSON с историей ответов
    
    # Метаданные
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<AdaptiveTestResult user_id={self.user_id}, topic={self.topic}, level={self.final_level}>'


class DailyQuest(db.Model):
    """Ежедневные задачи (Daily Quest)"""
    __tablename__ = 'daily_quests'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)  # Дата квеста
    
    # Задачи (JSON массив ID задач)
    task_ids = db.Column(db.Text, nullable=False)  # JSON: [id1, id2, id3, id4, id5]
    
    # Прогресс
    completed_count = db.Column(db.Integer, default=0)  # Решено задач
    total_count = db.Column(db.Integer, default=10)  # Всего задач
    
    # Награды
    xp_earned = db.Column(db.Integer, default=0)  # Заработано XP
    
    # AI комментарий
    ai_comment = db.Column(db.Text)  # Почему именно эти задачи

    # Какие задачи (по индексу в task_ids) уже решены ПРАВИЛЬНО.
    # JSON-массив индексов, например: "[0, 2, 4]".
    # Используется чтобы запретить повторное решение той же задачи.
    solved_indices = db.Column(db.Text, default='[]')

    # DQ_ATTEMPTS_V1: счётчик неправильных попыток на каждую задачу.
    # JSON-словарь {task_index_str: attempts_count}. Например '{"0": 1, "2": 2}'.
    attempts_map = db.Column(db.Text, default='{}')

    # DQ_ATTEMPTS_V1: индексы задач, заблокированных после исчерпания попыток.
    # JSON-массив, например [2, 4]. Параллелен solved_indices, но для fails.
    # NB: тип db.JSON. На проде колонка уже jsonb (Render PG); на SQLite
    # SQLAlchemy сериализует/десериализует через TEXT прозрачно. Это лечит
    # psycopg.errors.DatatypeMismatch при записи строки в jsonb-колонку.
    # solved_indices намеренно остаётся db.Text — на проде у него тип text.
    failed_indices = db.Column(db.JSON, default=list)

    # DQ_REGEN_COOLDOWN_V1: когда последний раз пользователь перегенерил квест.
    # Нужно для cooldown-логики (1 час между регенерациями).
    last_regenerated_at = db.Column(db.DateTime, nullable=True)

    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)  # Когда завершён
    
    # Связь
    user = db.relationship('User', backref=db.backref('daily_quests', lazy='dynamic'))
    
    # Уникальность: один квест на пользователя в день
    __table_args__ = (db.UniqueConstraint('user_id', 'date', name='_user_date_uc'),)
    
    def __repr__(self):
        return f'<DailyQuest user_id={self.user_id}, date={self.date}, progress={self.completed_count}/{self.total_count}>'


class UserStreak(db.Model):
    """Streak система (как в Duolingo)"""
    __tablename__ = 'user_streaks'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    
    # Streak данные
    current_streak = db.Column(db.Integer, default=0)  # Текущая серия дней
    longest_streak = db.Column(db.Integer, default=0)  # Рекорд
    last_active_date = db.Column(db.Date)  # Последний активный день
    
    # Freeze (заморозка streak)
    freeze_available = db.Column(db.Integer, default=1)  # Доступно заморозок (1 в месяц)
    freeze_used_at = db.Column(db.Date)  # Когда использована последняя заморозка
    
    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связь
    user = db.relationship('User', backref=db.backref('streak', uselist=False))
    
    def __repr__(self):
        return f'<UserStreak user_id={self.user_id}, current={self.current_streak}, longest={self.longest_streak}>'


class TopicMastery(db.Model):
    """Мастерство по темам (для подбора Daily Quest)"""
    __tablename__ = 'topic_mastery'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Тема
    topic = db.Column(db.String(100), nullable=False)  # Название темы
    grade = db.Column(db.Integer, nullable=False)  # Класс
    
    # Статистика
    solved = db.Column(db.Integer, default=0)  # Решено задач
    attempts = db.Column(db.Integer, default=0)  # Попыток всего
    avg_level = db.Column(db.Float, default=3.0)  # Средний уровень решённых задач
    
    # Мастерство (0.0 - 1.0)
    mastery = db.Column(db.Float, default=0.0)  # Уровень владения темой
    
    # Метаданные
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Связь
    user = db.relationship('User', backref=db.backref('topic_mastery', lazy='dynamic'))
    
    # Уникальность: одна запись на тему+класс для пользователя
    __table_args__ = (db.UniqueConstraint('user_id', 'topic', 'grade', name='_user_topic_grade_uc'),)
    
    def __repr__(self):
        return f'<TopicMastery user_id={self.user_id}, topic={self.topic}, mastery={self.mastery:.2f}>'


class OlympiadGenerationLog(db.Model):
    """Лог генерации олимпиадных задач (для аналитики качества)."""
    __tablename__ = 'olympiad_generation_log'

    id = db.Column(db.Integer, primary_key=True)
    olympiad_slug = db.Column(db.String(100), nullable=False)
    round_key = db.Column(db.String(100), nullable=False)
    class_level = db.Column(db.Integer, nullable=False)
    attempts = db.Column(db.Integer, default=1)
    success = db.Column(db.Integer, default=0)  # 1 / 0
    errors_json = db.Column(db.Text, nullable=True)  # JSON лог попыток
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('olympiad_gen_logs', lazy='dynamic'))

    def __repr__(self):
        return (
            f'<OlympiadGenerationLog {self.olympiad_slug}/{self.round_key}'
            f'/класс {self.class_level} success={self.success}>'
        )


class TestResult(db.Model):
    """Детальная история результатов тестов"""
    __tablename__ = 'test_results_detail'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    device_id = db.Column(db.String(64), nullable=True)
    test_type = db.Column(db.String(50), nullable=False)  # adaptive, mock, daily, practice
    class_level = db.Column(db.Integer, nullable=True)
    topic = db.Column(db.String(200), nullable=True)
    task_id = db.Column(db.Integer, nullable=True)
    difficulty = db.Column(db.Integer, nullable=True)
    is_correct = db.Column(db.Boolean, nullable=False)
    user_answer = db.Column(db.Text, nullable=True)
    time_spent_sec = db.Column(db.Integer, nullable=True)
    rating_delta = db.Column(db.Float, nullable=True)
    rating_after = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user = db.relationship('User', backref=db.backref('detailed_results', lazy='dynamic'))
    
    def to_dict(self):
        return {
            'id': self.id,
            'test_type': self.test_type,
            'class_level': self.class_level,
            'topic': self.topic,
            'task_id': self.task_id,
            'difficulty': self.difficulty,
            'is_correct': self.is_correct,
            'user_answer': self.user_answer,
            'time_spent_sec': self.time_spent_sec,
            'rating_delta': self.rating_delta,
            'rating_after': self.rating_after,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class UserProgress(db.Model):
    """Агрегированный прогресс пользователя по темам"""
    __tablename__ = 'user_progress'
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    topic = db.Column(db.String(200), nullable=False)
    class_level = db.Column(db.Integer, nullable=False)
    rating = db.Column(db.Float, default=1000.0)
    tasks_solved = db.Column(db.Integer, default=0)
    tasks_attempted = db.Column(db.Integer, default=0)
    current_difficulty = db.Column(db.Integer, default=1)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.PrimaryKeyConstraint('user_id', 'topic', 'class_level'),
    )
    
    user = db.relationship('User', backref=db.backref('progress_entries', lazy='dynamic'))
    
    def to_dict(self):
        return {
            'topic': self.topic,
            'class_level': self.class_level,
            'rating': self.rating,
            'tasks_solved': self.tasks_solved,
            'tasks_attempted': self.tasks_attempted,
            'current_difficulty': self.current_difficulty,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None
        }


# ═══════════════════════════════════════════════════════════════════════════════
# OLYMPIAD PREP SYSTEM (PrepPlan / PrepDay / OlympiadPrep / TaskSolution)
# ═══════════════════════════════════════════════════════════════════════════════

class OlympiadPrep(db.Model):
    """Каталог олимпиад для подготовки (ВсОШ, Турнир городов, etc.)."""
    __tablename__ = 'olympiad_prep'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    short_name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    grades = db.Column(db.Text, nullable=True)              # JSON list of int
    stages = db.Column(db.Text, nullable=True)              # JSON list of stage names
    official_url = db.Column(db.String(500), nullable=True)
    logo_path = db.Column(db.String(500), nullable=True)
    color_hex = db.Column(db.String(20), default='#22d3a6')
    sort_order = db.Column(db.Integer, default=0, index=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, server_default='1')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def grades_list(self):
        import json
        try:
            return json.loads(self.grades) if self.grades else []
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def stages_list(self):
        import json
        try:
            return json.loads(self.stages) if self.stages else []
        except (json.JSONDecodeError, TypeError):
            return []

    def __repr__(self):
        return f'<OlympiadPrep {self.slug} id={self.id}>'


class PrepPlan(db.Model):
    """Персональный план подготовки пользователя к олимпиаде."""
    __tablename__ = 'prep_plans'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    olympiad_id = db.Column(db.Integer, db.ForeignKey('olympiad_prep.id'), nullable=False, index=True)
    target_stage = db.Column(db.String(100), nullable=True)
    target_grade = db.Column(db.Integer, nullable=True)  # User can prep for higher grade
    start_date = db.Column(db.Date, nullable=False)
    target_date = db.Column(db.Date, nullable=False)
    baseline_radar = db.Column(db.Text, nullable=True)   # JSON {topic: 0..100}
    current_radar = db.Column(db.Text, nullable=True)    # JSON {topic: 0..100}
    daily_task_count = db.Column(db.Integer, default=5)
    status = db.Column(db.String(20), default='active', index=True)  # active|paused|completed|expired
    current_streak = db.Column(db.Integer, default=0)
    longest_streak = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('prep_plans', lazy='dynamic'))
    olympiad = db.relationship('OlympiadPrep', backref=db.backref('plans', lazy='dynamic'))
    days = db.relationship('PrepDay', backref='plan', lazy='dynamic',
                           cascade='all, delete-orphan', order_by='PrepDay.date')

    @property
    def baseline_radar_dict(self):
        import json
        try:
            return json.loads(self.baseline_radar) if self.baseline_radar else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @baseline_radar_dict.setter
    def baseline_radar_dict(self, value):
        import json
        self.baseline_radar = json.dumps(value, ensure_ascii=False)

    @property
    def current_radar_dict(self):
        import json
        try:
            return json.loads(self.current_radar) if self.current_radar else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @current_radar_dict.setter
    def current_radar_dict(self, value):
        import json
        self.current_radar = json.dumps(value, ensure_ascii=False)

    @property
    def days_total(self):
        return (self.target_date - self.start_date).days

    @property
    def days_elapsed(self):
        from datetime import date as _date
        today = _date.today()
        if today < self.start_date:
            return 0
        if today > self.target_date:
            return self.days_total
        return (today - self.start_date).days

    @property
    def progress_pct(self):
        total = self.days_total
        if total <= 0:
            return 100
        return min(100, round(self.days_elapsed / total * 100))

    def to_dict(self):
        return {
            'id': self.id,
            'olympiad_id': self.olympiad_id,
            'olympiad_slug': self.olympiad.slug if self.olympiad else None,
            'olympiad_name': self.olympiad.name if self.olympiad else None,
            'target_stage': self.target_stage,
            'target_grade': self.target_grade,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'target_date': self.target_date.isoformat() if self.target_date else None,
            'baseline_radar': self.baseline_radar_dict,
            'current_radar': self.current_radar_dict,
            'daily_task_count': self.daily_task_count,
            'status': self.status,
            'current_streak': self.current_streak,
            'longest_streak': self.longest_streak,
            'progress_pct': self.progress_pct,
            'days_total': self.days_total,
            'days_elapsed': self.days_elapsed,
        }

    def __repr__(self):
        return f'<PrepPlan id={self.id} user={self.user_id} olympiad={self.olympiad_id} status={self.status}>'


class PrepDay(db.Model):
    """День в персональном плане подготовки."""
    __tablename__ = 'prep_days'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('prep_plans.id'), nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    target_topics = db.Column(db.Text, nullable=True)         # JSON list of topics
    problem_ids = db.Column(db.Text, nullable=True)           # JSON list of AdaptiveTask ids
    completed_problem_ids = db.Column(db.Text, default='[]')  # JSON list
    day_score = db.Column(db.Integer, default=0)              # # correct
    status = db.Column(db.String(20), default='upcoming', index=True)  # upcoming|today|completed|missed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def target_topics_list(self):
        import json
        try:
            return json.loads(self.target_topics) if self.target_topics else []
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def problem_ids_list(self):
        import json
        try:
            return json.loads(self.problem_ids) if self.problem_ids else []
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def completed_problem_ids_list(self):
        import json
        try:
            return json.loads(self.completed_problem_ids) if self.completed_problem_ids else []
        except (json.JSONDecodeError, TypeError):
            return []

    @property
    def total_problems(self):
        return len(self.problem_ids_list)

    @property
    def completed_count(self):
        return len(self.completed_problem_ids_list)

    def to_dict(self):
        return {
            'id': self.id,
            'plan_id': self.plan_id,
            'date': self.date.isoformat() if self.date else None,
            'target_topics': self.target_topics_list,
            'problem_ids': self.problem_ids_list,
            'completed_problem_ids': self.completed_problem_ids_list,
            'completed_count': self.completed_count,
            'total_problems': self.total_problems,
            'day_score': self.day_score,
            'status': self.status,
        }

    def __repr__(self):
        return f'<PrepDay id={self.id} plan={self.plan_id} date={self.date} status={self.status}>'


class BrokenTaskLog(db.Model):
    """Лог отбракованных задач для разных surface (planner, daily, etc.)."""
    __tablename__ = 'broken_task_log'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, nullable=False, index=True)
    surface = db.Column(db.String(50), nullable=False, index=True)
    reasons = db.Column(db.Text, nullable=True)
    hits = db.Column(db.Integer, default=1)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f'<BrokenTaskLog task={self.task_id} surface={self.surface} hits={self.hits}>'


class TaskSolution(db.Model):
    """Сохранённое решение задачи пользователем (для ML dataset + истории)."""
    __tablename__ = 'task_solutions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey('adaptive_tasks.id'), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('prep_plans.id'), nullable=True, index=True)
    day_id = db.Column(db.Integer, db.ForeignKey('prep_days.id'), nullable=True, index=True)

    # Solution content
    user_answer = db.Column(db.Text, nullable=True)           # short answer text
    user_solution = db.Column(db.Text, nullable=True)         # full text solution
    original_photo_url = db.Column(db.String(500), nullable=True)  # R2 URL of handwritten photo
    photo_hash = db.Column(db.String(64), nullable=True, index=True)  # SHA256 dedupe

    # OCR pipeline
    ocr_raw_output = db.Column(db.Text, nullable=True)        # Raw OCR JSON
    ocr_corrected = db.Column(db.Text, nullable=True)         # User-corrected LaTeX
    was_corrected = db.Column(db.Boolean, default=False)

    # Evaluation
    is_correct = db.Column(db.Boolean, nullable=True)
    feedback_json = db.Column(db.Text, nullable=True)         # DeepSeek feedback

    # ML dataset
    consent_for_training = db.Column(db.Boolean, default=False, nullable=False, server_default='0')
    quality_score = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    user = db.relationship('User', backref=db.backref('task_solutions', lazy='dynamic'))
    task = db.relationship('AdaptiveTask', backref=db.backref('solutions', lazy='dynamic'))

    def __repr__(self):
        return f'<TaskSolution id={self.id} user={self.user_id} task={self.task_id}>'


class TaskAssignmentHistory(db.Model):
    """Shared assignment history: which task was assigned to which student.

    Used by the daily rotation engine to prevent repeat assignments.
    One row per unique (user_id, task_id) pair.
    """
    __tablename__ = 'task_assignment_history'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id'), nullable=False, index=True,
    )
    task_id = db.Column(
        db.Integer, db.ForeignKey('adaptive_tasks.id'), nullable=False, index=True,
    )
    assigned_date = db.Column(db.Date, nullable=False)
    source = db.Column(
        db.String(32), nullable=False, default='daily_set',
    )  # 'diagnostic' | 'daily_set' | 'daily_quest'
    result = db.Column(db.String(16), nullable=True)  # 'correct' | 'incorrect' | None
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'task_id', name='uq_tah_user_task'),
    )

    def __repr__(self):
        return (f'<TaskAssignmentHistory user={self.user_id} '
                f'task={self.task_id} src={self.source}>')


class DrawingGeneration(db.Model):
    """Лог одной генерации чертежа (code-generation pipeline)."""
    __tablename__ = 'drawing_generations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id'),
        nullable=True, index=True,
    )
    problem_sha256 = db.Column(db.String(64), nullable=False, index=True)
    problem = db.Column(db.Text, nullable=False)
    generated_code = db.Column(db.Text, nullable=True)
    model = db.Column(db.String(120), nullable=True)
    status = db.Column(
        db.String(20), nullable=False, default='ok', index=True,
    )  # 'ok' | 'error' | 'rejected' | 'timeout' | 'cache_hit'
    error = db.Column(db.Text, nullable=True)
    repair_iters = db.Column(db.Integer, nullable=False, default=0)
    render_ms = db.Column(db.Integer, nullable=True)
    cost_usd = db.Column(db.Float, nullable=False, default=0.0)
    image_path = db.Column(db.String(500), nullable=True)
    image_size = db.Column(db.Integer, nullable=True)
    # Gemini-critic stage (added later — nullable for backward compat)
    critique_rounds = db.Column(db.Integer, nullable=False, default=0)
    critique_accepted = db.Column(db.Integer, nullable=False, default=0)
    critique_rejected = db.Column(db.Integer, nullable=False, default=0)
    critique_findings_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False, index=True,
    )

    user = db.relationship(
        'User',
        backref=db.backref('drawing_generations', lazy='dynamic'),
    )

    def __repr__(self):
        return (
            f'<DrawingGeneration id={self.id} status={self.status} '
            f'model={self.model} render_ms={self.render_ms}>'
        )


class GroupChat(db.Model):
    """CHAT_GROUPS_V1 — group conversation owned by a user."""
    __tablename__ = 'group_chats'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    avatar_emoji = db.Column(db.String(8), nullable=True, default='')
    owner_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class GroupMember(db.Model):
    """CHAT_GROUPS_V1 — membership in a group chat."""
    __tablename__ = 'group_members'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('group_chats.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    role = db.Column(db.String(16), nullable=False, default='member')
    joined_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('group_id', 'user_id', name='_group_member_unique'),
    )


class GroupMessage(db.Model):
    """CHAT_GROUPS_V1 — single message in a group chat.

    CHAT_ATTACH_V1 — supports image/PDF attachments via the same
    attachment_* columns as DirectMessage.
    """
    __tablename__ = 'group_messages'
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(
        db.Integer, db.ForeignKey('group_chats.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    sender_id = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    kind = db.Column(db.String(20), nullable=False, default='text')
    body = db.Column(db.Text, nullable=True)

    # CHAT_ATTACH_V1 — вложения (картинка / pdf)
    attachment_url = db.Column(db.String(400), nullable=True)
    attachment_kind = db.Column(db.String(16), nullable=True)   # 'image' | 'pdf'
    attachment_name = db.Column(db.String(255), nullable=True)
    attachment_size = db.Column(db.Integer, nullable=True)      # bytes

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


def init_db(app):
    """Инициализация базы данных"""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        print("[OK] База данных инициализирована")


# ──────────────────────────────────────────────────────────────────────────────
# Раздел «Олимпиады» (/olympiads/*) — модели вынесены в models_olympiad.py,
# чтобы не раздувать этот файл.  Реэкспортируем здесь, чтобы остальной
# код мог писать `from models import Probnik, OlympiadTask, ...` единообразно.
#
# ВАЖНО: импорт обязательно В КОНЦЕ файла, чтобы к моменту регистрации
# моделей объект `db = SQLAlchemy()` (см. начало этого модуля) уже существовал
# и не возникло циклического импорта.
# ──────────────────────────────────────────────────────────────────────────────
from models_olympiad import (  # noqa: E402  (intentional late import)
    Probnik,
    OlympiadTask,
    TheoryBlock,
    ProbnikTheory,
    TaskAttempt,
    StageAttempt,
    PROBNIK_TYPES,
    DIFFICULTY_LEVELS,
    THEORY_SECTIONS,
    ATTEMPT_STATUSES,
    STAGE_RESULTS,
)


# ── D4: Figure Generation Models ───────────────────────────────────────

class FigureGeneration(db.Model):
    """Лог одной генерации чертежа через ризонер (reasoner + engine pipeline)."""
    __tablename__ = 'figure_generations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id'),
        nullable=True, index=True,
    )
    problem_sha256 = db.Column(db.String(64), nullable=False, index=True)
    problem = db.Column(db.Text, nullable=False)
    solution = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.String(20), nullable=False, default='ok', index=True,
    )  # 'ok' | 'error' | 'validation_failed'
    json_description = db.Column(db.Text, nullable=True)
    model = db.Column(db.String(120), nullable=True)
    cost_usd = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False, index=True,
    )

    user = db.relationship(
        'User',
        backref=db.backref('figure_generations', lazy='dynamic'),
    )

    def __repr__(self):
        return (
            f'<FigureGeneration id={self.id} status={self.status} '
            f'model={self.model}>'
        )


class FigureCreditTransaction(db.Model):
    """Журнал операций с чертежами (начисление/списание)."""
    __tablename__ = 'figure_credit_transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.id'),
        nullable=False, index=True,
    )
    amount = db.Column(db.Integer, nullable=False)      # positive = credit, negative = debit
    reason = db.Column(db.String(64), nullable=False)   # 'initial', 'spend', 'streak_7day', 'slice_pass', 'purchase'
    reference = db.Column(db.String(128), nullable=True) # e.g. streak_week_id or purchase_id
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False, index=True,
    )

    user = db.relationship(
        'User',
        backref=db.backref('figure_credit_transactions', lazy='dynamic'),
    )

    def __repr__(self):
        return (
            f'<FigureCreditTransaction user={self.user_id} '
            f'amount={self.amount} reason={self.reason}>'
        )


class FigureEmailSubscription(db.Model):
    """Emails collected from «сообщить мне, когда заработает» payment stub."""
    __tablename__ = 'figure_email_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False,
    )

    def __repr__(self):
        return f'<FigureEmailSubscription email={self.email}>'


# ── D5: Background Figure Generation Queue ─────────────────────────────

class FigureJob(db.Model):
    """Фоновое задание на построение чертежа (D5 queue).

    Статусы: queued -> thinking -> drawing -> done | failed.
    Кредит списывается только в момент перехода в done.
    """
    __tablename__ = 'figure_jobs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    problem = db.Column(db.Text, nullable=False)
    solution = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.String(20), nullable=False, default='queued', index=True,
    )  # queued | thinking | drawing | done | failed
    step_label = db.Column(db.String(80), nullable=True)
    json_description = db.Column(db.Text, nullable=True)
    svg_result = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    credit_spent = db.Column(db.Boolean, nullable=False, default=False)
    model_used = db.Column(db.String(120), nullable=True)
    cost_usd = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False, index=True,
    )
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
    )

    user = db.relationship(
        'User',
        backref=db.backref('figure_jobs', lazy='dynamic'),
    )

    def __repr__(self):
        return (
            f'<FigureJob id={self.id} user={self.user_id} '
            f'status={self.status}>'
        )


class FigureBuildJob(db.Model):
    """CH5: Background figure build queue (new /figures/generate pipeline).

    Статусы: queued -> thinking -> drawing -> done | failed.
    Кредит списывается только в момент перехода в done (флаг credit_charged).
    Хранится в БД, а не в памяти процесса — переживает перезапуск.
    """
    __tablename__ = 'figure_build_jobs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'),
                        nullable=False, index=True)
    problem_text = db.Column(db.Text, nullable=False)
    status = db.Column(
        db.String(20), nullable=False, default='queued', index=True,
    )  # queued | thinking | drawing | done | failed
    model_name = db.Column(db.String(120), nullable=True)
    svg_path = db.Column(db.Text, nullable=True)
    aux_svg_path = db.Column(db.Text, nullable=True)
    has_aux = db.Column(db.Boolean, nullable=False, default=False)
    aux_reason = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    credit_charged = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False, index=True,
    )
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
        nullable=False,
    )

    user = db.relationship(
        'User',
        backref=db.backref('figure_build_jobs', lazy='dynamic'),
    )

    def __repr__(self):
        return (
            f'<FigureBuildJob id={self.id} user={self.user_id} '
            f'status={self.status}>'
        )


class SolutionAttempt(db.Model):
    """D9: solution method for morning probe tasks (text or photo)."""
    __tablename__ = 'solution_attempts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey('adaptive_tasks.id'), nullable=False, index=True)
    probe_id = db.Column(db.Integer, nullable=True, index=True)  # ThemeProbe id
    attempt_type = db.Column(db.String(8), nullable=False)  # 'text' or 'photo'
    solution_text = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(512), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)  # bytes after compression
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('solution_attempts', lazy='dynamic'))

    def __repr__(self):
        return f'<SolutionAttempt id={self.id} user={self.user_id} type={self.attempt_type}>'


class KimiReview(db.Model):
    """CH10: Kimi K2.5 review of a solution attempt."""
    __tablename__ = 'kimi_reviews'

    id = db.Column(db.Integer, primary_key=True)
    solution_attempt_id = db.Column(db.Integer, db.ForeignKey('solution_attempts.id'), nullable=True, index=True)
    raw_response = db.Column(db.Text, nullable=True)
    label = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    solution_attempt = db.relationship('SolutionAttempt', backref=db.backref('kimi_reviews', lazy='dynamic'))

    def __repr__(self):
        return f'<KimiReview id={self.id} attempt={self.solution_attempt_id} label={self.label}>'


class SchemaMigrationLog(db.Model):
    """V11: Log of applied migration scripts for idempotent re-runs.

    Tracks ad-hoc migration scripts that are NOT managed by Alembic.
    Each row records one successfully applied migration file.
    Before executing, a migration script checks this table;
    after success, it inserts a row.  This ensures repeated runs
    are safe on both SQLite and PostgreSQL.
    """
    __tablename__ = 'schema_migration_log'

    id = db.Column(db.Integer, primary_key=True)
    migration_name = db.Column(db.String(256), unique=True, nullable=False, index=True)
    applied_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f'<SchemaMigrationLog {self.migration_name} @ {self.applied_at}>'
