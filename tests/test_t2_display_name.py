# tests/test_t2_display_name.py — тесты функции display_name_from_email

from services.user_helpers import display_name_from_email


def test_display_name_victorkrvvk():
    """victorkrvvk@gmail.com -> Виктор (словарное имя, остаток отбрасывается)."""
    assert display_name_from_email('victorkrvvk@gmail.com') == 'Виктор'


def test_display_name_anna1990():
    """anna1990@mail.ru -> Анна (словарное имя, цифры удаляются)."""
    assert display_name_from_email('anna1990@mail.ru') == 'Анна'


def test_display_name_dot_petrov():
    """k.petrov@yandex.ru -> Пётров (часть после точки, из словаря)."""
    assert display_name_from_email('k.petrov@yandex.ru') == 'Пётров'


def test_display_name_only_digits():
    """12345@bk.ru -> Игрок123 (только цифры, fallback)."""
    assert display_name_from_email('12345@bk.ru') == 'Игрок123'


def test_display_name_dot_sergeyev():
    """dmitry.sergeyev@gmail.com -> Сергеев (имя после точки, префикс + суффикс с фонологией)."""
    assert display_name_from_email('dmitry.sergeyev@gmail.com') == 'Сергеев'
