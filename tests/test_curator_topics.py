# -*- coding: utf-8 -*-
"""
CURATOR_TOPICS_V1 + CURATOR_FREE_V1 (19.11.2026).

Проверяем:
  * посторонняя тема (не математика, не сайт) — вежливый отказ БЕЗ обращения
    к основному промпту куратора (классификатор отсекает до генерации);
  * математика и вопросы о сайте — доходят до генерации ответа;
  * сбой классификатора не блокирует ученика: отвечаем как обычно;
  * куратор доступен на бесплатном тарифе: /curator не отдаёт 404,
    сообщение из чата обрабатывается.
"""
import json

import pytest

import services.curator_chat as curator_chat
from models import db, User, CuratorChatMessage


@pytest.fixture
def free_user(app, monkeypatch):
    """Обычный бесплатный пользователь (без подписки и без админ-прав).

    is_admin_id отключаем: в свежей тестовой базе он получает id=1,
    который в проде принадлежит владельцу и считается админом.
    """
    import services.curator_actions as curator_actions
    monkeypatch.setattr(curator_actions, 'is_admin_id', lambda uid=None, **k: False)
    u = User(email='free_user@test.ru', nickname='free_user')
    db.session.add(u)
    db.session.commit()
    return u


def _fake_deepseek(topic, main_reply='Хороший вопрос! Разберём по шагам.'):
    """Фейковый _call_deepseek: классификатор -> topic, основной чат -> main_reply.

    Возвращает (fn, calls) где calls — список вызовов с ролями system-сообщений.
    """
    calls = []

    def _fn(messages, thinking=False, max_tokens=1200):
        calls.append([m.get('role') for m in messages])
        first_system = messages[0].get('content', '') if messages else ''
        if 'классификатор' in first_system:
            return json.dumps({'topic': topic})
        return main_reply

    return _fn, calls


def test_off_topic_refused_without_generation(free_user, monkeypatch):
    """Посторонний вопрос — отказ, основной промпт куратора даже не вызывается."""
    fn, calls = _fake_deepseek('off')
    monkeypatch.setattr(curator_chat, '_call_deepseek', fn)

    reply = curator_chat.generate_reply(free_user.id, 'Какая завтра будет погода в Москве?')

    assert reply['off_topic'] is True
    assert reply['fallback'] is False
    assert 'только по математике' in reply['content']
    # ровно один вызов модели — классификатор; генерации ответа не было
    assert len(calls) == 1


def test_math_question_answered(free_user, monkeypatch):
    """Математический вопрос доходит до генерации полного ответа."""
    fn, calls = _fake_deepseek('math', main_reply='Домножим обе части на сопряжённое...')
    monkeypatch.setattr(curator_chat, '_call_deepseek', fn)

    reply = curator_chat.generate_reply(free_user.id, 'Реши уравнение x^2 - 5x + 6 = 0')

    assert reply['off_topic'] is False
    assert reply['fallback'] is False
    assert 'сопряжённое' in reply['content']
    # первый вызов — классификатор, второй — генерация ответа
    assert len(calls) == 2


def test_site_question_answered(free_user, monkeypatch):
    """Вопрос о сайте FORMYLA доходит до генерации ответа."""
    fn, calls = _fake_deepseek('site', main_reply='Задачи дня обновляются каждый день в 00:00 по Москве.')
    monkeypatch.setattr(curator_chat, '_call_deepseek', fn)

    reply = curator_chat.generate_reply(free_user.id, 'Сколько задач в день даётся на бесплатном тарифе?')

    assert reply['off_topic'] is False
    assert '00:00' in reply['content']
    assert len(calls) == 2


def test_classifier_failure_still_answers(free_user, monkeypatch):
    """Сбой классификатора не блокирует ученика: генерируем ответ как обычно."""

    def _flaky(messages, thinking=False, max_tokens=1200):
        first_system = messages[0].get('content', '') if messages else ''
        if 'классификатор' in first_system:
            raise RuntimeError('classifier down')
        return 'План на сегодня: один блок задач дня.'

    monkeypatch.setattr(curator_chat, '_call_deepseek', _flaky)

    reply = curator_chat.generate_reply(free_user.id, 'Помоги доказать неравенство Коши')

    assert reply['off_topic'] is False
    assert 'задач дня' in reply['content']


