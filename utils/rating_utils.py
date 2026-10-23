"""
Система рейтинга и опыта (XP) для пользователей.
Управляет начислением очков опыта и повышением уровней.
"""

# Константы системы рейтинга
MAX_LEVEL = 10
XP_PER_LEVEL = 100
XP_PER_DIFFICULTY = 10  # Базовое количество XP за уровень сложности
BONUS_MULTIPLIER = 2  # Множитель для бонуса за новую максимальную сложность
ADAPTIVE_TEST_BONUS = 50  # Бонус за завершение адаптивного теста
MOCK_EXAM_BONUS = 100  # Бонус за пробник с результатом >= 80%
MOCK_EXAM_THRESHOLD = 80  # Минимальный процент для получения бонуса


def add_xp_for_task(user, task_difficulty):
    """
    Начисляет XP за решение обычной задачи.
    
    Формула: 10 XP * уровень сложности задачи
    
    Args:
        user: Объект пользователя (модель User)
        task_difficulty: Уровень сложности задачи (1-7)
    
    Returns:
        dict: Информация о начисленном опыте
            {
                'xp_gained': int,
                'bonus_xp': int,
                'total_xp': int,
                'old_level': int,
                'new_level': int,
                'level_up': bool,
                'reason': str
            }
    """
    if task_difficulty < 1:
        task_difficulty = 1
    
    # Сохраняем старый уровень для проверки повышения
    old_level = user.current_level
    old_xp = user.experience_points
    
    # Базовое начисление XP
    base_xp = XP_PER_DIFFICULTY * task_difficulty
    user.experience_points += base_xp
    
    # Проверяем бонус за новую максимальную сложность
    bonus_xp = add_bonus_for_max_difficulty(user, task_difficulty)
    
    # Обновляем счетчик решенных задач
    user.total_problems_solved += 1
    
    # Проверяем повышение уровня
    _check_level_up(user)
    
    return {
        'xp_gained': base_xp,
        'bonus_xp': bonus_xp,
        'total_xp': user.experience_points,
        'old_level': old_level,
        'new_level': user.current_level,
        'level_up': user.current_level > old_level,
        'reason': 'task_solved'
    }


def add_bonus_for_max_difficulty(user, task_difficulty):
    """
    Начисляет бонус, если пользователь решил задачу сложнее, чем когда-либо раньше.
    
    Формула: 20 XP * уровень сложности (двойной бонус)
    
    Args:
        user: Объект пользователя
        task_difficulty: Уровень сложности задачи
    
    Returns:
        int: Количество бонусного XP (0 если бонус не начислен)
    """
    if task_difficulty > user.highest_difficulty_solved:
        bonus = XP_PER_DIFFICULTY * BONUS_MULTIPLIER * task_difficulty
        user.experience_points += bonus
        user.highest_difficulty_solved = task_difficulty
        
        print(f"[BONUS] User {user.id} solved difficulty {task_difficulty} (new record!)")
        print(f"   Bonus XP awarded: {bonus}")
        
        return bonus
    return 0


def add_xp_for_adaptive_test(user):
    """
    Начисляет бонус за завершение адаптивного теста.
    
    Бонус: +50 XP
    
    Args:
        user: Объект пользователя
    
    Returns:
        dict: Информация о начисленном опыте
    """
    old_level = user.current_level
    
    user.experience_points += ADAPTIVE_TEST_BONUS
    user.adaptive_tests_completed += 1
    
    _check_level_up(user)
    
    return {
        'xp_gained': ADAPTIVE_TEST_BONUS,
        'bonus_xp': 0,
        'total_xp': user.experience_points,
        'old_level': old_level,
        'new_level': user.current_level,
        'level_up': user.current_level > old_level,
        'reason': 'adaptive_test_completed'
    }


def add_xp_for_mock_exam(user, score_percentage):
    """
    Начисляет бонус за успешное прохождение пробника.
    
    Бонус: +100 XP если результат >= 80%
    
    Args:
        user: Объект пользователя
        score_percentage: Процент правильных ответов (0-100)
    
    Returns:
        dict: Информация о начисленном опыте
    """
    old_level = user.current_level
    xp_gained = 0
    
    if score_percentage >= MOCK_EXAM_THRESHOLD:
        xp_gained = MOCK_EXAM_BONUS
        user.experience_points += xp_gained
        user.mock_exams_passed += 1
        
        print(f"[SUCCESS] User {user.id} passed mock exam with {score_percentage}%!")
        print(f"   XP awarded: {xp_gained}")
    
    _check_level_up(user)
    
    return {
        'xp_gained': xp_gained,
        'bonus_xp': 0,
        'total_xp': user.experience_points,
        'old_level': old_level,
        'new_level': user.current_level,
        'level_up': user.current_level > old_level,
        'reason': 'mock_exam_completed',
        'passed': score_percentage >= MOCK_EXAM_THRESHOLD
    }


