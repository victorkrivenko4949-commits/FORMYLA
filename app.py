from flask import Flask, render_template, request, abort, redirect, session, jsonify
from olympiads import OLYMPIADS_DB as _RAW_DB, OLYMPIADS_INFO
try:
    from problems import PROBLEMS_DB
except ImportError:
    PROBLEMS_DB = []
import requests, random, json, uuid, os, base64, math
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production-' + str(uuid.uuid4()))


# ============================================================
# Автоопределение формата olympiads.py и группировка
# ============================================================
# Новый формат: каждый элемент — пробник с полем "problems" (список задач)
# Старый формат: каждый элемент — одна задача (поля text, answer, solution напрямую)

if _RAW_DB and "problems" in _RAW_DB[0] and isinstance(_RAW_DB[0]["problems"], list):
    # Новый формат — используем как есть
    COMBOS = _RAW_DB
    print(f"olympiads.py: новый формат, {len(COMBOS)} пробников")
else:
    # Старый формат — группируем задачи в пробники
    from collections import OrderedDict
    groups = OrderedDict()
    for task in _RAW_DB:
        key = (task.get("olympiad", ""), task.get("year", 0), task.get("grade", 0), task.get("round", ""))
        if key not in groups:
            groups[key] = {
                "olympiad": task.get("olympiad", ""),
                "olympiad_title": task.get("olympiad_title", ""),
                "year": task.get("year", 0),
                "grade": task.get("grade", 0),
                "round": task.get("round", ""),
                "round_title": task.get("round_title", task.get("round", "")),
                "problems": [],
            }
        groups[key]["problems"].append({
            "num": len(groups[key]["problems"]) + 1,
            "text": task.get("text", ""),
            "answer": task.get("answer", ""),
            "solution": task.get("solution", ""),
        })
    COMBOS = []
    for i, combo in enumerate(groups.values(), start=1):
        combo["id"] = i
        COMBOS.append(combo)
    print(f"olympiads.py: старый формат, {len(_RAW_DB)} задач -> {len(COMBOS)} пробников")

print(f"Пробников всего: {len(COMBOS)}, с задачами: {sum(1 for c in COMBOS if c.get('problems'))}")
# ============================================================


OPENROUTER_API_KEY = "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"


UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


VARIANTS = {}

# Константа для маршрута обучения
REQUIRED_SOLVED_TASKS = 5


SUBJECTS = {
    "algebra": "Алгебра",
    "geometry": "Геометрия",
    "combinatorics": "Комбинаторика",
    "number_theory": "Теория чисел",
    "movement": "Задачи на движение",
    "knights_liars": "Рыцари и лжецы"
}


SUBTOPICS = {
    "algebra": {
        "equations": "Уравнения",
        "inequalities": "Неравенства",
        "sequences": "Последовательности",
        "functions": "Функции",
        "systems": "Системы уравнений",
    },
    "geometry": {
        "triangles": "Треугольники",
        "circles": "Окружности",
        "areas": "Площади",
        "quadrilaterals": "Четырёхугольники",
        "coordinate": "Координатная геометрия",
    },
    "combinatorics": {
        "counting": "Подсчёт и перебор",
        "pigeonhole": "Принцип Дирихле",
        "graphs": "Графы и раскраски",
        "games": "Игры и стратегии",
    },
    "number_theory": {
        "divisibility": "Делимость",
        "remainders": "Остатки",
        "primes": "Простые числа",
        "diophantine": "Диофантовы уравнения",
    },
    "knights_liars": {
        "classic": "Классические задачи",
        "conditions": "Задачи с условиями",
        "island": "Задачи на острове",
    },
    "movement": {
        "uniform": "Равномерное движение",
        "encounter": "Движение навстречу и вдогонку",
        "special": "Движение по воде и эскалаторы",
    },
}


GRADES = [5, 6, 7, 8, 9, 10, 11]


LEVELS = [
    (1, "Уровень 1"), (2, "Уровень 2"), (3, "Уровень 3"), (4, "Уровень 4"), (5, "Уровень 5"),
    (6, "Уровень 6"), (7, "Уровень 7"), (8, "Уровень 8"), (9, "Уровень 9"), (10, "Уровень 10")
]


ROUNDS = {
    "school": "Школьный",
    "municipal": "Муниципальный",
    "regional": "Региональный",
    "final": "Заключительный"
}


