import re
import json
import difflib
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Признаки утечки решения в условии задачи
LEAK_PATTERNS = [
    r'\bРешение\s*[:.]',
    r'\bДоказательство\s*[:.]',
    r'\bОтвет\s*[:.]',
    r'\bSolution\s*[:.]',
    r'\(\s*используйте\s+',
    r'\(\s*подсказка\s*[:.]',
    r'\bитак,?\s+получаем\b',
    r'\bследовательно,?\s+x\s*=',
    r'\bтаким\s+образом,?\s+ответ\b',
    r'\bзначит,?\s+ответ\b',
    r'\bОтвет:\s*\d',
    r'\bAnswer:\s*\d',
]

# Русские математические слова, которые нужно оборачивать в \text{} внутри формул
RUSSIAN_MATH_WORDS = [
    'НОД', 'НОК', 'tg', 'ctg', 'arctg', 'arcctg',
]




def is_plagiarism(generated_text: str, examples: list, threshold: float = 0.65):
    """
    Checks similarity between generated_text and any of the examples.
    Returns (True, similarity) if similarity > threshold.
    """
    if not examples:
        return False, 0.0

    max_sim = 0.0
    for example in examples:
        gen_norm = re.sub(r'\d+', 'N', generated_text.lower())
        gen_norm = re.sub(r'\s+', ' ', gen_norm).strip()
        ex_norm = re.sub(r'\d+', 'N', str(example).lower())
        ex_norm = re.sub(r'\s+', ' ', ex_norm).strip()

        similarity = difflib.SequenceMatcher(None, gen_norm, ex_norm).ratio()
        max_sim = max(max_sim, similarity)

    return max_sim > threshold, max_sim

def has_index_confusion(task_text: str) -> tuple:
    """
    Детектирует путаницу между индексами (f_1, f_2) и степенями (f², f^2)
    в условии задачи.

    Типичный баг LLM: пишет f1(x), f²(x), f100(x) вместо
    \\(f_1(x)\\), \\(f_2(x)\\), \\(f_{100}(x)\\).

    Returns:
        (bool, str) — (есть_путаница, описание_проблемы)
    """
    # Убираем содержимое LaTeX-формул — там индексы правильные
    text_outside_latex = re.sub(
        r'\\\(.*?\\\)|\\\[.*?\\\]', '', task_text, flags=re.DOTALL
    )

    # Проверка 1: голые индексы вне LaTeX — f1(x), f2(x), x1, a100
    bare_indexes = re.findall(r'\b[a-zA-Z]\d+\s*\(', text_outside_latex)
    if len(bare_indexes) >= 2:
        return (
            True,
            "Найдены индексы без LaTeX-обёрток: "
            + str(bare_indexes[:3])
            + r". Должно быть \(f_1(x)\) вместо f1(x)"
        )

    # Проверка 2: Unicode-степени (², ³, ...) рядом с числовыми индексами
    unicode_powers = re.findall(r'[a-zA-Z\u0430-\u044f\u0410-\u042f][²³⁴⁵⁶⁷⁸⁹]', task_text)
    if unicode_powers:
        if re.search(r'[a-zA-Z]\d+', text_outside_latex):
            return (
                True,
                "Смешение Unicode-степеней "
                + str(unicode_powers[:3])
                + " и числовых индексов без LaTeX — путаница нотаций"
            )
        if re.search(r'[a-zA-Z]_\d', task_text):
            return (
                True,
                "Unicode-степени "
                + str(unicode_powers[:3])
                + " вместе с LaTeX-индексами — несогласованная нотация"
            )

    # Проверка 3: f^N(x) рядом с числовыми индексами — подозрение на путаницу
    if re.search(r'[a-zA-Z]\^[2-9]\s*\([a-zA-Z]', task_text):
        if re.search(r'\b[a-zA-Z]\d+\b|[a-zA-Z]_\d', task_text):
            return (
                True,
                "f^N(x) рядом с числовыми индексами — подозрение на путаницу степени и индекса"
            )

    # Проверка 4: индексы >9 без фигурных скобок внутри LaTeX: \(a_10\) вместо \(a_{10}\)
    bad_big_index = re.findall(r'[a-zA-Z]_\d{2,}', task_text)
    if bad_big_index:
        return (
            True,
            "Числовые индексы >9 без фигурных скобок: "
            + str(bad_big_index[:3])
            + r". Должно быть \(f_{10}\)"
        )

    # Проверка 5: потерянная степень после скобки — ")2", ")3" вне LaTeX
    # Например: "(n + 1)2" вместо "\((n+1)^2\)"
    lost_power_after_paren = re.findall(r'\)\d', text_outside_latex)
    if lost_power_after_paren:
        return (
            True,
            "Цифра сразу после ) — вероятно потерянная степень: "
            + str(lost_power_after_paren[:3])
            + r". Должно быть \((...)^N\)"
        )

    # Проверка 6: большие числа без LaTeX в математическом контексте
    # Например: "n > 10100" вместо "\(n > 10^{100}\)"
    big_numbers = re.findall(r'\b1\d{4,}\b', text_outside_latex)
    if big_numbers:
        # Только если рядом есть математический контекст
        if re.search(r'число|больше|меньше|n\s*[><=]|m\s*[><=]|k\s*[><=]', text_outside_latex):
            return (
                True,
                "Подозрительно большое число без LaTeX: "
                + str(big_numbers[:3])
                + r". Возможно потерянная степень типа \(10^{100}\)"
            )

    return False, ""