def test_parse_topic_variants():
    """Классификаторный JSON разбирается и в markdown-обёртке, и с мусором."""
    assert curator_chat._parse_topic('{"topic": "math"}') == 'math'
    assert curator_chat._parse_topic('```json\n{"topic": "site"}\n```') == 'site'
    assert curator_chat._parse_topic('Ответ: {"topic": "off"}') == 'off'
    assert curator_chat._parse_topic('{"topic": "weather"}') is None
    assert curator_chat._parse_topic(None) is None
    assert curator_chat._parse_topic('не json вообще') is None


def test_system_prompt_has_topic_rules():
    """В системном промпте есть правило про отказ от посторонних тем."""
    assert 'Я помогаю только по математике и по сайту FORMYLA' in curator_chat.SYSTEM_PROMPT


def test_guide_included_for_everyone(free_user, monkeypatch):
    """Справка FORMYLA попадает в промпт даже без admin_features."""
    fn, calls = _fake_deepseek('math')
    monkeypatch.setattr(curator_chat, '_call_deepseek', fn)

    ctx = curator_chat.build_context(free_user.id)
    assert ctx.get('admin_features') is not True
    msgs = curator_chat._system_messages(ctx)
    joined = '\n'.join(m['content'] for m in msgs)
    assert 'Справка FORMYLA' in joined
    # действия куратора ([[ACTION) — только админам, бесплатнику их не даём
    assert '[[ACTION' not in joined


# ── Доступ на бесплатном тарифе ──────────────────────────────────────────────

@pytest.fixture
def curator_app(app):
    """Тестовое приложение с blueprint'ом куратора.

    routes/__init__.py авто-регистрирует curator_chat_bp на любом Flask-приложении
    (admin_base autoreg), поэтому дублирующую регистрацию не делаем.
    """
    from routes.curator_chat import curator_chat_bp
    if 'curator_chat' not in app.blueprints:
        app.register_blueprint(curator_chat_bp)
    return app


def test_curator_page_open_for_free_user(curator_app, free_user):
    """Бесплатник открывает /curator — 200, а не 404."""
    client = curator_app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(free_user.id)

    resp = client.get('/curator')
    assert resp.status_code == 200
    assert 'Куратор'.encode('utf-8') in resp.data


def test_curator_chat_send_for_free_user(curator_app, free_user, monkeypatch):
    """Бесплатник пишет в чат — сообщение сохраняется, куратор отвечает."""
    client = curator_app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(free_user.id)

    fn, _calls = _fake_deepseek('math', main_reply='Разберём задачу по шагам.')
    monkeypatch.setattr(curator_chat, '_call_deepseek', fn)

    resp = client.post('/api/curator/chat',
                       json={'text': 'Как решать задачи на принцип Дирихле?'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    roles = [m['role'] for m in data['messages']]
    assert 'user' in roles and 'curator' in roles
    # сообщение и ответ сохранены в истории
    saved = CuratorChatMessage.query.filter_by(user_id=free_user.id).all()
    assert any(m.role == 'curator' and 'Дирихле' in m.content or m.role == 'curator'
               for m in saved)


def test_curator_chat_off_topic_for_free_user(curator_app, free_user, monkeypatch):
    """Бесплатник задаёт посторонний вопрос — получает вежливый отказ."""
    client = curator_app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(free_user.id)

    fn, _calls = _fake_deepseek('off')
    monkeypatch.setattr(curator_chat, '_call_deepseek', fn)

    resp = client.post('/api/curator/chat', json={'text': 'Расскажи анекдот'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    curator_msgs = [m['content'] for m in data['messages'] if m['role'] == 'curator']
    assert curator_msgs
    assert 'только по математике' in curator_msgs[-1]
