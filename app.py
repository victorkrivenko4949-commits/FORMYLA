from flask import Flask, render_template, request, abort, redirect, session, jsonify, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from olympiads import OLYMPIADS_DB as _RAW_DB, OLYMPIADS_INFO
try:
    from problems import PROBLEMS_DB
except ImportError:
    PROBLEMS_DB = []
import requests, random, json, uuid, os, base64, math
from werkzeug.utils import secure_filename

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# AI Integration
try:
    from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError
    DEEPSEEK_AVAILABLE = True
except ImportError:
    DEEPSEEK_AVAILABLE = False
    print("⚠️  DeepSeek client not available. AI recommendations disabled.")


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production-' + str(uuid.uuid4()))

# DEBUG: Проверка переменных окружения
print("="*60)
print("DEBUG: Доступные переменные окружения:")
env_keys = list(os.environ.keys())
print(f"Всего переменных: {len(env_keys)}")
print(f"SECRET_KEY = {'ЕСТЬ' if os.environ.get('SECRET_KEY') else 'НЕТ (используется автогенерация)'}")
print(f"MAIL_USERNAME = {os.environ.get('MAIL_USERNAME')}")
print(f"MAIL_PASSWORD = {'ЕСТЬ' if os.environ.get('MAIL_PASSWORD') else 'НЕТ'}")
print(f"DEEPSEEK_API_KEY = {'ЕСТЬ' if os.environ.get('DEEPSEEK_API_KEY') else 'НЕТ'}")
print("="*60)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///formyla.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Flask-Login configuration (долгоживущие cookie)
from datetime import timedelta
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
domain_url = os.environ.get('DOMAIN_URL', 'http://localhost:5000')
app.config['REMEMBER_COOKIE_SECURE'] = domain_url.startswith('https')
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = domain_url.startswith('https')
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Flask-Mail configuration (Yandex SMTP)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.yandex.ru')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '465'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'False') == 'True'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

# Yandex OAuth configuration
app.config['YANDEX_CLIENT_ID'] = os.environ.get('YANDEX_CLIENT_ID')
app.config['YANDEX_CLIENT_SECRET'] = os.environ.get('YANDEX_CLIENT_SECRET')
app.config['DOMAIN_URL'] = os.environ.get('DOMAIN_URL', 'http://localhost:5000')

# Initialize database, login manager and mail
from models import db, User, init_db
init_db(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице'

mail = Mail(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


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
        "equations": "Уравнения и системы",
        "inequalities": "Неравенства и оценки (8-11)",
        "text_problems": "Текстовые задачи",
        "other_algebra": "Другое (Алгебра)"
    },
    "geometry": {
        "basics": "Углы, отрезки и многоугольники",
        "triangles": "Треугольники (7-11)",
        "circles": "Окружности (8-11)",
        "other_geometry": "Другое (Геометрия)"
    },
    "combinatorics": {
        "dirichlet_and_graphs": "Графы и Принцип Дирихле",
        "games": "Игры и стратегии",
        "other_combinatorics": "Другое (Комбинаторика)"
    },
    "number_theory": {
        "divisibility": "Делимость и остатки",
        "primes_and_equations": "Простые числа и диофантовы уравнения (7-11)",
        "other_number_theory": "Другое (Теория чисел)"
    },
    "movement": {
        "movement_all": "Все задачи на движение"
    },
    "knights_liars": {
        "logic_all": "Рыцари, лжецы и логика"
    }
}


GRADES = [5, 6, 7, 8, 9, 10, 11]


LEVELS = [
    (1, "Уровень 1"), (2, "Уровень 2"), (3, "Уровень 3"), (4, "Уровень 4"), (5, "Уровень 5"),
    (6, "Уровень 6"), (7, "Уровень 7")
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
        solved_count=solved_count
    )