def has_solution_leak(task_text: str) -> tuple:
    """
    Проверяет, есть ли утечка решения в условии задачи.

    Returns:
        (bool, str) — (есть_утечка, описание_паттерна)
    """
    for pattern in LEAK_PATTERNS:
        match = re.search(pattern, task_text, re.IGNORECASE)
        if match:
            return True, f"Найден паттерн: '{match.group()}'"
    return False, ""


def fix_latex(text: str) -> str:
    """
    Автофикс типичных проблем с LaTeX в тексте задачи.

    Исправляет:
    - $$...$$ -> \\[...\\]
    - $...$ -> \\(...\\)
    - \\\\frac -> \\frac (двойной backslash)
    - frac{...} без backslash -> \\frac{...}
    - sqrt{...} без backslash -> \\sqrt{...}
    """
    if not text:
        return text

    for u,l in [(chr(8730),r"\\sqrt"),(chr(8805),r"\\geq"),(chr(8804),r"\\leq"),(chr(8800),r"\\neq"),(chr(178),"2"),(chr(179),"3")]:
        text=text.replace(u,l)

    # Сначала исправляем $$...$$ -> \[...\] (до одиночных $)
    text = re.sub(
        r'\$\$([^\$]{1,1000}?)\$\$',
        r'\\[\1\\]',
        text,
        flags=re.DOTALL
    )

    # $...$ -> \(...\) (но не если это знак доллара/рубля перед числом)
    # Эвристика: $ окружённый математическими символами — формула
    text = re.sub(
        r'\$([^\$\n]{1,200}?)\$',
        r'\\(\1\\)',
        text
    )

    # Двойной backslash перед командами -> одинарный
    # \\frac -> \frac, \\sqrt -> \sqrt и т.д.
    math_commands = [
        'frac', 'sqrt', 'sum', 'int', 'cdot', 'times', 'leq', 'geq',
        'neq', 'infty', 'pi', 'alpha', 'beta', 'gamma', 'delta',
        'theta', 'lambda', 'mu', 'sigma', 'phi', 'psi', 'omega',
        'left', 'right', 'begin', 'end', 'text', 'mathbb', 'mathbf',
        'overline', 'underline', 'hat', 'vec', 'bar', 'dot',
        'ldots', 'cdots', 'vdots', 'ddots', 'pm', 'mp', 'div',
        'equiv', 'approx', 'sim', 'subset', 'supset', 'cup', 'cap',
        'in', 'notin', 'forall', 'exists', 'neg', 'wedge', 'vee',
        'lfloor', 'rfloor', 'lceil', 'rceil', 'binom', 'pmod',
    ]
    for cmd in math_commands:
        # \\\\cmd -> \cmd (четыре backslash -> один)
        text = text.replace(f'\\\\\\\\{cmd}', f'\\{cmd}')
        # \\cmd -> \cmd (два backslash -> один), но только если не уже правильно
        # Используем regex чтобы не трогать уже правильные \cmd
        text = re.sub(
            r'\\\\(' + re.escape(cmd) + r')(?=[^a-zA-Z]|$)',
            r'\\\1',
            text
        )

    # frac{...} без backslash -> \frac{...}
    text = re.sub(
        r'(?<![\\\w])frac\{',
        r'\\frac{',
        text
    )

    # sqrt{...} без backslash -> \sqrt{...}
    text = re.sub(
        r'(?<![\\\w])sqrt\{',
        r'\\sqrt{',
        text
    )

    # sqrt(...) без backslash -> \sqrt(...)
    text = re.sub(
        r'(?<![\\\w])sqrt\(',
        r'\\sqrt(',
        text
    )

    return text