def get_olympiad_by_slug(slug):
    return next((o for o in OLYMPIADS_INFO if o.get("slug") == slug), None)

def generate_variant(olympiad_slug, grade, round_key):
    
    print(f"DEBUG generate: slug={olympiad_slug!r}, grade={grade!r}, round={round_key!r}")

    # Фильтруем варианты
    variants = [
        v for v in _RAW_DB
        if v.get("olympiad") == olympiad_slug
        and v.get("grade") == grade
        and (not round_key or v.get("round") == round_key)
    ]
    if not variants:
        variants = [
            v for v in _RAW_DB
            if v.get("olympiad") == olympiad_slug
            and v.get("grade") == grade
        ]
    if not variants:
        return []

    # Собираем все задачи из подходящих вариантов
    source = []
    for v in variants:
        for p in v.get("problems", []):
            source.append({**p, "olympiad": v["olympiad"], "grade": v["grade"]})

    if not source:
        return []

    selected = random.sample(source, min(5, len(source)))
    modified = []



    for p in selected:
        prompt = f"""Вот олимпиадная задача по математике:
{p['text']}


Немного измени эту задачу: поменяй числа, названия объектов или условия, но сохрани тот же математический смысл и сложность. Ответь ТОЛЬКО валидным JSON без markdown:
{{"text": "новый текст задачи", "answer": "ответ", "solution": "подробное решение"}}"""


        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}"},
                json={
                    "model": "google/gemini-2.0-flash-001",
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            )
            content = response.json()["choices"][0]["message"]["content"]
            content = content.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            data = json.loads(content)
            modified.append({
                "id": p["id"],
                "subject": p.get("subject"),
                "grade": grade,
                "difficulty": p.get("difficulty"),
                "title": p.get("title", "Задача"),
                "text": data["text"],
                "answer": data["answer"],
                "solution": data["solution"],
                "original_id": p["id"]
            })
        except Exception:
            modified.append(p)


    return modified



@app.route("/")
def index():
    solved_count = len(session.get('solved_problems', []))
    return render_template("index.html",
        subjects=SUBJECTS,
        solved_count=solved_count,
        required=REQUIRED_SOLVED_TASKS
    )



@app.route("/section/<subject_key>")
def section(subject_key):
    if subject_key not in SUBJECTS:
        abort(404)
    subject_title = SUBJECTS[subject_key]
    subtopics = SUBTOPICS.get(subject_key, {})

    # Считаем количество задач для каждой подтемы
    subtopic_counts = {}
    for p in PROBLEMS_DB:
        if p.get("subject") == subject_key:
            sub = p.get("subtopic", "")
            subtopic_counts[sub] = subtopic_counts.get(sub, 0) + 1

    total = sum(subtopic_counts.values())

    return render_template('section.html',
        subject_key=subject_key,
        subject_title=subject_title,
        subtopics=subtopics,
        subtopic_counts=subtopic_counts,
        total=total
    )



@app.route("/section/<subject_key>/<subtopic_key>")
def section_subtopic(subject_key, subtopic_key):
    """Выбор класса и уровня для подтемы."""
    if subject_key not in SUBJECTS:
        abort(404)
    subtopics = SUBTOPICS.get(subject_key, {})
    if subtopic_key not in subtopics:
        abort(404)
    subject_title = SUBJECTS[subject_key]
    subtopic_title = subtopics[subtopic_key]

    # Подсчет задач по классам
    grade_counts = {}
    level_counts = {}
    
    for g in GRADES:
        cnt = sum(1 for p in PROBLEMS_DB if p.get("subject")==subject_key and p.get("subtopic")==subtopic_key and p.get("grade")==g)
        grade_counts[g] = cnt
        
        level_counts[g] = {}
        for lev in range(1, 11):
            lev_cnt = sum(1 for p in PROBLEMS_DB if p.get("subject")==subject_key and p.get("subtopic")==subtopic_key and p.get("grade")==g and p.get("difficulty")==lev)
            level_counts[g][lev] = lev_cnt

    return render_template('subtopic.html',
        subject_key=subject_key,
        subject_title=subject_title,
        subtopic_key=subtopic_key,
        subtopic_title=subtopic_title,
        grades=GRADES,
        grade_counts=grade_counts,
        level_counts=level_counts
    )


