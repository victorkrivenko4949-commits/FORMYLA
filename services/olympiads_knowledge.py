# -*- coding: utf-8 -*-
"""База знаний по олимпиадам для ИИ-куратора FORMYLA."""

OLYMPIAD_KNOWLEDGE = {
    "fiztekh": {
        "name": "Олимпиада «Физтех»", "level": "high",
        "profile": "Техническая олимпиада МФТИ. Акцент: алгебра, тригонометрия, параметры; геометрия и оптимизация.",
        "perk": "Льготы при поступлении в МФТИ и технические вузы (БВИ/100 баллов).",
        "format": "Письменный, развёрнутые решения, 6–8 задач, нарастающая сложность.",
        "by_grade": {
            9:  {"focus": ["Квадратные уравнения, параметры", "Системы", "Текстовые задачи на движение/работу"],
                 "subtopic_keys": ["quadratic_parameters", "systems_modules_radicals"],
                 "must_know": ["Теорема Виета", "Метод интервалов", "Модули и иррациональные уравнения"]},
            10: {"focus": ["Тригонометрия", "Параметры и неравенства", "Показательные/логарифмические"],
                 "subtopic_keys": ["trigonometry", "systems_parameters_inequalities", "exp_log"],
                 "must_know": ["Тригонометрические уравнения и отбор корней", "Метод оценок", "Логарифмические неравенства"]},
            11: {"focus": ["Параметры (граф./аналит.)", "Тригонометрия повышенной сложности", "Стереометрия с координатами"],
                 "subtopic_keys": ["functions_graphs_parameters", "trigonometry_mixed", "stereometry_coordinates_vectors"],
                 "must_know": ["Разбор параметра по случаям", "Координатный метод", "Неравенство Коши"]},
        },
    },
    "kurchatov": {
        "name": "Олимпиада «Курчатов»", "level": "medium",
        "profile": "Олимпиада Курчатовского института. Классика: теория чисел, комбинаторика, логика, геометрия.",
        "perk": "Льготы в ряд вузов; широкий охват классов (6–11).",
        "format": "Отборочный онлайн + очный заключительный, 5–6 задач.",
        "by_grade": {
            7:  {"focus": ["Делимость и остатки", "Логика, инварианты", "Комбинаторика и графы"],
                 "subtopic_keys": ["divisibility_remainders", "logic_invariants", "combinatorics_graphs"],
                 "must_know": ["Признаки делимости", "Принцип Дирихле", "Чётность как инвариант"]},
            8:  {"focus": ["Диофантовы уравнения", "Подобие, окружность", "Комбинаторика и логика"],
                 "subtopic_keys": ["number_theory_diophantine", "geometry_similarity_circle", "combinatorics_logic_invariants"],
                 "must_know": ["Подобие треугольников", "Вписанные углы", "Инварианты и раскраски"]},
            9:  {"focus": ["Теория чисел", "Геометрия треугольника и окружности", "Игры, стратегии, инварианты"],
                 "subtopic_keys": ["number_theory", "geometry_triangle_circle", "logic_invariants_strategies"],
                 "must_know": ["НОД/НОК, модульная арифметика", "Теорема о биссектрисе", "Выигрышные стратегии"]},
            10: {"focus": ["Продвинутая теория чисел", "Комбинаторика, графы, вероятность", "Логика, множества"],
                 "subtopic_keys": ["number_theory_advanced", "combinatorics_graphs_probability", "logic_sets_functions"],
                 "must_know": ["Сравнения по модулю", "Подсчёт двумя способами", "Принцип включений-исключений"]},
            11: {"focus": ["Диофантовы задачи", "Комбинаторика, графы, логика", "Многочлены, последовательности"],
                 "subtopic_keys": ["number_theory_diophantine", "combinatorics_graphs_logic", "polynomials_sequences_fe"],
                 "must_know": ["Оценки в теории чисел", "Графовые модели", "Функциональные уравнения (базово)"]},
        },
    },
    "shag-v-budushchee": {
        "name": "Шаг в будущее", "level": "medium",
        "profile": "Инженерно-техническая олимпиада МГТУ им. Баумана. Алгебра, геометрия, прикладные задачи.",
        "perk": "Льготы в Бауманку и технические вузы.",
        "format": "Отборочный заочный + очный заключительный.",
        "by_grade": {
            8:  {"focus": ["Квадратные уравнения, Виет", "Подобие, окружность", "Текстовые задачи"],
                 "subtopic_keys": ["quadratic_vieta", "geometry_similarity_circle", "systems_word_problems"],
                 "must_know": ["Теорема Виета", "Подобие", "Составление уравнений по условию"]},
            9:  {"focus": ["Параметры", "Геометрия треугольника и окружности", "Системы, модули, радикалы"],
                 "subtopic_keys": ["quadratic_parameters", "geometry_triangle_circle", "systems_modules_radicals"],
                 "must_know": ["Разбор параметра", "Метрические соотношения", "Иррациональные уравнения"]},
            10: {"focus": ["Тригонометрия", "Стереометрия, векторы", "Показательные/логарифмические"],
                 "subtopic_keys": ["trigonometry", "stereometry_vectors", "exp_log"],
                 "must_know": ["Тригонометрические преобразования", "Векторный метод", "Свойства логарифмов"]},
            11: {"focus": ["Параметры с функциями", "Стереометрия: координаты, векторы", "Неравенства, оценки"],
                 "subtopic_keys": ["functions_graphs_parameters", "stereometry_coordinates_vectors", "inequalities_estimates"],
                 "must_know": ["Графический метод для параметров", "Координаты в пространстве", "Неравенство Коши-Буняковского"]},
        },
    },
    "otkrytaya": {
        "name": "Открытая олимпиада школьников", "level": "high",
        "profile": "Олимпиада ИТМО и вузов-партнёров. Сильная алгебра и теория чисел, нестандартные сюжеты.",
        "perk": "Льготы в ИТМО и вузы-партнёры.",
        "format": "1-й онлайн отборочный + заключительный.",
        "by_grade": {
            8:  {"focus": ["Квадратные уравнения и неравенства", "Делимость", "Комбинаторика и логика"],
                 "subtopic_keys": ["quadratic_vieta", "number_theory_diophantine", "combinatorics_logic_invariants"],
                 "must_know": ["Метод интервалов", "Делимость и остатки", "Перебор с обоснованием"]},
            9:  {"focus": ["Параметры", "Теория чисел", "Логика и стратегии"],
                 "subtopic_keys": ["quadratic_parameters", "number_theory", "logic_invariants_strategies"],
                 "must_know": ["Параметр по случаям", "Сравнения по модулю", "Инварианты"]},
            10: {"focus": ["Параметры и неравенства", "Продвинутая теория чисел", "Комбинаторика/вероятность"],
                 "subtopic_keys": ["systems_parameters_inequalities", "number_theory_advanced", "combinatorics_graphs_probability"],
                 "must_know": ["Метод оценок", "Модульная арифметика", "Подсчёт двумя способами"]},
            11: {"focus": ["Функции и параметры", "Многочлены, ФУ", "Комбинаторика, графы, логика"],
                 "subtopic_keys": ["functions_graphs_parameters", "polynomials_sequences_fe", "combinatorics_graphs_logic"],
                 "must_know": ["Исследование функций", "Функциональные уравнения", "Графовые рассуждения"]},
        },
    },
    "vsesibirskaya": {
        "name": "Всесибирская открытая олимпиада", "level": "high",
        "profile": "Олимпиада НГУ. Классические олимпиадные задачи: теория чисел, геометрия, комбинаторика, логика.",
        "perk": "Льготы в НГУ и сибирские вузы.",
        "format": "Отборочный + заключительный (весна).",
        "by_grade": {
            7:  {"focus": ["Делимость, остатки", "Логика, инварианты", "Комбинаторика"],
                 "subtopic_keys": ["divisibility_remainders", "logic_invariants", "combinatorics_graphs"],
                 "must_know": ["Принцип Дирихле", "Чётность", "Перебор случаев"]},
            8:  {"focus": ["Диофантовы уравнения", "Геометрия окружности", "Комбинаторика и логика"],
                 "subtopic_keys": ["number_theory_diophantine", "geometry_similarity_circle", "combinatorics_logic_invariants"],
                 "must_know": ["Вписанные/описанные окружности", "Раскраски", "Оценка + пример"]},
            9:  {"focus": ["Теория чисел", "Геометрия треугольника", "Игры и стратегии"],
                 "subtopic_keys": ["number_theory", "geometry_triangle_circle", "logic_invariants_strategies"],
                 "must_know": ["Модульная арифметика", "Подобие и площади", "Выигрышные стратегии"]},
            10: {"focus": ["Продвинутая теория чисел", "Комбинаторика, графы", "Логика, функции, множества"],
                 "subtopic_keys": ["number_theory_advanced", "combinatorics_graphs_probability", "logic_sets_functions"],
                 "must_know": ["Сравнения по модулю", "Двойной подсчёт", "Свойства функций"]},
            11: {"focus": ["Диофантовы задачи", "Комбинаторика, графы, логика", "Многочлены, ФУ"],
                 "subtopic_keys": ["number_theory_diophantine", "combinatorics_graphs_logic", "polynomials_sequences_fe"],
                 "must_know": ["Оценки", "Графовые модели", "Функциональные уравнения"]},
        },
    },
    "itmo": {
        "name": "Олимпиада ИТМО", "level": "high",
        "profile": "Профильная олимпиада ИТМО по математике. Алгебра, теория чисел, комбинаторика.",
        "perk": "Льготы при поступлении в ИТМО.",
        "format": "Отборочный (осень–зима) + заключительный (весна).",
        "by_grade": {
            9:  {"focus": ["Параметры", "Теория чисел", "Логика, стратегии"],
                 "subtopic_keys": ["quadratic_parameters", "number_theory", "logic_invariants_strategies"],
                 "must_know": ["Разбор параметра", "Сравнения по модулю", "Инварианты"]},
            10: {"focus": ["Параметры, неравенства", "Продвинутая теория чисел", "Комбинаторика/вероятность"],
                 "subtopic_keys": ["systems_parameters_inequalities", "number_theory_advanced", "combinatorics_graphs_probability"],
                 "must_know": ["Метод оценок", "Модульная арифметика", "Включения-исключения"]},
            11: {"focus": ["Функции и параметры", "Многочлены, последовательности, ФУ", "Комбинаторика, графы, логика"],
                 "subtopic_keys": ["functions_graphs_parameters", "polynomials_sequences_fe", "combinatorics_graphs_logic"],
                 "must_know": ["Исследование функций", "Функциональные уравнения", "Графовые рассуждения"]},
        },
    },
    "nadezhda-energetiki": {
        "name": "Надежда энергетики", "level": "medium",
        "profile": "Инженерная олимпиада (НИУ МЭИ и партнёры). Прикладная алгебра, геометрия, текстовые задачи.",
        "perk": "Льготы в энергетические/технические вузы (МЭИ и др.).",
        "format": "Отборочный + заключительный (весна).",
        "by_grade": {
            8:  {"focus": ["Квадратные уравнения, Виет", "Подобие, окружность", "Текстовые задачи"],
                 "subtopic_keys": ["quadratic_vieta", "geometry_similarity_circle", "systems_word_problems"],
                 "must_know": ["Теорема Виета", "Подобие", "Составление уравнений"]},
            9:  {"focus": ["Параметры", "Геометрия треугольника и окружности", "Системы, модули, радикалы"],
                 "subtopic_keys": ["quadratic_parameters", "geometry_triangle_circle", "systems_modules_radicals"],
                 "must_know": ["Разбор параметра", "Метрические соотношения", "Иррациональные уравнения"]},
            10: {"focus": ["Тригонометрия", "Стереометрия, векторы", "Показательные/логарифмические"],
                 "subtopic_keys": ["trigonometry", "stereometry_vectors", "exp_log"],
                 "must_know": ["Тригонометрические преобразования", "Векторный метод", "Свойства логарифмов"]},
            11: {"focus": ["Параметры с функциями", "Стереометрия: координаты", "Неравенства, оценки"],
                 "subtopic_keys": ["functions_graphs_parameters", "stereometry_coordinates_vectors", "inequalities_estimates"],
                 "must_know": ["Графический метод", "Координаты в пространстве", "Неравенство Коши"]},
        },
    },
    "rosatom": {
        "name": "Олимпиада «Росатом»", "level": "medium",
        "profile": "Олимпиада Росатома. Алгебра, теория чисел, комбинаторика с прикладным уклоном.",
        "perk": "Льготы в инженерные/технические и атомные вузы (НИЯУ МИФИ и партнёры).",
        "format": "Отборочный + заключительный (весна).",
        "by_grade": {
            8:  {"focus": ["Квадратные уравнения, Виет", "Делимость", "Комбинаторика и логика"],
                 "subtopic_keys": ["quadratic_vieta", "number_theory_diophantine", "combinatorics_logic_invariants"],
                 "must_know": ["Теорема Виета", "Делимость и остатки", "Перебор с обоснованием"]},
            9:  {"focus": ["Параметры", "Теория чисел", "Логика, стратегии"],
                 "subtopic_keys": ["quadratic_parameters", "number_theory", "logic_invariants_strategies"],
                 "must_know": ["Разбор параметра", "Сравнения по модулю", "Инварианты"]},
            10: {"focus": ["Параметры, неравенства", "Продвинутая теория чисел", "Комбинаторика/вероятность"],
                 "subtopic_keys": ["systems_parameters_inequalities", "number_theory_advanced", "combinatorics_graphs_probability"],
                 "must_know": ["Метод оценок", "Модульная арифметика", "Двойной подсчёт"]},
            11: {"focus": ["Функции и параметры", "Многочлены, последовательности", "Комбинаторика, графы, логика"],
                 "subtopic_keys": ["functions_graphs_parameters", "polynomials_sequences_fe", "combinatorics_graphs_logic"],
                 "must_know": ["Исследование функций", "Последовательности", "Графовые рассуждения"]},
        },
    },
    "inzhenernaya": {
        "name": "Инженерная олимпиада школьников", "level": "medium",
        "profile": "Инженерная олимпиада (НИЯУ МИФИ и партнёры). Прикладная математика, алгебра, геометрия.",
        "perk": "Льготы в инженерно-физические вузы.",
        "format": "Отборочный + заключительный (весна).",
        "by_grade": {
            8:  {"focus": ["Квадратные уравнения, Виет", "Подобие, окружность", "Текстовые задачи"],
                 "subtopic_keys": ["quadratic_vieta", "geometry_similarity_circle", "systems_word_problems"],
                 "must_know": ["Теорема Виета", "Подобие", "Составление уравнений по условию"]},
            9:  {"focus": ["Параметры", "Геометрия треугольника и окружности", "Системы, модули, радикалы"],
                 "subtopic_keys": ["quadratic_parameters", "geometry_triangle_circle", "systems_modules_radicals"],
                 "must_know": ["Разбор параметра", "Метрические соотношения", "Иррациональные уравнения"]},
            10: {"focus": ["Тригонометрия", "Стереометрия, векторы", "Показательные/логарифмические"],
                 "subtopic_keys": ["trigonometry", "stereometry_vectors", "exp_log"],
                 "must_know": ["Тригонометрические преобразования", "Векторный метод", "Свойства логарифмов"]},
            11: {"focus": ["Параметры с функциями", "Стереометрия: координаты, векторы", "Неравенства, оценки"],
                 "subtopic_keys": ["functions_graphs_parameters", "stereometry_coordinates_vectors", "inequalities_estimates"],
                 "must_know": ["Графический метод для параметров", "Координаты в пространстве", "Неравенство Коши-Буняковского"]},
        },
    },
}