@app.route("/section/<subject_key>")
def section(subject_key):
    if subject_key not in SUBJECTS:
        abort(404)
    subject_title = SUBJECTS[subject_key]
    subtopics = SUBTOPICS.get(subject_key, {})

    # Считаем количество задач для каждой подтемы (максимум 5 на ячейку)
    subtopic_counts = {}
    for sub_key in subtopics.keys():
        count = 0
        for grade in GRADES:
            for level in range(1, 8):  # 7 уровней
                tasks = [p for p in PROBLEMS_DB
                        if p.get("subject") == subject_key
                        and p.get("subtopic") == sub_key
                        and p.get("grade") == grade
                        and p.get("difficulty") == level]
                count += min(len(tasks), 5)  # Максимум 5 на ячейку
        subtopic_counts[sub_key] = count

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

    # Подсчет задач по классам (максимум 5 задач на уровень)
    grade_counts = {}
    level_counts = {}
    
    for g in GRADES:
        # Подсчитываем задачи по уровням с ограничением 5 на уровень
        level_counts[g] = {}
        total_for_grade = 0
        
        for lev in range(1, 8):  # 7 уровней!
            # Считаем задачи для этого уровня
            problems_for_level = [p for p in PROBLEMS_DB if p.get("subject")==subject_key and p.get("subtopic")==subtopic_key and p.get("grade")==g and p.get("difficulty")==lev]
            # Ограничиваем до 5 задач
            lev_cnt = min(len(problems_for_level), 5)
            level_counts[g][lev] = lev_cnt
            total_for_grade += lev_cnt
        
        grade_counts[g] = total_for_grade

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

    # ВСЕГДА показываем ТОЛЬКО 5 задач (БЕЗ пагинации)
    MAX_PROBLEMS = 5
    total_count = len(filtered)
    
    # Берём только первые 5 задач
    limited_problems = filtered[:MAX_PROBLEMS]

    solved_problems = session.get('solved_problems', [])
    
    return render_template('problems.html',
        subject_title=subject_title,
        subtopic_title=subtopic_title,
        problems=limited_problems,
        back_url=back_url,
        page_title=page_title,
        solved_problems=solved_problems,
        page=1,
        total_pages=1,
        total_count=min(total_count, MAX_PROBLEMS),
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


def send_auth_email(recipient_email, code):
    """Отправка кода через smtplib (Yandex SMTP)."""
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email import charset
    
    # Устанавливаем UTF-8 кодировку
    charset.add_charset('utf-8', charset.QP, charset.QP, 'utf-8')
    
    sender = os.getenv('MAIL_USERNAME')
    password = os.getenv('MAIL_PASSWORD')
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'Код для входа в FORMYLA: {code}'
    msg['From'] = f'FORMYLA <{sender}>'
    msg['To'] = recipient_email
    msg.set_charset('utf-8')
    
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 400px; margin: 0 auto; padding: 20px; text-align: center;">
        <h2 style="color: #333;">FORMYLA</h2>
        <p>Ваш код для входа:</p>
        <div style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #4F46E5; margin: 20px 0; padding: 15px; background: #F3F4F6; border-radius: 8px;">
            {code}
        </div>
        <p style="color: #888; font-size: 12px;">Код действителен 10 минут.</p>
    </div>
    """
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL('smtp.yandex.ru', 465, context=context) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient_email, msg.as_string())


@app.route("/login", methods=["GET", "POST"])
def login():
    """Passwordless вход - шаг 1: ввод email."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == "POST":
        import sys
        print(">>> LOGIN POST ВЫЗВАН", flush=True)
        sys.stdout.flush()
        app.logger.warning("LOGIN POST ВЫЗВАН")
        
        email = request.form.get('email', '').strip().lower()
        
        if not email:
            flash('Email обязателен', 'error')
            return render_template('login.html')
        
        # Проверяем или создаем пользователя
        user = User.query.filter_by(email=email).first()
        
        if not user:
            # Создаем нового пользователя
            user = User(email=email)
            db.session.add(user)
        
        # Генерируем код
        code = user.generate_auth_code()
        db.session.commit()
        
        print(f">>> КОД СГЕНЕРИРОВАН: {code}", flush=True)
        app.logger.warning(f"КОД СГЕНЕРИРОВАН: {code} для {email}")
        
        # Отправляем код на email
        # Проверяем настройки
        mail_configured = app.config.get('MAIL_USERNAME') and app.config.get('MAIL_PASSWORD')
        
        print(f"\n🔍 DEBUG: MAIL_USERNAME = {app.config.get('MAIL_USERNAME')}", flush=True)
        mail_pass = app.config.get('MAIL_PASSWORD') or ''
        print(f"🔍 DEBUG: MAIL_PASSWORD = {'*' * len(mail_pass)} ({len(mail_pass)} символов)", flush=True)
        print(f"🔍 DEBUG: Mail configured = {mail_configured}\n", flush=True)
        
        if mail_configured:
            try:
                send_auth_email(email, code)
                
                # Дублируем в консоль для отладки
                print("\n" + "="*60, flush=True)
                print("✅ EMAIL УСПЕШНО ОТПРАВЛЕН", flush=True)
                print("="*60, flush=True)
                print(f"   Кому: {email}", flush=True)
                print(f"   Код: {code}", flush=True)
                print("="*60 + "\n", flush=True)
                app.logger.warning(f"EMAIL ОТПРАВЛЕН: {email}, код: {code}")
                
                flash(f'Код отправлен на {email}. Проверьте почту!', 'success')
                
            except Exception as e:
                print(f"\n❌ ОШИБКА ОТПРАВКИ EMAIL: {e}\n", flush=True)
                app.logger.error(f"ОШИБКА EMAIL: {e}")
                # Fallback - выводим код в консоль
                print("\n" + "="*60, flush=True)
                print("⚠️  FALLBACK - КОД В КОНСОЛИ", flush=True)
                print("="*60, flush=True)
                print(f"   Email: {email}", flush=True)
                print(f"   КОД: {code}", flush=True)
                print(f"   Действителен: 10 минут", flush=True)
                print("="*60 + "\n", flush=True)
                
                flash(f'Ошибка отправки email. Попробуйте еще раз.', 'error')
        else:
            # Email не настроен
            print("\n" + "="*60, flush=True)
            print("⚠️  EMAIL НЕ НАСТРОЕН - КОД В КОНСОЛИ", flush=True)
            print("="*60, flush=True)
            print(f"   Email: {email}", flush=True)
            print(f"   КОД: {code}", flush=True)
            print(f"   Действителен: 10 минут", flush=True)
            print("="*60 + "\n", flush=True)
            app.logger.warning(f"EMAIL НЕ НАСТРОЕН - КОД: {code}")
            
            flash(f'Код отправлен на {email}', 'success')
        
        # Сохраняем email в сессию для следующего шага
        session['verify_email'] = email
        return redirect(url_for('verify_code'))
    
    return render_template('login.html')


@app.route("/verify-code", methods=["GET", "POST"])
def verify_code():
    """Passwordless вход - шаг 2: проверка кода."""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    email = session.get('verify_email')
    if not email:
        flash('Сначала введите email', 'error')
        return redirect(url_for('login'))
    
    if request.method == "POST":
        code = request.form.get('code', '').strip()
        
        if not code:
            flash('Введите код', 'error')
            return render_template('verify_code.html', email=email)
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            flash('Пользователь не найден', 'error')
            return redirect(url_for('login'))
        
        if user.verify_auth_code(code):
            # Успешная авторизация
            user.clear_auth_code()
            from datetime import datetime
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Вход с долгоживущей сессией (30 дней)
            login_user(user, remember=True, duration=None)
            session.pop('verify_email', None)
            
            flash('Добро пожаловать!', 'success')
            
            # Редирект на онбординг если не пройден
            if not user.onboarding_completed:
                return redirect(url_for('onboarding'))
            
            # Иначе на главную
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        
        flash('Неверный или просроченный код', 'error')
        return render_template('verify_code.html', email=email)
    
    return render_template('verify_code.html', email=email)


@app.route("/logout")
@login_required
def logout():
    """Выход пользователя."""
    logout_user()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('index'))