def _check_level_up(user):
    """
    Проверяет и обновляет уровень пользователя на основе накопленного XP.
    
    Формула: Уровень = 1 + (XP // 100), максимум 10
    
    Args:
        user: Объект пользователя
    """
    new_level = 1 + (user.experience_points // XP_PER_LEVEL)
    
    if new_level > MAX_LEVEL:
        user.current_level = MAX_LEVEL
    else:
        user.current_level = new_level
    
    # Логирование повышения уровня
    if user.current_level != new_level and new_level <= MAX_LEVEL:
        print(f"[LEVEL UP] User {user.id} reached level {user.current_level}!")


def get_xp_for_next_level(user):
    """
    Вычисляет, сколько XP нужно до следующего уровня.
    
    Args:
        user: Объект пользователя
    
    Returns:
        dict: Информация о прогрессе
            {
                'current_xp': int,
                'current_level': int,
                'xp_for_current_level': int,
                'xp_for_next_level': int,
                'xp_needed': int,
                'progress_percentage': float
            }
    """
    if user.current_level >= MAX_LEVEL:
        return {
            'current_xp': user.experience_points,
            'current_level': user.current_level,
            'xp_for_current_level': (MAX_LEVEL - 1) * XP_PER_LEVEL,
            'xp_for_next_level': MAX_LEVEL * XP_PER_LEVEL,
            'xp_needed': 0,
            'progress_percentage': 100.0,
            'max_level_reached': True
        }
    
    xp_for_current_level = (user.current_level - 1) * XP_PER_LEVEL
    xp_for_next_level = user.current_level * XP_PER_LEVEL
    xp_in_current_level = user.experience_points - xp_for_current_level
    xp_needed = xp_for_next_level - user.experience_points
    progress_percentage = (xp_in_current_level / XP_PER_LEVEL) * 100
    
    return {
        'current_xp': user.experience_points,
        'current_level': user.current_level,
        'xp_for_current_level': xp_for_current_level,
        'xp_for_next_level': xp_for_next_level,
        'xp_needed': xp_needed,
        'progress_percentage': round(progress_percentage, 1),
        'max_level_reached': False
    }


def get_user_rank(user, all_users):
    """
    Определяет ранг пользователя среди всех пользователей.
    
    Args:
        user: Объект пользователя
        all_users: Список всех пользователей
    
    Returns:
        dict: Информация о ранге
            {
                'rank': int,
                'total_users': int,
                'percentile': float
            }
    """
    # Сортируем пользователей по XP (убывание)
    sorted_users = sorted(all_users, key=lambda u: u.experience_points, reverse=True)
    
    # Находим позицию текущего пользователя
    rank = next((i + 1 for i, u in enumerate(sorted_users) if u.id == user.id), None)
    
    if rank is None:
        return {'rank': None, 'total_users': len(all_users), 'percentile': 0}
    
    percentile = ((len(all_users) - rank + 1) / len(all_users)) * 100
    
    return {
        'rank': rank,
        'total_users': len(all_users),
        'percentile': round(percentile, 1)
    }


# Тесты для проверки функций
if __name__ == "__main__":
    # Создаем mock объект пользователя для тестирования
    class MockUser:
        def __init__(self):
            self.id = 1
            self.experience_points = 0
            self.current_level = 1
            self.highest_difficulty_solved = 0
            self.total_problems_solved = 0
            self.adaptive_tests_completed = 0
            self.mock_exams_passed = 0
    
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ СИСТЕМЫ РЕЙТИНГА")
    print("=" * 60)
    
    user = MockUser()
    
    # Тест 1: Решение задачи сложности 3
    print("\n1. Решение задачи сложности 3:")
    result = add_xp_for_task(user, 3)
    print(f"   XP получено: {result['xp_gained']}")
    print(f"   Бонус: {result['bonus_xp']}")
    print(f"   Всего XP: {result['total_xp']}")
    print(f"   Уровень: {result['new_level']}")
    
    # Тест 2: Решение задачи сложности 5 (новый рекорд)
    print("\n2. Решение задачи сложности 5 (новый рекорд):")
    result = add_xp_for_task(user, 5)
    print(f"   XP получено: {result['xp_gained']}")
    print(f"   Бонус: {result['bonus_xp']}")
    print(f"   Всего XP: {result['total_xp']}")
    print(f"   Уровень: {result['new_level']}")
    
    # Тест 3: Завершение адаптивного теста
    print("\n3. Завершение адаптивного теста:")
    result = add_xp_for_adaptive_test(user)
    print(f"   XP получено: {result['xp_gained']}")
    print(f"   Всего XP: {result['total_xp']}")
    print(f"   Уровень: {result['new_level']}")
    
    # Тест 4: Прохождение пробника с 85%
    print("\n4. Прохождение пробника с 85%:")
    result = add_xp_for_mock_exam(user, 85)
    print(f"   XP получено: {result['xp_gained']}")
    print(f"   Всего XP: {result['total_xp']}")
    print(f"   Уровень: {result['new_level']}")
    print(f"   Повышение уровня: {result['level_up']}")
    
    # Тест 5: Прогресс до следующего уровня
    print("\n5. Прогресс до следующего уровня:")
    progress = get_xp_for_next_level(user)
    print(f"   Текущий XP: {progress['current_xp']}")
    print(f"   Текущий уровень: {progress['current_level']}")
    print(f"   XP до следующего уровня: {progress['xp_needed']}")
    print(f"   Прогресс: {progress['progress_percentage']}%")
    
    print("\n" + "=" * 60)
    print(f"ИТОГО: Уровень {user.current_level}, XP {user.experience_points}")
    print("=" * 60)
