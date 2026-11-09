# -*- coding: utf-8 -*-
"""PARENT_PAYLINK_V1: ученик копирует саму оплату ЮKassa для родителя.

Запуск: pytest tests/test_parent_paylink.py -q
"""
import pytest

from tests.test_premium_gift import gift_app, _make_user, _login, _plan  # noqa: F401


def test_student_paylink_demo_activates_student(gift_app):
    student = _make_user('pl_student@example.invalid', 'pl_student', role='student', uid=1)
    client = gift_app.test_client()
    _login(client, student)

    resp = client.post('/payments/premium/create', json={
        'plan': 'premium_intense', 'mode': 'parent_link'})
    assert resp.status_code == 200
    d = resp.get_json()
    assert d['ok'] and d['pay_url'] and d['amount'] == 800
    assert '/pay/premium/done' in d['pay_url']

    # Родитель открывает ссылку БЕЗ входа
    anon = gift_app.test_client()
    from flask import g
    g.pop('_login_user', None)
    path = d['pay_url'].split('://', 1)[1].split('/', 1)[1]
    r = anon.get('/' + path)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'Оплата прошла' in html and 'pl_student' in html
    assert _plan(student.id)['is_premium']

    # Повторное открытие не продлевает второй раз (идемпотентно)
    exp1 = _plan(student.id)['expires_at']
    anon.get('/' + path)
    assert _plan(student.id)['expires_at'] == exp1


def test_parent_cannot_make_paylink(gift_app):
    parent = _make_user('pl_parent@example.invalid', 'pl_parent', role='parent')
    client = gift_app.test_client()
    _login(client, parent)
    resp = client.post('/payments/premium/create', json={
        'plan': 'premium_intense', 'mode': 'parent_link'})
    assert resp.status_code in (400, 403)


def test_unknown_order_404(gift_app):
    r = gift_app.test_client().get('/pay/premium/done?order_id=nope')
    assert r.status_code == 404


def test_demo_flag_required(gift_app):
    student = _make_user('pl_s2@example.invalid', 'pl_s2', role='student', uid=5)
    client = gift_app.test_client()
    _login(client, student)
    d = client.post('/payments/premium/create', json={
        'plan': 'premium_calm', 'mode': 'parent_link'}).get_json()
    oid = d['order_id']
    from flask import g
    g.pop('_login_user', None)
    r = gift_app.test_client().get(f'/pay/premium/done?order_id={oid}')
    assert 'Проверяем оплату' in r.get_data(as_text=True)
    assert not _plan(student.id)['is_premium']


def test_checkout_has_copy_button(gift_app):
    student = _make_user('pl_s3@example.invalid', 'pl_s3', role='student', uid=7452)
    client = gift_app.test_client()
    _login(client, student)
    r = client.get('/payments/premium/checkout?plan=premium_intense')
    assert r.status_code == 200
    assert 'Скопировать оплату для родителя' in r.get_data(as_text=True)