@app.route("/yandex_login")
def yandex_login_start():
    """Начало OAuth через Яндекс (редирект)."""
    client_id = app.config.get('YANDEX_CLIENT_ID')
    domain = os.environ.get('DOMAIN_URL', 'http://localhost:5000')
    redirect_uri = f"{domain}/yandex_receiver"
    
    if not client_id:
        flash('Яндекс OAuth не настроен', 'error')
        return redirect(url_for('login'))
    
    # Редирект на Яндекс OAuth
    auth_url = f"https://oauth.yandex.ru/authorize?response_type=token&client_id={client_id}&redirect_uri={redirect_uri}"
    return redirect(auth_url)


@app.route("/yandex_receiver")
def yandex_receiver():
    """Техническая страница для Яндекс OAuth виджета."""
    html = f'''<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8" />
    <title>Ожидание...</title>
    <script src="https://yastatic.net/s3/passport-sdk/autofill/v1/sdk-suggest-token-with-polyfills-latest.js"></script>
</head>
<body>
    <script>
        window.YaSendSuggestToken("{app.config['DOMAIN_URL']}");
    </script>
</body>
</html>'''
    return html


@app.route("/auth/yandex/login", methods=["POST"])
def yandex_login():
    """Обработка OAuth токена от Яндекса."""
    data = request.get_json()
    access_token = data.get('access_token')
    
    if not access_token:
        return jsonify({'error': 'Токен не предоставлен'}), 400
    
    try:
        # Получаем данные от Яндекса
        response = requests.get(
            'https://login.yandex.ru/info?format=json',
            headers={'Authorization': f'OAuth {access_token}'}
        )
        
        if response.status_code != 200:
            return jsonify({'error': 'Ошибка Яндекса'}), 400
        
        yandex_data = response.json()
        provider_user_id = str(yandex_data.get('id'))
        email = yandex_data.get('default_email')
        name = yandex_data.get('display_name') or yandex_data.get('real_name', '')
        avatar_id = yandex_data.get('default_avatar_id', '')
        avatar_url = f"https://avatars.yandex.net/get-yapic/{avatar_id}/islands-200" if avatar_id else None
        
        from models import OAuthAccount
        
        # Ищем OAuth аккаунт
        oauth = OAuthAccount.query.filter_by(provider='yandex', provider_user_id=provider_user_id).first()
        
        if oauth:
            user = oauth.user
        else:
            # Ищем по email
            user = User.query.filter_by(email=email).first()
            
            if not user:
                # Создаем нового
                user = User(email=email, name=name, avatar_url=avatar_url)
                db.session.add(user)
                db.session.flush()
            
            # Создаем OAuth связь
            oauth = OAuthAccount(user_id=user.id, provider='yandex', provider_user_id=provider_user_id)
            db.session.add(oauth)
        
        # Обновляем данные
        if name and not user.name:
            user.name = name
        if avatar_url and not user.avatar_url:
            user.avatar_url = avatar_url
        
        from datetime import datetime
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Авторизуем
        login_user(user, remember=True)
        
        # Редирект
        redirect_url = url_for('onboarding') if not user.onboarding_completed else url_for('index')
        
        return jsonify({'success': True, 'redirect_url': redirect_url})
        
    except Exception as e:
        print(f"Ошибка OAuth: {e}")
        return jsonify({'error': str(e)}), 500