def _extract_json_from_response(raw_response: str) -> Optional[dict]:
    """
    Пытается извлечь JSON из ответа LLM.
    Обрабатывает случаи когда JSON обёрнут в markdown-блоки.
    """
    if not raw_response:
        return None

    text = raw_response.strip()

    # Попытка 1: прямой парсинг
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Попытка 2: извлечь из ```json ... ``` блока
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Попытка 3: найти первый { ... } в тексте
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Попытка 4: убрать trailing запятые (частая ошибка LLM)
    cleaned = re.sub(r',\s*([}\]])', r'\1', text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    return None


def validate_generated_task(raw_response: str, few_shot_texts=None) -> dict:
    """
    Парсит ответ LLM, валидирует структуру, фиксит LaTeX.

    Args:
        raw_response: Сырой текст ответа от LLM

    Returns:
        {
            'valid': bool,
            'task': dict | None,
            'errors': list[str]
        }
    """
    errors = []

    # Парсим JSON
    data = _extract_json_from_response(raw_response)
    if data is None:
        logger.warning(f"Не удалось распарсить JSON. Ответ: {raw_response[:200]}")
        return {
            'valid': False,
            'task': None,
            'errors': ['Невалидный JSON: не удалось распарсить ответ LLM'],
        }

    if not isinstance(data, dict):
        return {
            'valid': False,
            'task': None,
            'errors': [f'Ожидался JSON-объект, получен {type(data).__name__}'],
        }

    # Проверяем обязательные поля
    required_fields = ['task_text', 'correct_answer', 'solution', 'topic', 'difficulty']
    for field in required_fields:
        if field not in data or data[field] is None or str(data[field]).strip() == '':
            errors.append(f'Отсутствует или пустое поле: {field}')

    if errors:
        return {'valid': False, 'task': None, 'errors': errors}

    # Фиксим LaTeX в условии и решении
    data['task_text'] = fix_latex(str(data['task_text']))
    data['solution'] = fix_latex(str(data['solution']))
    if 'correct_answer' in data and data['correct_answer']:
        data['correct_answer'] = fix_latex(str(data['correct_answer']))

    # Проверяем утечку решения в условии
    has_leak, leak_msg = has_solution_leak(data['task_text'])
    if has_leak:
        errors.append(f'Утечка решения в условии: {leak_msg}')
        return {'valid': False, 'task': data, 'errors': errors}

    # Проверяем путаницу индексов и степеней
    has_conf, conf_msg = has_index_confusion(data['task_text'])
    if has_conf:
        errors.append('Путаница индексов/степеней: ' + conf_msg)
        return {'valid': False, 'task': data, 'errors': errors}

    # Минимальная длина условия
    if len(data['task_text'].strip()) < 30:
        errors.append(
            f'Слишком короткое условие ({len(data["task_text"])} символов, минимум 30)'
        )
        return {'valid': False, 'task': data, 'errors': errors}

    # Максимальная длина условия (защита от "задачи с решением")
    if len(data['task_text'].strip()) > 3000:
        errors.append(
            f'Слишком длинное условие ({len(data["task_text"])} символов, максимум 3000) — '
            f'возможно, в условие включено решение'
        )
        return {'valid': False, 'task': data, 'errors': errors}

    # Difficulty в диапазоне 1-4
    try:
        diff = int(data['difficulty'])
        if not 1 <= diff <= 4:
            errors.append(f'Difficulty {diff} вне диапазона 1-4')
            return {'valid': False, 'task': data, 'errors': errors}
        data['difficulty'] = diff
    except (ValueError, TypeError):
        errors.append(f'Difficulty не является числом: {data["difficulty"]}')
        return {'valid': False, 'task': data, 'errors': errors}

    # Проверяем что условие не содержит слово "Решение" в любом регистре
    # (дополнительная проверка помимо LEAK_PATTERNS)
    task_lower = data['task_text'].lower()
    forbidden_in_task = ['решение:', 'доказательство:', 'ответ:', 'solution:', 'answer:']
    for forbidden in forbidden_in_task:
        if forbidden in task_lower:
            errors.append(
                f'Условие содержит запрещённое слово: "{forbidden}"'
            )
            return {'valid': False, 'task': data, 'errors': errors}


    # Минимальная длина решения
    solution_text = str(data.get('solution', ''))
    if len(solution_text.strip()) < 200:
        errors.append(
            f'Решение слишком короткое ({len(solution_text)} символов). '
            f'Минимум 200, желательно 500+.'
        )
        return {'valid': False, 'task': data, 'errors': errors}

    # Ответ не должен быть размытым
    answer_text = str(data.get('correct_answer', '')).strip().lower()
    vague_answers = [
        'зависит', 'любой', 'любое', 'не определено',
        'неизвестно', 'может быть разным', 'нет ответа'
    ]
    for vague in vague_answers:
        if vague in answer_text:
            errors.append(
                f'Ответ размытый ("{answer_text[:50]}"). Нужен конкретный ответ.'
            )
            return {'valid': False, 'task': data, 'errors': errors}


    # Проверяем плагиат относительно few-shot примеров
    if few_shot_texts:
        is_plag, sim = is_plagiarism(data['task_text'], few_shot_texts)
        if is_plag:
            errors.append(
                f'Задача слишком похожа на пример из БД '
                f'(схожесть {sim:.0%}). Нужна оригинальная.'
            )
            return {'valid': False, 'task': data, 'errors': errors}

    # Проверяем упоминание авторов задач (признак копирования)
    author_patterns = [
        r'[А-ЯA-Z]\.\s*[А-ЯA-Z][а-яa-z]+',  # А. Храбров
        r'автор', r'составитель',
    ]
    for pat in author_patterns:
        if re.search(pat, data['task_text']):
            errors.append(
                'Условие содержит имя автора — признак копирования реальной задачи.'
            )
            return {'valid': False, 'task': data, 'errors': errors}

    # Проверяем unicode-математику вместо LaTeX
    unicode_math = re.findall(r'[√≥≤≠∈∑∫⩽⩾∀∃∩∪]', data['task_text'])
    if len(unicode_math) >= 3:
        errors.append(
            'Условие содержит unicode-matematiku vmesto LaTeX. '
            'Ispolzujte: \\sqrt, \\geq, \\leq, \\neq, \\in, \\sum, \\int.'
        )
        return {'valid': False, 'task': data, 'errors': errors}

    # Добавляем key_idea если отсутствует
    if 'key_idea' not in data or not data.get('key_idea'):
        data['key_idea'] = ''

    logger.info(
        f"Задача прошла валидацию: тема='{data.get('topic')}', "
        f"сложность={data.get('difficulty')}, "
        f"длина условия={len(data['task_text'])}"
    )

    return {'valid': True, 'task': data, 'errors': []}
