# services/user_helpers.py — хелперы для отображения пользователей
# Функция display_name_from_email извлекает читаемое имя из email-адреса

import re

# Словарь известных имён: английская транслитерация -> русское имя
_NAME_DICT = {
    'victor': 'Виктор',
    'anna': 'Анна',
    'petr': 'Пётр',
    'ivan': 'Иван',
    'elena': 'Елена',
    'dmitry': 'Дмитрий',
    'sergey': 'Сергей',
    'olga': 'Ольга',
    'maxim': 'Максим',
    'alexey': 'Алексей',
    'maria': 'Мария',
    'natalia': 'Наталья',
    'ekaterina': 'Екатерина',
    'andrey': 'Андрей',
    'nadezhda': 'Надежда',
}

# Таблица посимвольной транслитерации en->ru.
# Ключи отсортированы по убыванию длины для жадного разбора.
_TRANSLIT_TABLE = [
    ('zh', 'ж'), ('ch', 'ч'), ('sh', 'ш'),
    ('ya', 'я'), ('yu', 'ю'), ('yo', 'ё'),
    ('ju', 'ю'), ('ja', 'я'),
    ('a', 'а'), ('b', 'б'), ('v', 'в'),
    ('g', 'г'), ('d', 'д'), ('e', 'е'),
    ('z', 'з'), ('i', 'и'), ('k', 'к'),
    ('l', 'л'), ('m', 'м'), ('n', 'н'),
    ('o', 'о'), ('p', 'п'), ('r', 'р'),
    ('s', 'с'), ('t', 'т'), ('u', 'у'),
    ('f', 'ф'), ('h', 'х'), ('c', 'ц'),
    ('y', 'й'),
]

_VOWELS = set('аеёиоуыэюя')


def _transliterate(text: str) -> str:
    """Посимвольная транслитерация en->ru по таблице."""
    result = []
    i = 0
    text_lower = text.lower()
    while i < len(text_lower):
        matched = False
        for en_chunk, ru_chunk in _TRANSLIT_TABLE:
            if text_lower[i:].startswith(en_chunk):
                result.append(ru_chunk)
                i += len(en_chunk)
                matched = True
                break
        if not matched:
            result.append(text_lower[i])
            i += 1
    return ''.join(result)


def _merge_ru(base: str, suffix: str) -> str:
    """Соединяет русское имя-основу с транслитерированным суффиксом.

    Фонетические правила русского языка:
    - Если основа заканчивается на 'й' и суффикс начинается с гласной:
      'й' выпадает (Сергей + ев -> Сергеев, Андрей + ев -> Андреев).
    """
    if not suffix:
        return base
    if base.endswith('й') and suffix and suffix[0] in _VOWELS:
        return base[:-1] + suffix
    return base + suffix


def display_name_from_email(email: str) -> str:
    """Извлекает читаемое имя из email-адреса.

    Логика:
    1. Если email пустой, None или без '@' — возвращает 'Игрок'.
    2. Берёт часть до '@', убирает цифры.
    3. Если после удаления цифр пусто — 'Игрок' + первые 3 символа до '@' (верхний регистр).
    4. Если содержит точку — берёт последнюю часть после последней точки.
       Если после точки пусто — берёт всю часть до '@' без точки.
    5. Проверяет словарь известных имён (точное совпадение).
    6. Если точного совпадения нет:
       - ищет самый длинный префикс в словаре.
       - Для dot-имён: словарное значение + транслитерация остатка (с фонологией).
       - Для обычных имён: только словарное значение, остаток отбрасывается.
    7. Если префикс не найден — полная транслитерация.
    8. Если результат пустой — 'Игрок' + первые 3 символа до '@' (верхний регистр).
    9. Первая буква заглавная, остальные строчные.
    """
    if not email or '@' not in email:
        return 'Игрок'

    local_part = email.split('@')[0]
    # Убираем все цифры
    name_part_without_digits = re.sub(r'\d+', '', local_part)

    if not name_part_without_digits:
        # Только цифры — fallback на первые 3 символа до @
        fallback = local_part[:3].upper()
        return f'Игрок{fallback}'

    # Определяем, содержит ли локальная часть точку
    has_dot = '.' in local_part
    if has_dot:
        # Берём последнюю часть после последней точки
        name_part = name_part_without_digits.rsplit('.', 1)[-1]
        if not name_part:
            # После точки пусто — берём всю часть до @ без последней точки
            name_part = re.sub(r'\d+', '', local_part.rsplit('.', 1)[0])
    else:
        name_part = name_part_without_digits

    name_lower = name_part.lower()

    # 1. Проверяем точное совпадение в словаре
    if name_lower in _NAME_DICT:
        return _NAME_DICT[name_lower]

    # 2. Ищем самый длинный префикс из словаря
    best_prefix = ''
    best_value = ''
    for en_key, ru_value in _NAME_DICT.items():
        if name_lower.startswith(en_key) and len(en_key) > len(best_prefix):
            best_prefix = en_key
            best_value = ru_value

    if best_prefix:
        remainder = name_lower[len(best_prefix):]
        if remainder and has_dot:
            # Для dot-имён: значение словаря + транслитерация остатка с фонологией
            transliterated = _transliterate(remainder)
            result = _merge_ru(best_value, transliterated)
        else:
            # Для обычных имён: только значение словаря, остаток отбрасывается
            result = best_value
    else:
        # 3. Полная транслитерация
        result = _transliterate(name_lower)

    if not result:
        fallback = local_part[:3].upper()
        return f'Игрок{fallback}'

    # Первая буква заглавная, остальные строчные
    return result[0].upper() + result[1:].lower()
