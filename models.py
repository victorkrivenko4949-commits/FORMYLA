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
    
    # Relationships
    topic_progress = db.relationship('UserTopicProgress', backref='user', lazy=True, cascade='all, delete-orphan')
    test_results = db.relationship('AdaptiveTestResult', backref='user', lazy=True, cascade='all, delete-orphan')
    
    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
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
        score = self.experience_points
        score += self.mock_exams_passed * 100  # Большой бонус за пробники
        score += self.adaptive_tests_completed * 50
        score += self.highest_difficulty_solved * 20
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
    difficulty_level = db.Column(db.Integer, nullable=False, index=True)  # Уровень сложности 1-7
    topic = db.Column(db.String(200), nullable=False, index=True)  # Тема из матрицы 25 тем
    subtopic = db.Column(db.String(100), nullable=True, index=True)  # Подтема для уникальности в пробнике
    task_text = db.Column(db.Text, nullable=False)  # Условие задачи (с LaTeX)
    solution = db.Column(db.Text, nullable=False)  # Полное авторское решение
    criteria_1_point = db.Column(db.Text, nullable=False)  # Критерий на 1 балл
    criteria_2_points = db.Column(db.Text, nullable=False)  # Критерий на 2 балла
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    correct_answer = db.Column(db.String(500))  # Правильный ответ для автопроверки
    
    # СИСТЕМА КОНТРОЛЯ КАЧЕСТВА
    is_flagged = db.Column(db.Boolean, default=False, index=True)  # Помечена как некорректная
    reports_count = db.Column(db.Integer, default=0)  # Количество жалоб от пользователей
    flagged_reason = db.Column(db.String(500))  # Причина пометки (от AI или пользователя)
    
    # АДАПТИВНАЯ КАЛИБРОВКА СЛОЖНОСТИ
    attempts_count = db.Column(db.Integer, default=0)  # Всего попыток решения
    solves_count = db.Column(db.Integer, default=0)  # Успешных решений
    actual_solve_rate = db.Column(db.Float, default=None)  # Реальный % решивших (обновляется еженедельно)
    suggested_level = db.Column(db.Integer, default=None)  # Предложенный уровень (если расходится с difficulty_level)
    needs_reclassification = db.Column(db.Boolean, default=False, index=True)  # Требует переклассификации
    last_calibrated_at = db.Column(db.DateTime, default=None)  # Когда последний раз калибровалась
    
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
    total_count = db.Column(db.Integer, default=5)  # Всего задач
    
    # Награды
    xp_earned = db.Column(db.Integer, default=0)  # Заработано XP
    
    # AI комментарий
    ai_comment = db.Column(db.Text)  # Почему именно эти задачи
    
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


def init_db(app):
    """Инициализация базы данных"""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        print("✅ База данных инициализирована")
