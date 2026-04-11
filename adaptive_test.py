import random
from flask import Blueprint, session, request, redirect, url_for, render_template
from problems import PROBLEMS_DB

# Создаем отдельный Blueprint (модуль) для адаптивного теста
adaptive_bp = Blueprint('adaptive_test', __name__)

@adaptive_bp.route('/start', methods=['POST'])
def start_adaptive_test():
    """Запуск нового адаптивного теста (25 задач)"""
    grade = request.form.get('grade', '9 класс')
    
    session['adaptive_test'] = {
        'grade': grade,
        'current_question_index': 0,
        'total_questions': 25,
        'current_level': 3,  # Начинаем со среднего уровня
        'correct_answers': 0,
        'history': [],
        'asked_ids': []
    }
    return redirect(url_for('adaptive_test.question'))

@adaptive_bp.route('/question', methods=['GET', 'POST'])
def question():
    """Вывод текущей задачи или обработка ответа"""
    test_data = session.get('adaptive_test')
    if not test_data:
        return redirect(url_for('practice'))
        
    if test_data['current_question_index'] >= test_data['total_questions']:
        return redirect(url_for('adaptive_test.result'))

    # Обработка ответа (POST)
    if request.method == 'POST':
        user_answer = request.form.get('answer', '').strip().lower()
        problem = session.get('current_adaptive_problem')
        
        if not problem:
            return redirect(url_for('adaptive_test.question'))
            
        correct_answer = str(problem.get('answer', '')).strip().lower()
        is_correct = (user_answer == correct_answer) or (correct_answer in user_answer)
        
        # Алгоритм IRT: меняем сложность
        if is_correct:
            test_data['correct_answers'] += 1
            test_data['current_level'] = min(7, test_data['current_level'] + 1)
        else:
            test_data['current_level'] = max(1, test_data['current_level'] - 1)
            
        test_data['history'].append({
            'problem_id': problem['id'],
            'level': problem['level'],
            'is_correct': is_correct,
            'user_answer': user_answer
        })
        
        test_data['asked_ids'].append(problem['id'])
        test_data['current_question_index'] += 1
        session['adaptive_test'] = test_data
        
        return redirect(url_for('adaptive_test.question'))

    # Показ задачи (GET)
    grade = test_data['grade']
    level = test_data['current_level']
    
    suitable_problems = [
        p for p in PROBLEMS_DB 
        if p['grade'] == grade and str(p['level']) == str(level) and p['id'] not in test_data['asked_ids']
    ]
    
    if not suitable_problems:
        suitable_problems = [p for p in PROBLEMS_DB if p['grade'] == grade and p['id'] not in test_data['asked_ids']]
        
    if not suitable_problems:
        return redirect(url_for('adaptive_test.result'))
        
    problem = random.choice(suitable_problems)
    session['current_adaptive_problem'] = problem
    
    # Здесь используется шаблон, который Roo должен был создать (adaptive_test.html)
    return render_template('adaptive_test.html', 
                           problem=problem, 
                           q_num=test_data['current_question_index'] + 1,
                           total=test_data['total_questions'],
                           level=level)

@adaptive_bp.route('/result')
def result():
    """Итоговый расчет вероятности диплома ВсОШ"""
    test_data = session.get('adaptive_test')
    if not test_data:
        return redirect(url_for('practice'))
        
    history = test_data['history']
    score_weight = 0
    max_possible_weight = 0
    
    for item in history:
        level_weight = int(item['level']) * 10
        max_possible_weight += level_weight
        if item['is_correct']:
            score_weight += level_weight
            
    readiness_percent = round((score_weight / max_possible_weight) * 100) if max_possible_weight > 0 else 0
        
    session.pop('adaptive_test', None)
    session.pop('current_adaptive_problem', None)
    
    return render_template('adaptive_result.html', 
                           percent=readiness_percent, 
                           history=history,
                           correct=test_data['correct_answers'],
                           total=test_data['total_questions'])