# ─── Хелперы базы знаний ──────────────────────────────────────────────────────
def get_olympiad_knowledge(slug, grade=None):
    """Вернуть знания по олимпиаде; если задан grade — срез по классу."""
    data = OLYMPIAD_KNOWLEDGE.get(slug)
    if not data:
        return None
    if grade is None:
        return data
    try:
        grade_int = int(grade)
    except (TypeError, ValueError):
        return data
    return {
        "name": data["name"], "level": data["level"], "profile": data["profile"],
        "perk": data["perk"], "format": data["format"],
        "grade": grade_int, "grade_info": data["by_grade"].get(grade_int),
    }


def recommend_olympiads_for(grade, weak_subtopic_keys=None, limit=3):
    """
    Подобрать олимпиады для класса, отсортировав по совпадению со слабыми подтемами.
    weak_subtopic_keys — список key слабых подтем ученика (из build_profile).
    Возвращает список slug в порядке релевантности.
    """
    weak = set(weak_subtopic_keys or [])
    scored = []
    try:
        grade_int = int(grade)
    except (TypeError, ValueError):
        return []
    for slug, data in OLYMPIAD_KNOWLEDGE.items():
        ginfo = data["by_grade"].get(grade_int)
        if not ginfo:
            continue
        keys = set(ginfo.get("subtopic_keys", []))
        overlap = len(keys & weak)
        scored.append((overlap, slug))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [slug for _, slug in scored[:limit]]


def build_olympiads_context(grade, weak_subtopic_keys=None):
    """Текстовый блок для system_prompt DeepSeek: какие олимпиады подходят классу и что для них нужно."""
    lines = []
    try:
        grade_int = int(grade)
    except (TypeError, ValueError):
        return "Класс не указан."
    for slug, data in OLYMPIAD_KNOWLEDGE.items():
        ginfo = data["by_grade"].get(grade_int)
        if not ginfo:
            continue
        focus = "; ".join(ginfo.get("focus", []))
        must = "; ".join(ginfo.get("must_know", []))
        lines.append(
            f"• {data['name']} ({data['level']}, {grade_int} кл.): "
            f"фокус — {focus}. Надо уметь: {must}. Льгота: {data['perk']}."
        )
    return "\n".join(lines) if lines else f"Для {grade_int} класса нет подходящих олимпиад в базе."
