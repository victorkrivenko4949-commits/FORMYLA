# -*- coding: utf-8 -*-
"""PWA для всех, но только на Android (06.11.2026).

Кнопка «Скачать приложение» (manifest + pwa_install.js) вставляется всем на Android,
на iPhone и компьютере — нет; тестовые аккаунты видят её на любом устройстве.
Запуск: pytest tests/test_pwa_access.py -q
"""
import os
import sys

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routes import pwa  # noqa: E402

ANDROID = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36'
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile Safari/604.1'
DESKTOP = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36'
PAGE = '<!DOCTYPE html><html><head><title>x</title></head><body>hi</body></html>'


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setattr(pwa, '_ALLOWED_USERS', {'*'})
    monkeypatch.setattr(pwa, '_PLATFORMS', {'android'})
    monkeypatch.setattr(pwa, '_TEST_USERS', {'lavrik', 'victor'})
    app = Flask(__name__)

    @app.route('/')
    def index():
        return PAGE

    app.after_request(pwa._inject)
    return app


def _as(monkeypatch, *names):
    monkeypatch.setattr(pwa, '_current_user_names', lambda: (object() if names else None, set(names)))


def _html(app, ua):
    return app.test_client().get('/', headers={'User-Agent': ua}).get_data(as_text=True)


def test_defaults_open_to_everyone_on_android():
    assert pwa._ALLOWED_USERS == {'*'} or os.environ.get('PWA_ALLOWED_USERS')
    assert pwa._PLATFORMS == {'android'} or os.environ.get('PWA_PLATFORMS')


@pytest.mark.parametrize('names', [(), ('student1',)])
def test_android_gets_install_button(app, monkeypatch, names):
    _as(monkeypatch, *names)
    html = _html(app, ANDROID)
    assert 'rel="manifest"' in html and 'pwa_install.js?v=6' in html


@pytest.mark.parametrize('ua', [IPHONE, DESKTOP])
def test_other_devices_get_nothing(app, monkeypatch, ua):
    _as(monkeypatch, 'student1')
    html = _html(app, ua)
    assert 'rel="manifest"' not in html and 'pwa_install.js' not in html


def test_test_accounts_see_it_everywhere(app, monkeypatch):
    _as(monkeypatch, 'victor')
    assert 'pwa_install.js' in _html(app, DESKTOP)


def test_platforms_star_opens_all_devices(app, monkeypatch):
    monkeypatch.setattr(pwa, '_PLATFORMS', {'*'})
    _as(monkeypatch, 'student1')
    assert 'pwa_install.js' in _html(app, IPHONE)


def test_user_list_still_restricts(app, monkeypatch):
    monkeypatch.setattr(pwa, '_ALLOWED_USERS', {'lavrik'})
    _as(monkeypatch, 'student1')
    assert 'pwa_install.js' not in _html(app, ANDROID)


def test_android_label_in_script():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(root, 'static', 'js', 'pwa_install.js'), encoding='utf-8').read()
    assert 'Скачать приложение для Android' in js
