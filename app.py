from flask import Flask, render_template, request, abort, redirect, session, jsonify, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from olympiads import OLYMPIADS_DB as _RAW_DB
try:
    from olympiads import OLYMPIADS_INFO
except ImportError:
    # Создаем OLYMPIADS_INFO из OLYMPIADS_DB
    OLYMPIADS_INFO = []
    seen = set()
    for item in _RAW_DB:
        slug = item.get('olympiad', '')
        if slug and slug not in seen:
            OLYMPIADS_INFO.append({
                'slug': slug,
                'title': item.get('olympiad_title', slug)
            })
            seen.add(slug)
try:
    from problems import PROBLEMS_DB
except ImportError:
    PROBLEMS_DB = []
try:
    from problem_images import IMAGE_MAP
except ImportError:
    IMAGE_MAP = {}

print(f"DEBUG: Загружено {len(IMAGE_MAP)} привязок картинок из problem_images.py")
try:
    from problem_images import IMAGE_MAP
except ImportError:
    IMAGE_MAP = {}

print(f"DEBUG: Загружено {len(IMAGE_MAP)} привязок картинок из problem_images.py")

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
# CRITICAL: SECRET_KEY must be consistent across restarts to maintain session integrity
# Using a fallback that's consistent for development, but MUST be set in production
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-DO-NOT-USE-IN-PRODUCTION-12345')

# Validate SECRET_KEY is set properly
if app.secret_key == 'dev-secret-key-DO-NOT-USE-IN-PRODUCTION-12345':
    print("⚠️  WARNING: Using default SECRET_KEY! Set SECRET_KEY environment variable in production!")

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
from datetime import timedelta, datetime
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
domain_url = os.environ.get('DOMAIN_URL', 'http://localhost:5000')
app.config['REMEMBER_COOKIE_SECURE'] = domain_url.startswith('https')
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = domain_url.startswith('https')
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Flask-Mail configuration (Yandex by default, fully configurable via env vars)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.yandex.ru')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '465'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'False') == 'True'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'True') == 'True'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')

# DEBUG: Проверка конфигурации Flask-Mail
print("="*60)
print("DEBUG: Flask-Mail Configuration:")
print(f"MAIL_SERVER = {app.config['MAIL_SERVER']}")
print(f"MAIL_PORT = {app.config['MAIL_PORT']}")
print(f"MAIL_USE_TLS = {app.config['MAIL_USE_TLS']}")
print(f"MAIL_USE_SSL = {app.config['MAIL_USE_SSL']}")
print(f"MAIL_USERNAME = {app.config['MAIL_USERNAME']}")
print(f"MAIL_PASSWORD = {'*' * len(app.config['MAIL_PASSWORD']) if app.config['MAIL_PASSWORD'] else 'НЕТ'} ({len(app.config['MAIL_PASSWORD']) if app.config['MAIL_PASSWORD'] else 0} символов)")
print("="*60)

# Yandex OAuth configuration
app.config['YANDEX_CLIENT_ID'] = os.environ.get('YANDEX_CLIENT_ID')
app.config['YANDEX_CLIENT_SECRET'] = os.environ.get('YANDEX_CLIENT_SECRET')
app.config['DOMAIN_URL'] = os.environ.get('DOMAIN_URL', 'http://localhost:5000')

# Initialize database, login manager and mail
from models import db, User, Friendship, Mentorship, init_db
init_db(app)

# AUTO-MIGRATION: Add agent_type column if it doesn't exist
# This runs on every startup to ensure database schema is up to date
try:
    with app.app_context():
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        
        # Check if chat_messages table exists
        if 'chat_messages' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('chat_messages')]
            
            # Add agent_type column if it doesn't exist
            if 'agent_type' not in columns:
                print("[AUTO-MIGRATION] Adding 'agent_type' column to chat_messages...")
                db.engine.execute(text("ALTER TABLE chat_messages ADD COLUMN agent_type VARCHAR(50) DEFAULT 'general' NOT NULL"))
                db.engine.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_messages_agent_type ON chat_messages (agent_type)"))
                print("[AUTO-MIGRATION] ✓ Column 'agent_type' added successfully!")
            else:
                print("[AUTO-MIGRATION] ✓ Column 'agent_type' already exists")
except Exception as e:
    print(f"[AUTO-MIGRATION] Warning: {e}")
    # Continue anyway - app should still work

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