@app.route("/problems")
def problems_list():
    subject_key = request.args.get("subject")
    subtopic_key = request.args.get("subtopic")
    grade = request.args.get("grade", type=int)
    level = request.args.get("level", type=int)
    page = request.args.get("page", 1, type=int)
    search_query = request.args.get("q", "").strip().lower()

    filtered = []
    for p in PROBLEMS_DB:
        db_subject = str(p.get("subject", "")).lower()
        match_subject = False

        if subject_key is None:
            match_subject = True
        elif subject_key == "algebra" and db_subject in ["algebra", "алгебра"]:
            match_subject = True
        elif subject_key == "geometry" and db_subject in ["geometry", "геометрия"]:
            match_subject = True
        elif subject_key == "combinatorics" and db_subject in ["combinatorics", "комбинаторика"]:
            match_subject = True
        elif subject_key == "number_theory" and db_subject in ["number_theory", "теория чисел", "теория_чисел"]:
            match_subject = True
        elif subject_key == "knights_liars" and db_subject in ["knights_liars", "рыцари и лжецы"]:
            match_subject = True
        elif subject_key == "movement" and db_subject in ["movement", "задачи на движение"]:
            match_subject = True
        elif db_subject == subject_key:
            match_subject = True

        match_subtopic = (subtopic_key is None) or (p.get("subtopic") == subtopic_key)
        match_grade = (grade is None) or (p.get("grade") == grade)
        match_level = (level is None) or (p.get("difficulty") == level)
        
        # Поиск по тексту задачи
        match_search = True
        if search_query:
            problem_text = str(p.get("text", "")).lower()
            match_search = search_query in problem_text

        if match_subject and match_subtopic and match_grade and match_level and match_search:
            filtered.append(p)

    subject_title = SUBJECTS.get(subject_key, "Задачи")
    subtopic_title = ""
    if subtopic_key and subject_key in SUBTOPICS:
        subtopic_title = SUBTOPICS[subject_key].get(subtopic_key, "")

    title_parts = [subject_title]
    if subtopic_title:
        title_parts.append(subtopic_title)
    if grade:
        title_parts.append(f"{grade} класс")
    if level:
        title_parts.append(f"Уровень {level}")
    page_title = " · ".join(title_parts)

    back_url = f"/section/{subject_key}/{subtopic_key}" if subtopic_key else f"/section/{subject_key}"

    # Пагинация
    PER_PAGE = 20
    total_count = len(filtered)
    total_pages = math.ceil(total_count / PER_PAGE) if total_count > 0 else 1
    
    # Ограничиваем номер страницы
    page = max(1, min(page, total_pages))
    
    # Срез для текущей страницы
    start_idx = (page - 1) * PER_PAGE
    end_idx = start_idx + PER_PAGE
    paginated_problems = filtered[start_idx:end_idx]

    solved_problems = session.get('solved_problems', [])
    
    return render_template('problems.html',
        subject_title=subject_title,
        subtopic_title=subtopic_title,
        problems=paginated_problems,
        back_url=back_url,
        page_title=page_title,
        solved_problems=solved_problems,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        search_query=search_query
    )



@app.route("/problems/<int:problem_id>")
@app.route("/problem/<int:problem_id>")
def problem_detail(problem_id):
    problem = next((p for p in PROBLEMS_DB if p.get("id") == problem_id), None)
    is_olympiad = False

    if not problem:
        problem = next((p for p in _RAW_DB if p.get("id") == problem_id), None)
        is_olympiad = True

    if not problem:
        abort(404)

    subject_title = SUBJECTS.get(problem.get("subject", ""), "Задачи")
    subtopic_title = problem.get("subtopic_title", "")

    solved_problems = session.get('solved_problems', [])
    is_solved = problem_id in solved_problems
    
    return render_template('problem_detail.html',
        problem=problem,
        subject_title=subject_title,
        subtopic_title=subtopic_title,
        is_olympiad=is_olympiad,
        is_solved=is_solved
    )