@app.route("/onboarding")
@login_required
def onboarding():
    """Страница AI-онбординга для новых пользователей."""
    # Если онбординг уже пройден, редирект на главную
    if current_user.onboarding_completed:
        flash('Вы уже прошли онбординг!', 'info')
        return redirect(url_for('index'))
    
    return render_template('onboarding.html')


@app.route("/api/onboarding", methods=["POST"])
@login_required
def api_onboarding():
    """API для анализа математического опыта пользователя через AI."""
    if not DEEPSEEK_AVAILABLE:
        return jsonify({
            'error': 'AI сервис недоступен',
            'level': 'intermediate',
            'report': 'Спасибо за ваш рассказ! Начнем с задач среднего уровня.',
            'recommended_topics': ['algebra', 'geometry']
        }), 503
    
    data = request.get_json()
    user_text = data.get('text', '').strip()
    
    if not user_text:
        return jsonify({'error': 'Текст не может быть пустым'}), 400
    
    if len(user_text) < 20:
        return jsonify({'error': 'Расскажите подробнее (минимум 20 символов)'}), 400
    
    try:
        # Инициализируем DeepSeek клиент
        client = DeepSeekClient()
        
        # Анализируем опыт пользователя
        result = client.analyze_user_background(user_text)
        
        # Сохраняем в БД
        current_user.complete_onboarding(
            level=result['level'],
            report=result['report'],
            topics=result['recommended_topics']
        )
        db.session.commit()
        
        return jsonify(result), 200
        
    except Exception as e:
        print(f"Ошибка анализа: {e}")
        return jsonify({
            'error': 'Ошибка анализа',
            'level': 'intermediate',
            'report': 'Спасибо за ваш рассказ! Мы подберем для вас подходящие задачи.',
            'recommended_topics': ['algebra', 'geometry']
        }), 500


