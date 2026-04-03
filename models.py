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


def init_db(app):
    """Инициализация базы данных"""
    db.init_app(app)
    with app.app_context():
        db.create_all()
        print("✅ База данных инициализирована")