@app.route("/api/check_answer", methods=["POST"])
def check_answer():
    """API для проверки ответа пользователя."""
    data = request.get_json()
    problem_id = data.get("problem_id")
    user_answer = data.get("user_answer", "").strip().lower()
    
    if not problem_id:
        return jsonify({"error": "problem_id required"}), 400
    
    # Ищем задачу в обеих базах
    problem = next((p for p in PROBLEMS_DB if p.get("id") == problem_id), None)
    if not problem:
        problem = next((p for p in _RAW_DB if p.get("id") == problem_id), None)
    
    if not problem:
        return jsonify({"error": "Problem not found"}), 404
    
    # Получаем правильный ответ и нормализуем его
    correct_answer = str(problem.get("answer", "")).strip().lower()
    solution = problem.get("solution", "Решение отсутствует")
    
    # Проверяем ответ
    is_correct = (user_answer == correct_answer)
    
    # Если ответ верный, сохраняем в сессию
    if is_correct:
        solved_problems = session.get('solved_problems', [])
        if problem_id not in solved_problems:
            solved_problems.append(problem_id)
            session['solved_problems'] = solved_problems
            session.modified = True
    
    return jsonify({
        "correct": is_correct,
        "solution": solution,
        "correct_answer": problem.get("answer", "")
    })


@app.route("/practice")
def practice():
    # Проверка доступа
    solved_count = len(session.get('solved_problems', []))
    if solved_count < REQUIRED_SOLVED_TASKS:
        return render_template('locked.html',
            solved=solved_count,
            required=REQUIRED_SOLVED_TASKS,
            section_name="Написать олимпиаду"
        )
    
    return render_template("practice.html", olympiads=OLYMPIADS_INFO, grades=GRADES, rounds=ROUNDS)




def generate_practice():
    slug = request.form.get("olympiad")
    grade = request.form.get("grade", type=int)
    round_key = request.form.get("round")


    print(f"DEBUG: slug={slug}, grade={grade}, round={round_key}")


    if not slug or not grade:
        print(f"DEBUG: slug={slug}, grade={grade}, round={round_key}")

        abort(400)


    problems = generate_variant(slug, grade, round_key)
    print(f"DEBUG: problems count = {len(problems)}")


    if not problems:
        print("DEBUG: abort 404 - нет задач")
        abort(404)


    variant_id = str(uuid.uuid4())[:8]
    VARIANTS[variant_id] = {
        "olympiad": slug,
        "olympiad_title": get_olympiad_by_slug(slug).get("title", slug) if get_olympiad_by_slug(slug) else slug,
        "grade": grade,
        "round": round_key,
        "round_title": ROUNDS.get(round_key, round_key),
        "problems": problems
    }
    print(f"DEBUG: variant_id={variant_id}, redirecting...")
    return redirect(f"/practice/{variant_id}")


@app.route("/practice/generate", methods=["POST"])
def generate_practice():
    slug = request.form.get("olympiad")
    grade = request.form.get("grade", type=int)
    round_key = request.form.get("round")

    print(f"DEBUG: slug={slug}, grade={grade}, round={round_key}")

    if not slug or not grade:
        abort(400)

    problems = generate_variant(slug, grade, round_key)
    print(f"DEBUG: problems={len(problems)}")

    if not problems:
        print("DEBUG: abort 404 - задач нет")
        abort(404)

    variant_id = str(uuid.uuid4())[:8]
    VARIANTS[variant_id] = {
        "olympiad": slug,
        "olympiad_title": get_olympiad_by_slug(slug).get("title", slug) if get_olympiad_by_slug(slug) else slug,
        "grade": grade,
        "round": round_key,
        "round_title": ROUNDS.get(round_key, round_key),
        "problems": problems
    }
    print(f"DEBUG: variant_id={variant_id}")
    return redirect(f"/practice/{variant_id}")



@app.route("/practice/<variant_id>")
def practice_variant(variant_id):
    variant = VARIANTS.get(variant_id)
    if not variant:
        abort(404)
    return render_template("practice_variant.html", variant=variant, variant_id=variant_id)



@app.route("/practice/<variant_id>/submit", methods=["POST"])
def submit_solution(variant_id):
    """Проверка ответов тренировочного варианта."""
    variant = VARIANTS.get(variant_id)
    if not variant:
        abort(404)
    
    # Собираем результаты проверки
    results = []
    correct_count = 0
    total_count = len(variant["problems"])
    
    for p in variant["problems"]:
        problem_id = p["id"]
        user_answer = request.form.get(f"ans_{problem_id}", "").strip().lower()
        correct_answer = str(p.get("answer", "")).strip().lower()
        
        is_correct = (user_answer == correct_answer)
        if is_correct:
            correct_count += 1
        
        results.append({
            "problem": p,
            "user_answer": request.form.get(f"ans_{problem_id}", "").strip(),
            "correct_answer": p.get("answer", ""),
            "is_correct": is_correct
        })
    
    # Вычисляем процент успеха
    success_rate = round((correct_count / total_count * 100)) if total_count > 0 else 0
    
    return render_template("practice_result.html",
        variant=variant,
        results=results,
        correct_count=correct_count,
        total_count=total_count,
        success_rate=success_rate
    )