# Привязываем картинки к задачам
if IMAGE_MAP:
    for combo in COMBOS:
        combo_id = combo.get('id')
        for problem in combo.get('problems', []):
            prob_num = problem.get('num')
            img_key = f"{combo_id}_{prob_num}"
            if img_key in IMAGE_MAP:
                problem['image'] = IMAGE_MAP[img_key]

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
        "equations": "Уравнения",
        "inequalities": "Неравенства",
        "text_problems": "Текстовые задачи"
    },
    "geometry": {
        "basics": "Основы геометрии",
        "triangles": "Треугольники",
        "circles": "Окружности"
    },
    "number_theory": {
        "divisibility": "Делимость",
        "primes_and_equations": "Простые числа и диофантовы уравнения"
    },
    "combinatorics": {
        "counting": "Подсчет вариантов",
        "dirichlet_and_graphs": "Принцип Дирихле и графы",
        "games_and_invariants": "Игры и инварианты"
    },
    "movement": {
        "linear": "Прямолинейное движение",
        "circular": "Движение по окружности и циклы"
    },
    "knights_liars": {
        "basic_logic": "Базовая логика",
        "complex_logic": "Сложные логические задачи"
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

    # Выбираем 5 задач с нарастающей сложностью (имитация реальной олимпиады)
    # Группируем задачи по уровню сложности
    by_difficulty = {}
    for p in source:
        diff = p.get("difficulty", 3)  # По умолчанию средний уровень
        if diff not in by_difficulty:
            by_difficulty[diff] = []
        by_difficulty[diff].append(p)
    
    selected = []
    # Пытаемся выбрать задачи разных уровней: 1-2 легкие, 2-3 средние, 1-2 сложные
    target_distribution = [
        (1, 2, 1),  # 1 задача уровня 1-2
        (3, 4, 2),  # 2 задачи уровня 3-4
        (5, 6, 1),  # 1 задача уровня 5-6
        (7, 10, 1)  # 1 задача уровня 7+
    ]
    
    for min_diff, max_diff, count in target_distribution:
        candidates = []
        for d in range(min_diff, max_diff + 1):
            candidates.extend(by_difficulty.get(d, []))
        if candidates:
            selected.extend(random.sample(candidates, min(count, len(candidates))))
    
    # Если не набрали 5 задач, дополняем случайными
    if len(selected) < 5:
        remaining = [p for p in source if p not in selected]
        if remaining:
            selected.extend(random.sample(remaining, min(5 - len(selected), len(remaining))))
    
    # Ограничиваем до 5 задач
    selected = selected[:5]
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
            problems_for_level = [p for p in PROBLEMS_DB
                                 if p.get("subject") == subject_key
                                 and p.get("subtopic") == subtopic_key
                                 and p.get("grade") == g
                                 and p.get("difficulty") == lev]
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

        # Проверка подтемы (прямое сравнение)
        if subtopic_key is None:
            match_subtopic = True
        else:
            match_subtopic = p.get("subtopic") == subtopic_key
            
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
        # Всегда используем строку для grade (для совместимости с JSON)
        grade = str(combo["grade"])
        if slug not in olympiad_data:
            olympiad_data[slug] = {}
        if year not in olympiad_data[slug]:
            olympiad_data[slug][year] = {}
        if rnd not in olympiad_data[slug][year]:
            olympiad_data[slug][year][rnd] = [rnd_title, []]
        if grade not in olympiad_data[slug][year][rnd][1]:
            olympiad_data[slug][year][rnd][1].append(grade)
    # Сортируем классы и конвертируем ВСЕ ключи в строки для JSON
    normalized_data = {}
    for slug in olympiad_data:
        normalized_data[str(slug)] = {}
        for year in olympiad_data[slug]:
            normalized_data[str(slug)][str(year)] = {}
            for rnd in olympiad_data[slug][year]:
                # Конвертируем все grade в строки для JSON
                grades_list = olympiad_data[slug][year][rnd][1]
                normalized_data[str(slug)][str(year)][str(rnd)] = [
                    str(olympiad_data[slug][year][rnd][0]),  # round_title
                    sorted([str(g) for g in grades_list])  # grades
                ]

    # DEBUG: Логирование структуры данных
    import logging
    logging.warning("=== ДЕБАГ OLYMPIAD_DATA ===")
    logging.warning(f"Тип normalized_data: {type(normalized_data)}")
    if isinstance(normalized_data, dict):
        top_keys = list(normalized_data.keys())
        logging.warning(f"Ключи первого уровня (Олимпиады): {top_keys[:10]}")
        if top_keys:
            first_key = top_keys[0]
            logging.warning(f"Пример ключа: {first_key}, тип значения: {type(normalized_data[first_key])}")
            if isinstance(normalized_data[first_key], dict):
                years = list(normalized_data[first_key].keys())
                logging.warning(f"Ключи второго уровня для '{first_key}' (Года): {years[:5]}")
    else:
        logging.warning("ВНИМАНИЕ: normalized_data НЕ является словарем!")
    logging.warning(f"Всего олимпиад: {len(normalized_data) if isinstance(normalized_data, dict) else 0}")
    logging.warning("===========================")
    
    return render_template(
        "olympiads.html",
        olympiads=OLYMPIADS_INFO,
        olympiad_data=normalized_data,
        grades=[str(g) for g in GRADES]  # Конвертируем в строки для JSON
    )


@app.route("/olympiads/open", methods=["POST"])
def olympiad_open():
    slug = request.form.get("olympiad")
    year = request.form.get("year")
    grade = request.form.get("grade")
    rnd = request.form.get("round")

    olympiad = get_olympiad_by_slug(slug)
    if not olympiad:
        abort(404)

    if not year or not grade:
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

    if not combo:
        abort(404)

    # Привязываем рисунки к задачам при каждом запросе
    if IMAGE_MAP:
        for p in combo.get('problems', []):
            num = p.get('num')
            img = IMAGE_MAP.get((combo.get('id'), num))
            if img:
                p['image'] = f'/static/images/problems/{img}'
    
    # RUNTIME PATCH: Удаление фразы "см. рисунок" для обхода клиентского кеша
    patch_count = 0
    for p in combo.get('problems', []):
        if p.get('text'):
            before = p['text']
            p['text'] = p['text'].replace('(см. рисунок)', '').replace('см. рисунок', '')
            if before != p['text']:
                patch_count += 1
        if p.get('solution'):
            before_sol = p['solution']
            p['solution'] = p['solution'].replace('(см. рисунок)', '').replace('см. рисунок', '')
            if before_sol != p['solution']:
                patch_count += 1
    
    if patch_count > 0:
        print(f"[RUNTIME PATCH] Удалено 'см. рисунок' из {patch_count} полей в combo_id={combo.get('id')}")

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

    # Привязываем рисунки к задачам при каждом запросе
    if IMAGE_MAP:
        for p in combo.get('problems', []):
            num = p.get('num')
            img = IMAGE_MAP.get((combo.get('id'), num))
            if img:
                p['image'] = f'/static/images/problems/{img}'
    
    # RUNTIME PATCH: Удаление фразы "см. рисунок" для обхода клиентского кеша
    patch_count = 0
    for p in combo.get('problems', []):
        if p.get('text'):
            before = p['text']
            p['text'] = p['text'].replace('(см. рисунок)', '').replace('см. рисунок', '')
            if before != p['text']:
                patch_count += 1
        if p.get('solution'):
            before_sol = p['solution']
            p['solution'] = p['solution'].replace('(см. рисунок)', '').replace('см. рисунок', '')
            if before_sol != p['solution']:
                patch_count += 1
    
    if patch_count > 0:
        print(f"[RUNTIME PATCH] Удалено 'см. рисунок' из {patch_count} полей в combo_id={combo.get('id')} (solutions)")

    return render_template('olympiad_solutions.html',
        olympiad=olympiad,
        combo=combo
    )


def send_auth_email(recipient_email, code):
    """Отправка кода через Yandex SMTP на порту 587 с TLS (для Render)."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    # Используем надежный порт 587 для TLS
    smtp_server = 'smtp.yandex.ru'
    smtp_port = 587
    smtp_user = 'kr1venkovictor@yandex.ru'
    smtp_pass = os.environ.get('MAIL_PASSWORD', 'ktxfblhgcrlryncy')
    
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = recipient_email
    msg['Subject'] = 'Код подтверждения FORMYLA'
    
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
    
    try:
        # Для порта 587 используем обычный SMTP с обязательным starttls()
        print(f"[EMAIL] Connecting to {smtp_server}:{smtp_port} via TLS")
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=30)
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        print(f"[EMAIL] ✅ Successfully sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send: {e}")
        raise Exception(f"Ошибка отправки email: {str(e)}")


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
                error_message = str(e)
                print(f"\n❌ ОШИБКА ОТПРАВКИ EMAIL: {error_message}\n", flush=True)
                app.logger.error(f"ОШИБКА EMAIL: {error_message}")
                
                # Fallback - выводим код в консоль
                print("\n" + "="*60, flush=True)
                print("⚠️  FALLBACK - КОД В КОНСОЛИ", flush=True)
                print("="*60, flush=True)
                print(f"   Email: {email}", flush=True)
                print(f"   КОД: {code}", flush=True)
                print(f"   Действителен: 10 минут", flush=True)
                print("="*60 + "\n", flush=True)
                
                # Показываем понятное сообщение пользователю
                if "аутентификации" in error_message.lower() or "authentication" in error_message.lower():
                    flash(f'Ошибка настройки email-сервера. Обратитесь к администратору.', 'error')
                elif "подключиться" in error_message.lower() or "connect" in error_message.lower():
                    flash(f'Не удалось подключиться к почтовому серверу. Попробуйте позже.', 'error')
                else:
                    flash(f'Ошибка отправки email: {error_message}', 'error')
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
            
            # Редирект на главную или указанную страницу
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
        
        # Редирект на главную страницу
        redirect_url = url_for('index')
        
        return jsonify({'success': True, 'redirect_url': redirect_url})
        
    except Exception as e:
        print(f"Ошибка OAuth: {e}")
        return jsonify({'error': str(e)}), 500


# Онбординг удален - используйте AI-тьютор

@app.route("/api/tutor/history")
@login_required
def tutor_history():
    """Получить историю чата с тьютором для конкретного агента."""
    from models import ChatMessage
    agent_type = request.args.get('agent_type', 'general')
    messages = ChatMessage.query.filter_by(
        user_id=current_user.id,
        agent_type=agent_type
    ).order_by(ChatMessage.timestamp).all()
    return jsonify([msg.to_dict() for msg in messages])


@app.route("/api/tutor/send", methods=["POST"])
@login_required
def tutor_send():
    """Отправить сообщение тьютору (специализированному агенту)."""
    if not DEEPSEEK_AVAILABLE:
        return jsonify({'error': 'AI недоступен'}), 503
    
    # Проверяем, это JSON или FormData (для файлов)
    if request.is_json:
        data = request.get_json()
        message = data.get('message', '').strip()
        agent_type = data.get('agent_type', 'general')
        hint_mode = data.get('hint_mode', True)
        image_data = None
    else:
        # FormData с файлом
        message = request.form.get('message', '').strip()
        agent_type = request.form.get('agent_type', 'general')
        hint_mode = request.form.get('hint_mode', 'true').lower() == 'true'
        
        # Обработка файла
        image_data = None
        if 'file' in request.files:
            file = request.files['file']
            if file and file.filename:
                import base64
                image_data = base64.b64encode(file.read()).decode('utf-8')
    
    if not message:
        return jsonify({'error': 'Сообщение пустое'}), 400
    
    try:
        from models import ChatMessage
        
        # Сохраняем сообщение пользователя с привязкой к агенту
        user_msg = ChatMessage(
            user_id=current_user.id,
            agent_type=agent_type,
            role='user',
            content=message + (" [📎 Прикреплено изображение]" if image_data else "")
        )
        db.session.add(user_msg)
        db.session.commit()
        
        # Получаем историю для ЭТОГО агента (не смешиваем с другими)
        history = ChatMessage.query.filter_by(
            user_id=current_user.id,
            agent_type=agent_type
        ).order_by(ChatMessage.timestamp).all()
        history_list = [{'role': msg.role, 'content': msg.content} for msg in history[-20:]]
        
        # Получаем ответ от AI с учетом типа агента, режима и изображения
        client = DeepSeekClient()
        response = client.chat_with_tutor(
            current_user,
            message,
            history_list,
            agent_type=agent_type,
            hint_mode=hint_mode,
            image_data=image_data
        )
        
        # Сохраняем ответ AI с привязкой к агенту
        ai_msg = ChatMessage(
            user_id=current_user.id,
            agent_type=agent_type,
            role='assistant',
            content=response
        )
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


@app.route("/api/tutor/hint/<int:problem_id>", methods=["POST"])
@login_required
def get_ai_hint(problem_id):
    """Получить наводящую подсказку от AI для конкретной задачи."""
    if not DEEPSEEK_AVAILABLE:
        return jsonify({'error': 'AI недоступен'}), 503
    
    # Ищем задачу в обеих базах
    problem = next((p for p in PROBLEMS_DB if p.get("id") == problem_id), None)
    if not problem:
        problem = next((p for p in _RAW_DB if p.get("id") == problem_id), None)
    
    if not problem:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    try:
        client = DeepSeekClient()
        hint = client.generate_hint(
            problem_text=problem.get('text', ''),
            problem_answer=problem.get('answer', ''),
            difficulty=problem.get('difficulty', 1)
        )
        
        return jsonify({
            'hint': hint,
            'problem_id': problem_id
        })
        
    except Exception as e:
        app.logger.error(f"AI Hint error: {e}")
        return jsonify({'error': f'Ошибка генерации подсказки: {str(e)}'}), 500


@app.route("/api/tutor/solution/<int:problem_id>", methods=["POST"])
@login_required
def get_ai_solution(problem_id):
    """Получить полное решение от AI для конкретной задачи."""
    if not DEEPSEEK_AVAILABLE:
        return jsonify({'error': 'AI недоступен'}), 503
    
    # Ищем задачу в обеих базах
    problem = next((p for p in PROBLEMS_DB if p.get("id") == problem_id), None)
    if not problem:
        problem = next((p for p in _RAW_DB if p.get("id") == problem_id), None)
    
    if not problem:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    try:
        client = DeepSeekClient()
        solution = client.generate_solution(
            problem_text=problem.get('text', ''),
            problem_answer=problem.get('answer', ''),
            difficulty=problem.get('difficulty', 1)
        )
        
        return jsonify({
            'solution': solution,
            'answer': problem.get('answer', ''),
            'problem_id': problem_id
        })
        
    except Exception as e:
        app.logger.error(f"AI Solution error: {e}")
        return jsonify({'error': f'Ошибка генерации решения: {str(e)}'}), 500


@app.route("/profile")
@login_required
def profile():
    """Личный кабинет пользователя с учениками."""
    # Получаем список учеников (accepted)
    mentorships = Mentorship.query.filter_by(
        teacher_id=current_user.id,
        status='accepted'
    ).all()
    
    students = []
    for m in mentorships:
        student = User.query.get(m.student_id)
        if student:
            students.append(student)
    
    # Получаем входящие заявки (где я - ученик)
    pending_requests = Mentorship.query.filter_by(
        student_id=current_user.id,
        status='pending'
    ).all()
    
    incoming_requests = []
    for m in pending_requests:
        teacher = User.query.get(m.teacher_id)
        if teacher:
            incoming_requests.append({'mentorship': m, 'teacher': teacher})
    
    return render_template('profile.html',
                         user=current_user,
                         students=students,
                         incoming_requests=incoming_requests)


# ============================================================
# MOCK EXAMS (Пробники)
# ============================================================

@app.route("/api/exam/generate", methods=["POST"])
@login_required
def generate_exam():
    """Генерация нового пробника с задачами разного уровня сложности."""
    from models import MockExam, MockExamTask
    import random
    
    data = request.get_json() or {}
    grade = data.get('grade', 9)  # По умолчанию 9 класс
    
    # Фильтруем задачи по классу
    grade_problems = [p for p in PROBLEMS_DB if p.get('grade') == grade]
    
    if not grade_problems:
        # Если нет задач для класса, берем любые
        grade_problems = PROBLEMS_DB
    
    # Группируем по уровню сложности
    by_difficulty = {}
    for p in grade_problems:
        diff = p.get('difficulty', 3)
        if diff not in by_difficulty:
            by_difficulty[diff] = []
        by_difficulty[diff].append(p)
    
    # Выбираем задачи с нарастающей сложностью (как на реальной олимпиаде)
    selected_problems = []
    target_distribution = [
        (1, 2, 1),  # 1 легкая задача
        (3, 4, 2),  # 2 средние задачи
        (5, 6, 1),  # 1 сложная задача
        (7, 10, 1)  # 1 очень сложная задача
    ]
    
    for min_diff, max_diff, count in target_distribution:
        candidates = []
        for d in range(min_diff, max_diff + 1):
            candidates.extend(by_difficulty.get(d, []))
        if candidates:
            selected_problems.extend(random.sample(candidates, min(count, len(candidates))))
    
    # Дополняем до 5 если нужно
    if len(selected_problems) < 5:
        remaining = [p for p in grade_problems if p not in selected_problems]
        if remaining:
            selected_problems.extend(random.sample(remaining, min(5 - len(selected_problems), len(remaining))))
    
    # Ограничиваем до 5 задач
    selected_problems = selected_problems[:5]
    
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


# ============================================================
# ADAPTIVE TESTING (Адаптивное тестирование)
# ============================================================

@app.route("/api/adaptive-test/start", methods=["POST"])
@login_required
def start_adaptive_test():
    """Начать новое адаптивное тестирование."""
    from models import AdaptiveTest, AdaptiveTestProblem
    from services.adaptive_test import AdaptiveTestEngine
    
    data = request.get_json() or {}
    subject = data.get('subject')  # Опционально: фильтр по предмету
    grade = data.get('grade')  # Опционально: фильтр по классу
    num_problems = data.get('num_problems', 25)  # По умолчанию 25 задач
    
    # Получаем историю пользователя для оценки начального уровня
    user_history = []
    previous_tests = AdaptiveTest.query.filter_by(
        user_id=current_user.id,
        status='completed'
    ).order_by(AdaptiveTest.completed_at.desc()).limit(5).all()
    
    for test in previous_tests:
        for problem in test.problems:
            if problem.is_correct is not None:
                user_history.append({
                    'difficulty': problem.problem_difficulty,
                    'is_correct': problem.is_correct
                })
    
    # Создаем движок адаптивного тестирования
    engine = AdaptiveTestEngine(PROBLEMS_DB)
    
    # Оцениваем начальный уровень
    initial_ability = engine.estimate_user_ability(user_history) if user_history else 3.5
    
    # Создаем тест
    test = AdaptiveTest(
        user_id=current_user.id,
        subject=subject,
        grade=grade,
        num_problems=num_problems,
        initial_ability=initial_ability,
        current_ability=initial_ability
    )
    db.session.add(test)
    db.session.flush()
    
    # Выбираем первую задачу
    first_problem = engine.select_next_problem(
        user_ability=initial_ability,
        subject=subject,
        grade=grade,
        excluded_ids=[]
    )
    
    if not first_problem:
        db.session.rollback()
        return jsonify({'error': 'Не удалось найти подходящие задачи'}), 400
    
    # Добавляем первую задачу
    test_problem = AdaptiveTestProblem(
        test_id=test.id,
        problem_id=first_problem['id'],
        sequence_number=1,
        user_ability_before=initial_ability,
        problem_difficulty=float(first_problem.get('level', 3.5))
    )
    db.session.add(test_problem)
    db.session.commit()
    
    return jsonify({
        'test_id': test.id,
        'problem': first_problem,
        'current_number': 1,
        'total_problems': num_problems,
        'current_ability': initial_ability
    })


@app.route("/api/problem/<int:problem_id>")
@login_required
def get_problem(problem_id):
    """Получить данные задачи по ID"""
    problem = next((p for p in PROBLEMS_DB if p['id'] == problem_id), None)
    if problem:
        return jsonify(problem)
    return jsonify({'error': 'Problem not found'}), 404


@app.route("/api/adaptive-test/<int:test_id>/submit", methods=["POST"])
@login_required
def submit_adaptive_answer(test_id):
    """Отправить ответ на задачу адаптивного теста."""
    from models import AdaptiveTest, AdaptiveTestProblem
    from services.adaptive_test import AdaptiveTestEngine
    
    test = AdaptiveTest.query.get_or_404(test_id)
    
    if test.user_id != current_user.id:
        abort(403)
    
    if test.status != 'in_progress':
        return jsonify({'error': 'Тест уже завершен'}), 400
    
    data = request.get_json() or {}
    problem_id = data.get('problem_id')
    user_answer = data.get('answer', '').strip()
    user_solution = data.get('solution', '').strip()
    
    # Находим текущую задачу
    current_problem_record = AdaptiveTestProblem.query.filter_by(
        test_id=test_id,
        problem_id=problem_id
    ).first()
    
    if not current_problem_record:
        return jsonify({'error': 'Задача не найдена'}), 404
    
    if current_problem_record.is_correct is not None:
        return jsonify({'error': 'Ответ уже отправлен'}), 400
    
    # Находим задачу в базе
    problem = next((p for p in PROBLEMS_DB if p['id'] == problem_id), None)
    if not problem:
        return jsonify({'error': 'Задача не найдена в базе'}), 404
    
    # Проверяем ответ
    correct_answer = str(problem.get('answer', '')).strip().lower()
    user_answer_normalized = user_answer.lower()
    is_correct = (user_answer_normalized == correct_answer)
    
    # Обновляем запись задачи
    current_problem_record.user_answer = user_answer
    current_problem_record.user_solution_text = user_solution
    current_problem_record.is_correct = is_correct
    current_problem_record.answered_at = datetime.utcnow()
    
    # Обновляем способность пользователя
    engine = AdaptiveTestEngine(PROBLEMS_DB)
    new_ability = engine.update_ability_after_answer(
        current_ability=test.current_ability,
        problem_difficulty=current_problem_record.problem_difficulty,
        is_correct=is_correct
    )
    
    current_problem_record.user_ability_after = new_ability
    test.current_ability = new_ability
    
    # Проверяем, нужно ли добавить следующую задачу
    answered_count = AdaptiveTestProblem.query.filter_by(test_id=test_id).filter(
        AdaptiveTestProblem.is_correct.isnot(None)
    ).count()
    
    next_problem = None
    if answered_count < test.num_problems:
        # Выбираем следующую задачу
        excluded_ids = [p.problem_id for p in test.problems]
        
        next_problem_data = engine.select_next_problem(
            user_ability=new_ability,
            subject=test.subject,
            grade=test.grade,
            excluded_ids=excluded_ids
        )
        
        if next_problem_data:
            next_problem_record = AdaptiveTestProblem(
                test_id=test.id,
                problem_id=next_problem_data['id'],
                sequence_number=answered_count + 1,
                user_ability_before=new_ability,
                problem_difficulty=float(next_problem_data.get('level', 3.5))
            )
            db.session.add(next_problem_record)
            next_problem = next_problem_data
    
    # Если это была последняя задача, завершаем тест
    if answered_count >= test.num_problems or next_problem is None:
        test.status = 'analyzing'
        test.completed_at = datetime.utcnow()
    
    db.session.commit()
    
    response = {
        'is_correct': is_correct,
        'correct_answer': problem.get('answer'),
        'current_ability': round(new_ability, 2),
        'answered_count': answered_count,
        'total_problems': test.num_problems
    }
    
    if next_problem:
        response['next_problem'] = next_problem
        response['next_number'] = answered_count + 1
    else:
        response['test_completed'] = True
        response['test_id'] = test.id
    
    return jsonify(response)


@app.route("/api/adaptive-test/<int:test_id>/analyze", methods=["POST"])
@login_required
def analyze_adaptive_test(test_id):
    """Анализ результатов адаптивного теста с помощью AI."""
    from models import AdaptiveTest, AdaptiveTestProblem
    from services.adaptive_test import AdaptiveTestEngine, get_olympiad_status
    
    test = AdaptiveTest.query.get_or_404(test_id)
    
    if test.user_id != current_user.id:
        abort(403)
    
    if test.status not in ['analyzing', 'completed']:
        return jsonify({'error': 'Тест еще не завершен'}), 400
    
    # Собираем данные для анализа
    problems = []
    answers = []
    
    for problem_record in test.problems.order_by(AdaptiveTestProblem.sequence_number):
        problem = next((p for p in PROBLEMS_DB if p['id'] == problem_record.problem_id), None)
        if problem:
            problems.append(problem)
            answers.append({
                'is_correct': problem_record.is_correct,
                'user_answer': problem_record.user_answer,
                'solution': problem_record.user_solution_text
            })
    
    # Анализируем результаты
    engine = AdaptiveTestEngine(PROBLEMS_DB)
    analysis = engine.analyze_test_results(problems, answers)
    
    # Обновляем тест
    test.final_ability = analysis['final_ability']
    test.total_correct = analysis['total_correct']
    test.accuracy = analysis['accuracy']
    
    # Получаем олимпиадный статус
    olympiad_status = get_olympiad_status(analysis['final_ability'])
    
    # Собираем статистику по разделам
    subject_stats = {}
    for problem, answer in zip(problems, answers):
        subject = problem.get('subject', 'unknown')
        if subject not in subject_stats:
            subject_stats[subject] = {'correct': 0, 'total': 0}
        subject_stats[subject]['total'] += 1
        if answer.get('is_correct'):
            subject_stats[subject]['correct'] += 1
    
    # Определяем сильные и слабые разделы
    strong_subjects = []
    weak_subjects = []
    for subject, stats in subject_stats.items():
        accuracy = stats['correct'] / stats['total'] if stats['total'] > 0 else 0
        if accuracy >= 0.7 and stats['total'] >= 3:
            strong_subjects.append(subject)
        elif accuracy < 0.5 and stats['total'] >= 3:
            weak_subjects.append(subject)
    
    # Генерируем AI анализ если доступен
    if DEEPSEEK_AVAILABLE:
        try:
            client = DeepSeekClient()
            
            # Переводим названия разделов на русский
            subject_names = {
                'algebra': 'Алгебра',
                'geometry': 'Геометрия',
                'combinatorics': 'Комбинаторика',
                'number_theory': 'Теория чисел',
                'movement': 'Задачи на движение',
                'knights_liars': 'Рыцари и лжецы'
            }
            
            strong_names = [subject_names.get(s, s) for s in strong_subjects]
            weak_names = [subject_names.get(s, s) for s in weak_subjects]
            
            # Формируем промпт для AI-тренера
            prompt = f"""Ты опытный тренер олимпиадной сборной. Ученик только что прошел адаптивное тестирование (25 задач).

Его итоговый статус: {olympiad_status['status']}
Финальный уровень: {analysis['final_ability']:.1f}/7.0
Правильных ответов: {analysis['total_correct']} из {analysis['total_problems']} ({analysis['accuracy']:.0f}%)

Сильные разделы: {', '.join(strong_names) if strong_names else 'пока не выявлены'}
Слабые разделы: {', '.join(weak_names) if weak_names else 'пока не выявлены'}

Напиши короткий, ободряющий отзыв (3-4 предложения) с конкретной рекомендацией, на какие разделы на сайте FORMYLA ему нужно сделать упор в ближайший месяц, чтобы достичь следующего статуса: {olympiad_status.get('next_status', 'высшего уровня')}.

Будь мотивирующим, но честным. Говори прямо и по делу, как настоящий тренер."""

            # Отправляем с таймаутом 10 секунд
            ai_analysis = client.generate(
                prompt=prompt,
                system_prompt="Ты опытный тренер олимпиадной математической сборной. Твоя задача - мотивировать учеников и давать конкретные рекомендации.",
                temperature=0.8,
                max_tokens=400
            )
            
            test.ai_analysis = ai_analysis
            
        except Exception as e:
            logger.error(f"Ошибка AI анализа: {e}")
            test.ai_analysis = "ИИ-тренер сейчас анализирует результаты других олимпиадников. Загляните сюда чуть позже!"
    
    test.status = 'completed'
    db.session.commit()
    
    return jsonify({
        'analysis': analysis,
        'ai_analysis': test.ai_analysis,
        'olympiad_status': olympiad_status
    })


@app.route("/adaptive-test/<int:test_id>")
@login_required
def adaptive_test_page(test_id):
    """Страница прохождения адаптивного теста."""
    from models import AdaptiveTest
    
    test = AdaptiveTest.query.get_or_404(test_id)
    
    if test.user_id != current_user.id:
        abort(403)
    
    # Конвертируем задачи в словари для JSON с данными задач
    problems_list = [p.to_dict(include_problem_data=True) for p in test.problems.all()]
    
    return render_template('adaptive_test.html', test=test, problems_list=problems_list)


@app.route("/adaptive-test/<int:test_id>/results")
@login_required
def adaptive_test_results(test_id):
    """Страница результатов адаптивного теста."""
    from models import AdaptiveTest
    from services.adaptive_test import get_olympiad_status
    
    test = AdaptiveTest.query.get_or_404(test_id)
    
    if test.user_id != current_user.id:
        abort(403)
    
    # Получаем задачи с результатами
    results_data = []
    for problem_record in test.problems.order_by(AdaptiveTestProblem.sequence_number):
        problem = next((p for p in PROBLEMS_DB if p['id'] == problem_record.problem_id), None)
        if problem:
            results_data.append({
                'problem': problem,
                'user_answer': problem_record.user_answer,
                'user_solution': problem_record.user_solution_text,
                'is_correct': problem_record.is_correct,
                'difficulty': problem_record.problem_difficulty,
                'ability_before': problem_record.user_ability_before,
                'ability_after': problem_record.user_ability_after
            })
    
    # Получаем олимпиадный статус
    olympiad_status = get_olympiad_status(test.final_ability) if test.final_ability else None
    
    return render_template('adaptive_test_results.html', test=test, results=results_data, olympiad_status=olympiad_status)


# ============================================================
# СЕКРЕТЫ ОЛИМПИАДНИКОВ
# ============================================================

SECRETS_TOPICS = {
    'number_theory_digits': 'Разложение на разряды',
    'divisibility': 'Признаки делимости',
    'modulo': 'Остатки и модули',
    'gcd_lcm': 'НОД и НОК',
    'combinatorics_rules': 'Правило суммы и произведения',
    'dirichlet': 'Принцип Дирихле',
    'algebra_estimation': 'Метод оценки',
    'am_gm': 'Неравенство AM-GM',
    'geometry_areas': 'Площади и отношения',
    'circles': 'Вписанные окружности',
    'logic_invariant': 'Инвариант',
    'coloring': 'Раскраска'
}

@app.route("/secrets")
def secrets():
    """Список секретов олимпиадников."""
    return render_template('secrets.html', topics=SECRETS_TOPICS)


@app.route("/secrets/<topic_slug>")
def secret_topic(topic_slug):
    """Страница с теорией (AI-генерация)."""
    if topic_slug not in SECRETS_TOPICS:
        abort(404)
    
    from models import SecretTopic
    
    # Ищем в кэше
    topic = SecretTopic.query.filter_by(slug=topic_slug).first()
    
    if not topic and DEEPSEEK_AVAILABLE:
        # Генерируем через AI
        try:
            client = DeepSeekClient()
            title = SECRETS_TOPICS[topic_slug]
            
            prompt = f"""Создай подробный теоретический материал по теме: {title}

Структура:
1. Краткое объяснение метода
2. Формулы и правила
3. 2-3 примера задач с решениями
4. Когда применять

Формат: HTML с inline стилями (темная тема)"""
            
            content = client.generate(prompt, temperature=0.7, max_tokens=2000)
            
            # Сохраняем в кэш
            topic = SecretTopic(slug=topic_slug, title=title, content=content)
            db.session.add(topic)
            db.session.commit()
            
        except:
            topic = SecretTopic(slug=topic_slug, title=SECRETS_TOPICS[topic_slug], content="<p>Контент генерируется...</p>")
    
    return render_template('secret_topic.html', topic=topic)


@app.route("/social")
@login_required
def social_page():
    """Страница социальных функций"""
    return render_template('social.html')


# ============================================================
# SOCIAL FEATURES API
# ============================================================

@app.route("/api/social/set-nickname", methods=["POST"])
@login_required
def set_nickname():
    """Установить никнейм пользователя"""
    try:
        data = request.get_json()
        nickname = data.get('nickname', '').strip()
        
        # Валидация
        if not nickname:
            return jsonify({'success': False, 'error': 'Nickname cannot be empty'}), 400
        
        if len(nickname) < 3 or len(nickname) > 50:
            return jsonify({'success': False, 'error': 'Nickname must be 3-50 characters'}), 400
        
        # Проверка на допустимые символы (буквы, цифры, подчеркивание)
        import re
        if not re.match(r'^[a-zA-Z0-9_а-яА-ЯёЁ]+$', nickname):
            return jsonify({'success': False, 'error': 'Nickname can only contain letters, numbers and underscore'}), 400
        
        # Проверка уникальности
        existing = User.query.filter_by(nickname=nickname).first()
        if existing and existing.id != current_user.id:
            return jsonify({'success': False, 'error': 'Nickname already taken'}), 409
        
        # Устанавливаем никнейм
        current_user.nickname = nickname
        db.session.commit()
        
        return jsonify({'success': True, 'nickname': nickname})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/search-users")
@login_required
def search_users():
    """Поиск пользователей по никнейму"""
    try:
        query = request.args.get('q', '').strip()
        limit = min(int(request.args.get('limit', 10)), 50)  # Максимум 50
        
        if not query or len(query) < 2:
            return jsonify({'success': False, 'error': 'Query too short (min 2 characters)'}), 400
        
        # Поиск по никнейму (LIKE с LIMIT)
        users = User.query.filter(
            User.nickname.ilike(f'%{query}%'),
            User.id != current_user.id  # Исключаем себя
        ).limit(limit).all()
        
        results = [{
            'id': u.id,
            'nickname': u.nickname,
            'name': u.name,
            'avatar_url': u.avatar_url
        } for u in users if u.nickname]  # Только с никнеймами
        
        return jsonify({'success': True, 'users': results})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/friends/request", methods=["POST"])
@login_required
def send_friend_request():
    """Отправить заявку в друзья"""
    try:
        data = request.get_json()
        to_user_id = data.get('user_id')
        
        if not to_user_id:
            return jsonify({'success': False, 'error': 'User ID required'}), 400
        
        # Проверка существования пользователя
        to_user = User.query.get(to_user_id)
        if not to_user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        # Создаем заявку (с проверкой на себя и дубликаты)
        friendship = Friendship.create_friendship_request(current_user.id, to_user_id)
        db.session.add(friendship)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'friendship_id': friendship.id,
            'status': friendship.status
        })
    
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/friends/respond", methods=["POST"])
@login_required
def respond_friend_request():
    """Принять или отклонить заявку в друзья"""
    try:
        data = request.get_json()
        friendship_id = data.get('friendship_id')
        action = data.get('action')  # 'accept' or 'reject'
        
        if not friendship_id or action not in ['accept', 'reject']:
            return jsonify({'success': False, 'error': 'Invalid parameters'}), 400
        
        friendship = Friendship.query.get(friendship_id)
        if not friendship:
            return jsonify({'success': False, 'error': 'Friendship not found'}), 404
        
        # Проверка прав (только получатель может принять/отклонить)
        if friendship.user_1_id != current_user.id and friendship.user_2_id != current_user.id:
            return jsonify({'success': False, 'error': 'Not authorized'}), 403
        
        if action == 'accept':
            friendship.accept()
        else:
            friendship.reject()
        
        db.session.commit()
        
        return jsonify({'success': True, 'status': friendship.status})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/friends/list")
@login_required
def list_friends():
    """Получить список друзей"""
    try:
        # Получаем все дружбы где пользователь участвует
        friendships = Friendship.query.filter(
            db.or_(
                Friendship.user_1_id == current_user.id,
                Friendship.user_2_id == current_user.id
            ),
            Friendship.status == 'accepted'
        ).all()
        
        friends = []
        for f in friendships:
            other_user_id = f.get_other_user_id(current_user.id)
            other_user = User.query.get(other_user_id)
            if other_user:
                friends.append({
                    'id': other_user.id,
                    'nickname': other_user.nickname,
                    'name': other_user.name,
                    'avatar_url': other_user.avatar_url
                })
        
        return jsonify({'success': True, 'friends': friends})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/mentorship/request", methods=["POST"])
@login_required
def send_mentorship_request():
    """Отправить заявку учитель-ученик"""
    try:
        data = request.get_json()
        student_id = data.get('student_id')
        
        if not student_id:
            return jsonify({'success': False, 'error': 'Student ID required'}), 400
        
        # Проверка существования пользователя
        student = User.query.get(student_id)
        if not student:
            return jsonify({'success': False, 'error': 'Student not found'}), 404
        
        # Создаем заявку (текущий пользователь = учитель)
        mentorship = Mentorship.create_mentorship_request(current_user.id, student_id)
        db.session.add(mentorship)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'mentorship_id': mentorship.id,
            'status': mentorship.status
        })
    
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/mentorship/respond", methods=["POST"])
@login_required
def respond_mentorship_request():
    """Принять или отклонить заявку учитель-ученик"""
    try:
        data = request.get_json()
        mentorship_id = data.get('mentorship_id')
        action = data.get('action')  # 'accept' or 'reject'
        
        if not mentorship_id or action not in ['accept', 'reject']:
            return jsonify({'success': False, 'error': 'Invalid parameters'}), 400
        
        mentorship = Mentorship.query.get(mentorship_id)
        if not mentorship:
            return jsonify({'success': False, 'error': 'Mentorship not found'}), 404
        
        # Проверка прав (только ученик может принять/отклонить)
        if mentorship.student_id != current_user.id:
            return jsonify({'success': False, 'error': 'Not authorized'}), 403
        
        if action == 'accept':
            mentorship.accept()
        else:
            mentorship.reject()
        
        db.session.commit()
        
        return jsonify({'success': True, 'status': mentorship.status})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/mentorship/students")
@login_required
def list_students():
    """Получить список учеников (для учителя)"""
    try:
        mentorships = Mentorship.query.filter_by(
            teacher_id=current_user.id,
            status='accepted'
        ).all()
        
        students = []
        for m in mentorships:
            student = User.query.get(m.student_id)
            if student:
                students.append({
                    'id': student.id,
                    'nickname': student.nickname,
                    'name': student.name,
                    'avatar_url': student.avatar_url
                })
        
        return jsonify({'success': True, 'students': students})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route("/api/social/mentorship/teachers")
@login_required
def list_teachers():
    """Получить список учителей (для ученика)"""
    try:
        mentorships = Mentorship.query.filter_by(
            student_id=current_user.id,
            status='accepted'
        ).all()
        
        teachers = []
        for m in mentorships:
            teacher = User.query.get(m.teacher_id)
            if teacher:
                teachers.append({
                    'id': teacher.id,
                    'nickname': teacher.nickname,
                    'name': teacher.name,
                    'avatar_url': teacher.avatar_url
                })
        
        return jsonify({'success': True, 'teachers': teachers})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# PROFILE AND STUDENT PROGRESS TRACKING
# ============================================================

@app.route("/update_nickname", methods=["POST"])
@login_required
def update_nickname():
    """Обновление nickname пользователя"""
    import re
    
    new_nickname = request.form.get('nickname', '').strip()
    
    # Убираем @ если есть
    if new_nickname.startswith('@'):
        new_nickname = new_nickname[1:]
    
    # Валидация
    if not new_nickname:
        flash('Никнейм не может быть пустым', 'error')
        return redirect(url_for('profile'))
    
    if len(new_nickname) < 3 or len(new_nickname) > 50:
        flash('Никнейм должен быть от 3 до 50 символов', 'error')
        return redirect(url_for('profile'))
    
    # Только буквы, цифры и подчеркивание
    if not re.match(r'^[a-zA-Z0-9_а-яА-ЯёЁ]+$', new_nickname):
        flash('Никнейм может содержать только буквы, цифры и подчеркивание', 'error')
        return redirect(url_for('profile'))
    
    # Проверка уникальности
    existing = User.query.filter(User.nickname.ilike(new_nickname)).first()
    if existing and existing.id != current_user.id:
        flash(f'Никнейм @{new_nickname} уже занят', 'error')
        return redirect(url_for('profile'))
    
    # Обновляем
    try:
        current_user.nickname = new_nickname
        db.session.commit()
        flash(f'Никнейм успешно изменен на @{new_nickname}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при обновлении: {str(e)}', 'error')
    
    return redirect(url_for('profile'))


@app.route("/add_student", methods=["POST"])
@login_required
def add_student():
    """Добавление ученика по nickname"""
    student_nickname = request.form.get('nickname', '').strip()
    
    # Убираем @ если пользователь ввел
    if student_nickname.startswith('@'):
        student_nickname = student_nickname[1:]
    
    if not student_nickname:
        flash('Введите никнейм ученика', 'error')
        return redirect(url_for('profile'))
    
    # Ищем пользователя по nickname (case-insensitive)
    student = User.query.filter(User.nickname.ilike(student_nickname)).first()
    
    if not student:
        flash(f'Пользователь @{student_nickname} не найден', 'error')
        return redirect(url_for('profile'))
    
    if student.id == current_user.id:
        flash('Нельзя добавить самого себя', 'error')
        return redirect(url_for('profile'))
    
    # Проверяем существующую связь
    existing = Mentorship.query.filter_by(
        teacher_id=current_user.id,
        student_id=student.id
    ).first()
    
    if existing:
        if existing.status == 'pending':
            flash('Заявка уже отправлена, ожидает подтверждения', 'warning')
        elif existing.status == 'accepted':
            flash('Этот ученик уже добавлен', 'info')
        else:
            flash('Заявка была отклонена ранее', 'error')
        return redirect(url_for('profile'))
    
    # Создаем заявку
    try:
        mentorship = Mentorship(
            teacher_id=current_user.id,
            student_id=student.id,
            status='pending'  # Требует подтверждения от ученика
        )
        db.session.add(mentorship)
        db.session.commit()
        flash(f'Заявка отправлена пользователю @{student.nickname}. Ожидайте подтверждения.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при добавлении: {str(e)}', 'error')
    
    return redirect(url_for('profile'))


@app.route("/accept_request/<int:mentorship_id>", methods=["POST"])
@login_required
def accept_request(mentorship_id):
    """Принять заявку на менторство"""
    mentorship = Mentorship.query.get_or_404(mentorship_id)
    
    # Проверка прав (только ученик может принять)
    if mentorship.student_id != current_user.id:
        flash('У вас нет прав для этого действия', 'error')
        return redirect(url_for('profile'))
    
    try:
        mentorship.accept()
        db.session.commit()
        teacher = User.query.get(mentorship.teacher_id)
        flash(f'Вы приняли заявку от @{teacher.nickname or teacher.email}!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect(url_for('profile'))


@app.route("/reject_request/<int:mentorship_id>", methods=["POST"])
@login_required
def reject_request(mentorship_id):
    """Отклонить заявку на менторство"""
    mentorship = Mentorship.query.get_or_404(mentorship_id)
    
    # Проверка прав (только ученик может отклонить)
    if mentorship.student_id != current_user.id:
        flash('У вас нет прав для этого действия', 'error')
        return redirect(url_for('profile'))
    
    try:
        mentorship.reject()
        db.session.commit()
        flash('Заявка отклонена', 'info')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
    
    return redirect(url_for('profile'))


@app.route("/student/<int:student_id>")
@login_required
def student_profile(student_id):
    """Просмотр профиля ученика"""
    # Проверяем права доступа
    mentorship = Mentorship.query.filter_by(
        teacher_id=current_user.id,
        student_id=student_id,
        status='accepted'
    ).first()
    
    if not mentorship:
        flash('У вас нет доступа к этому профилю', 'error')
        return redirect(url_for('profile'))
    
    student = User.query.get_or_404(student_id)
    
    # Собираем статистику ученика
    # (здесь можно добавить подсчет решенных задач, тестов и т.д.)
    
    return render_template('student_profile.html',
        student=student,
        teacher=current_user
    )


if __name__ == '__main__':
    app.run(debug=True, port=5001)

 
