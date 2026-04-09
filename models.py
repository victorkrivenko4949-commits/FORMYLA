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
    """Модель дружбы между пользователями"""
    __tablename__ = 'friendships'
    
    id = db.Column(db.Integer, primary_key=True)
    user_1_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    user_2_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Уникальность: нельзя дважды отправить заявку одной и той же паре
    # Используем CHECK constraint чтобы user_1_id всегда был меньше user_2_id
    __table_args__ = (
        db.UniqueConstraint('user_1_id', 'user_2_id', name='_friendship_unique'),
        db.CheckConstraint('user_1_id < user_2_id', name='_user_order_check'),
    )
    
    # Связи
    user_1 = db.relationship('User', foreign_keys=[user_1_id], backref=db.backref('friendships_as_user1', lazy='dynamic'))
    user_2 = db.relationship('User', foreign_keys=[user_2_id], backref=db.backref('friendships_as_user2', lazy='dynamic'))
    
    @staticmethod
    def normalize_user_ids(user_id_a, user_id_b):
        """Нормализация ID: меньший всегда первый"""
        return (min(user_id_a, user_id_b), max(user_id_a, user_id_b))
    
    @staticmethod
    def get_friendship(user_id_a, user_id_b):
        """Получить дружбу между двумя пользователями"""
        user_1_id, user_2_id = Friendship.normalize_user_ids(user_id_a, user_id_b)
        return Friendship.query.filter_by(user_1_id=user_1_id, user_2_id=user_2_id).first()
    
    @staticmethod
    def create_friendship_request(from_user_id, to_user_id):
        """Создать заявку в друзья"""
        if from_user_id == to_user_id:
            raise ValueError("Cannot add yourself as a friend")
        
        user_1_id, user_2_id = Friendship.normalize_user_ids(from_user_id, to_user_id)
        
        # Проверяем существующую дружбу
        existing = Friendship.query.filter_by(user_1_id=user_1_id, user_2_id=user_2_id).first()
        if existing:
            raise ValueError(f"Friendship already exists with status: {existing.status}")
        
        friendship = Friendship(user_1_id=user_1_id, user_2_id=user_2_id, status='pending')
        return friendship
    
    def accept(self):
        """Принять заявку в друзья"""
        self.status = 'accepted'
        self.updated_at = datetime.utcnow()
    
    def reject(self):
        """Отклонить заявку в друзья"""
        self.status = 'rejected'
        self.updated_at = datetime.utcnow()
    
    def get_other_user_id(self, current_user_id):
        """Получить ID другого пользователя в дружбе"""
        return self.user_2_id if self.user_1_id == current_user_id else self.user_1_id
    
    def __repr__(self):
        return f'<Friendship {self.user_1_id}<->{self.user_2_id} ({self.status})>'


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


def init_db(app):
    """Инициализация базы данных"""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        print("✅ База данных инициализирована")