@app.route("/api/tutor/history")
@login_required
def tutor_history():
    """Получить историю чата с тьютором."""
    from models import ChatMessage
    messages = ChatMessage.query.filter_by(user_id=current_user.id).order_by(ChatMessage.timestamp).all()
    return jsonify([msg.to_dict() for msg in messages])


@app.route("/api/tutor/send", methods=["POST"])
@login_required
def tutor_send():
    """Отправить сообщение тьютору."""
    if not DEEPSEEK_AVAILABLE:
        return jsonify({'error': 'AI недоступен'}), 503
    
    data = request.get_json()
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'error': 'Сообщение пустое'}), 400
    
    try:
        from models import ChatMessage
        
        # Сохраняем сообщение пользователя
        user_msg = ChatMessage(user_id=current_user.id, role='user', content=message)
        db.session.add(user_msg)
        db.session.commit()
        
        # Получаем историю
        history = ChatMessage.query.filter_by(user_id=current_user.id).order_by(ChatMessage.timestamp).all()
        history_list = [{'role': msg.role, 'content': msg.content} for msg in history[-10:]]
        
        # Получаем ответ от AI
        client = DeepSeekClient()
        response = client.chat_with_tutor(current_user, message, history_list)
        
        # Сохраняем ответ AI
        ai_msg = ChatMessage(user_id=current_user.id, role='assistant', content=response)
        db.session.add(ai_msg)
        db.session.commit()
        
        return jsonify({
            'user_message': user_msg.to_dict(),
            'ai_response': ai_msg.to_dict()
        })
        
    except Exception as e:
        print(f"Ошибка чата: {e}", flush=True)
        app.logger.error(f"AI Tutor error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Ошибка AI: {str(e)}'}), 500


@app.route("/profile")
@login_required
def profile():
    """Личный кабинет пользователя."""
    return render_template('profile.html', user=current_user)


# ============================================================
# MOCK EXAMS (Пробники)
# ============================================================

@app.route("/api/exam/generate", methods=["POST"])
@login_required
def generate_exam():
    """Генерация нового пробника."""
    from models import MockExam, MockExamTask
    import random
    
    data = request.get_json() or {}
    grade = data.get('grade', 9)  # По умолчанию 9 класс
    
    # Выбираем 5 случайных задач из разных тем для указанного класса
    subjects = ['algebra', 'geometry', 'combinatorics', 'number_theory', 'movement', 'knights_liars']
    selected_problems = []
    
    for subject in random.sample(subjects, min(5, len(subjects))):
        problems = [p for p in PROBLEMS_DB if p.get('subject') == subject and p.get('grade') == grade]
        if problems:
            selected_problems.append(random.choice(problems))
    
    # Дополняем до 5 если нужно
    while len(selected_problems) < 5:
        selected_problems.append(random.choice(PROBLEMS_DB))
    
    # Создаем пробник
    exam = MockExam(user_id=current_user.id)
    db.session.add(exam)
    db.session.flush()
    
    # Добавляем задачи
    for prob in selected_problems:
        task = MockExamTask(exam_id=exam.id, problem_id=prob['id'])
        db.session.add(task)
    
    db.session.commit()
    
    return jsonify({'exam_id': exam.id})


@app.route("/exam/<int:exam_id>")
@login_required
def exam_page(exam_id):
    """Страница прохождения пробника."""
    from models import MockExam
    exam = MockExam.query.get_or_404(exam_id)
    
    if exam.user_id != current_user.id:
        abort(403)
    
    # Получаем задачи
    tasks_data = []
    for task in exam.tasks:
        problem = next((p for p in PROBLEMS_DB if p['id'] == task.problem_id), None)
        if problem:
            tasks_data.append({
                'task_id': task.id,
                'problem': problem
            })
    
    return render_template('exam.html', exam=exam, tasks=tasks_data)


@app.route("/api/exam/<int:exam_id>/submit", methods=["POST"])
@login_required
def submit_exam(exam_id):
    """Отправка пробника на проверку AI."""
    from models import MockExam, MockExamTask
    
    exam = MockExam.query.get_or_404(exam_id)
    if exam.user_id != current_user.id:
        abort(403)
    
    data = request.get_json()
    answers = data.get('answers', {})
    
    # Сохраняем ответы
    for task in exam.tasks:
        task_data = answers.get(str(task.id), {})
        task.user_answer = task_data.get('answer', '')
        task.user_solution_text = task_data.get('solution', '')
    
    exam.status = 'checking'
    db.session.commit()
    
    # Проверка через AI
    if DEEPSEEK_AVAILABLE:
        try:
            client = DeepSeekClient()
            
            # Подготовка данных
            exam_data = []
            for task in exam.tasks:
                problem = next((p for p in PROBLEMS_DB if p['id'] == task.problem_id), None)
                if problem:
                    exam_data.append({
                        'text': problem['text'],
                        'correct_answer': problem['answer'],
                        'correct_solution': problem['solution'],
                        'user_answer': task.user_answer or '',
                        'user_solution': task.user_solution_text or ''
                    })
            
            # Проверка
            result = client.grade_exam(exam_data)
            
            # Сохранение результатов
            for i, task in enumerate(exam.tasks):
                task_result = result['tasks'][i] if i < len(result['tasks']) else {}
                task.is_correct = task_result.get('is_correct', False)
                task.ai_comment = task_result.get('comment', '')
            
            exam.ai_feedback = result.get('overall_feedback', '')
            exam.score = result.get('score', 0)
            exam.status = 'graded'
            db.session.commit()
            
            # Отправляем анализ в чат с тьютором
            try:
                from models import ChatMessage
                chat_msg = f"""🎯 Пробник #{exam_id} проверен!

Ваш результат: {exam.score}%

{exam.ai_feedback}

Хотите разобрать ошибки или попробовать еще раз?"""
                
                ai_msg = ChatMessage(user_id=current_user.id, role='assistant', content=chat_msg)
                db.session.add(ai_msg)
                db.session.commit()
            except:
                pass  # Не критично если не отправилось
            
            return jsonify({'success': True, 'exam_id': exam_id})
            
        except Exception as e:
            print(f"Ошибка проверки: {e}")
            exam.status = 'in_progress'
            db.session.commit()
            return jsonify({'error': str(e)}), 500
    
    return jsonify({'error': 'AI недоступен'}), 503


@app.route("/exam/<int:exam_id>/results")
@login_required
def exam_results(exam_id):
    """Страница результатов пробника."""
    from models import MockExam
    exam = MockExam.query.get_or_404(exam_id)
    
    if exam.user_id != current_user.id:
        abort(403)
    
    # Получаем задачи с результатами
    results_data = []
    for task in exam.tasks:
        problem = next((p for p in PROBLEMS_DB if p['id'] == task.problem_id), None)
        if problem:
            results_data.append({
                'problem': problem,
                'user_answer': task.user_answer,
                'user_solution': task.user_solution_text,
                'is_correct': task.is_correct,
                'ai_comment': task.ai_comment
            })
    
    return render_template('exam_results.html', exam=exam, results=results_data)


if __name__ == "__main__":
    app.run(debug=True)