# ============================================================
# ОЛИМПИАДЫ — пробники (каскадный выбор)
# ============================================================

@app.route("/olympiads")
def olympiads():
    # Проверка доступа
    solved_count = len(session.get('solved_problems', []))
    if solved_count < REQUIRED_SOLVED_TASKS:
        return render_template('locked.html',
            solved=solved_count,
            required=REQUIRED_SOLVED_TASKS,
            section_name="Олимпиады"
        )
    
    # Структура: {slug: {year: {round_key: [round_title, [grade1, grade2, ...]]}}}
    # Порядок: Олимпиада -> Год -> Этап -> Класс
    olympiad_data = {}
    for combo in COMBOS:
        slug = combo["olympiad"]
        year = str(combo["year"])
        rnd = combo["round"]
        rnd_title = combo.get("round_title", rnd)
        grade = int(combo["grade"])
        if slug not in olympiad_data:
            olympiad_data[slug] = {}
        if year not in olympiad_data[slug]:
            olympiad_data[slug][year] = {}
        if rnd not in olympiad_data[slug][year]:
            olympiad_data[slug][year][rnd] = [rnd_title, []]
        if grade not in olympiad_data[slug][year][rnd][1]:
            olympiad_data[slug][year][rnd][1].append(grade)
    # Сортируем классы
    for slug in olympiad_data:
        for year in olympiad_data[slug]:
            for rnd in olympiad_data[slug][year]:
                olympiad_data[slug][year][rnd][1].sort()

    return render_template(
        "olympiads.html",
        olympiads=OLYMPIADS_INFO,
        olympiad_data=olympiad_data,
        grades=GRADES
    )


@app.route("/olympiads/open", methods=["POST"])
def olympiad_open():
    # Проверка доступа
    solved_count = len(session.get('solved_problems', []))
    if solved_count < REQUIRED_SOLVED_TASKS:
        return render_template('locked.html',
            solved=solved_count,
            required=REQUIRED_SOLVED_TASKS,
            section_name="Олимпиады"
        )
    
    slug = request.form.get("olympiad")
    year = request.form.get("year")
    grade = request.form.get("grade")
    rnd = request.form.get("round")

    print(f"DEBUG olympiad_open: slug={slug!r}, year={year!r}, grade={grade!r}, rnd={rnd!r}")

    olympiad = get_olympiad_by_slug(slug)
    if not olympiad:
        print("DEBUG: олимпиада не найдена по slug")
        abort(404)

    if not year or not grade:
        print("DEBUG: year или grade пустые")
        abort(404)

    # Ищем пробник (combo)
    combo = None
    for c in COMBOS:
        if (c["olympiad"] == slug
            and str(c["year"]) == str(year)
            and str(c["grade"]) == str(grade)
            and (not rnd or c["round"] == rnd)):
            combo = c
            break

    if combo:
        print(f"НАЙДЕН combo id={combo['id']}, round={combo['round']}")
        print(f"  задач: {len(combo.get('problems', []))}")
    else:
        print(f"НЕ НАЙДЕН combo для {slug}/{year}/{grade}/{rnd}")

    if not combo:
        abort(404)

    return render_template('olympiad_detail.html',
        olympiad=olympiad,
        combo=combo,
        problems=combo.get('problems', [])
    )


@app.route("/olympiads/solution/<int:combo_id>")
def olympiad_solution(combo_id):
    """Показ решений пробника."""
    combo = next((c for c in COMBOS if c["id"] == combo_id), None)
    if not combo:
        abort(404)

    olympiad = get_olympiad_by_slug(combo["olympiad"])

    return render_template('olympiad_solutions.html',
        olympiad=olympiad,
        combo=combo
    )


if __name__ == "__main__":
    app.run(debug=True)

