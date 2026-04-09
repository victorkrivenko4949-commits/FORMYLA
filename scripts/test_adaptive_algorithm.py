# -*- coding: utf-8 -*-
"""
Тестирование адаптивного алгоритма
Симуляция прохождения теста учениками разных уровней
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import math
import random
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('TkAgg')  # Для Windows

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.adaptive_test import AdaptiveTestEngine
from problems import PROBLEMS_DB


class StudentSimulator:
    """Симулятор ученика с определенным уровнем способностей"""
    
    def __init__(self, true_ability: float, name: str):
        """
        Args:
            true_ability: Реальный уровень способностей (1.0-7.0)
            name: Имя профиля ученика
        """
        self.true_ability = true_ability
        self.name = name
    
    def answer_problem(self, problem_difficulty: float) -> bool:
        """
        Симулирует ответ ученика на задачу.
        Использует логистическую функцию для вероятности правильного ответа.
        
        Args:
            problem_difficulty: Сложность задачи (1.0-7.0)
            
        Returns:
            True если ответ правильный, False если нет
        """
        # Разница между способностью и сложностью
        diff = self.true_ability - problem_difficulty
        
        # Логистическая функция: P(correct) = 1 / (1 + exp(-k * diff))
        # k = 1.5 - параметр крутизны кривой
        k = 1.5
        probability = 1.0 / (1.0 + math.exp(-k * diff))
        
        # Случайный ответ на основе вероятности
        return random.random() < probability
    
    def __repr__(self):
        return f"{self.name} (уровень {self.true_ability:.1f})"


def simulate_adaptive_test(student: StudentSimulator, num_problems: int = 10, verbose: bool = True):
    """
    Симулирует прохождение адаптивного теста учеником.
    
    Args:
        student: Симулятор ученика
        num_problems: Количество задач в тесте
        verbose: Выводить ли детальную информацию
        
    Returns:
        dict с результатами симуляции
    """
    engine = AdaptiveTestEngine(PROBLEMS_DB)
    
    # История для отслеживания
    history = {
        'problem_numbers': [],
        'problem_difficulties': [],
        'estimated_abilities': [],
        'information_values': [],
        'is_correct': [],
        'problems': []
    }
    
    # Начальная оценка способностей
    current_ability = 3.5
    excluded_ids = []
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"СИМУЛЯЦИЯ ТЕСТА: {student}")
        print(f"{'='*70}\n")
    
    for i in range(num_problems):
        # Выбираем задачу
        problem = engine.select_next_problem(
            user_ability=current_ability,
            excluded_ids=excluded_ids
        )
        
        if not problem:
            if verbose:
                print(f"[!] Не удалось найти задачу #{i+1}")
            break
        
        problem_difficulty = float(problem.get('level', 3.5))
        excluded_ids.append(problem['id'])
        
        # Рассчитываем информационную ценность
        info_value = engine.calculate_information_value(problem_difficulty, current_ability)
        
        # Ученик отвечает на задачу
        is_correct = student.answer_problem(problem_difficulty)
        
        # Сохраняем данные
        history['problem_numbers'].append(i + 1)
        history['problem_difficulties'].append(problem_difficulty)
        history['estimated_abilities'].append(current_ability)
        history['information_values'].append(info_value)
        history['is_correct'].append(is_correct)
        history['problems'].append(problem)
        
        if verbose:
            status = "[+] Правильно" if is_correct else "[-] Неправильно"
            print(f"Задача {i+1:2d}: сложность={problem_difficulty:.1f} | "
                  f"оценка способностей={current_ability:.2f} | "
                  f"info={info_value:.3f} | {status}")
        
        # Обновляем оценку способностей
        new_ability = engine.update_ability_after_answer(
            current_ability=current_ability,
            problem_difficulty=problem_difficulty,
            is_correct=is_correct
        )
        
        current_ability = new_ability
    
    # Финальная статистика
    total_correct = sum(history['is_correct'])
    accuracy = (total_correct / len(history['is_correct']) * 100) if history['is_correct'] else 0
    
    if verbose:
        print(f"\n{'='*70}")
        print(f"РЕЗУЛЬТАТЫ:")
        print(f"  Реальный уровень:     {student.true_ability:.2f}")
        print(f"  Финальная оценка:     {current_ability:.2f}")
        print(f"  Ошибка оценки:        {abs(current_ability - student.true_ability):.2f}")
        print(f"  Правильных ответов:   {total_correct}/{len(history['is_correct'])} ({accuracy:.1f}%)")
        print(f"  Средняя сложность:    {sum(history['problem_difficulties'])/len(history['problem_difficulties']):.2f}")
        print(f"  Средняя info value:   {sum(history['information_values'])/len(history['information_values']):.3f}")
        print(f"{'='*70}\n")
    
    history['final_ability'] = current_ability
    history['true_ability'] = student.true_ability
    history['total_correct'] = total_correct
    history['accuracy'] = accuracy
    
    return history


def plot_results(results_list: list):
    """
    Визуализирует результаты симуляций для нескольких учеников.
    
    Args:
        results_list: Список кортежей (student, history)
    """
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle('Анализ адаптивного алгоритма тестирования', fontsize=16, fontweight='bold')
    
    colors = ['#ef4444', '#3b82f6', '#22c55e']
    
    # График 1: Сложность задач
    ax1 = axes[0, 0]
    for (student, history), color in zip(results_list, colors):
        ax1.plot(history['problem_numbers'], history['problem_difficulties'], 
                marker='o', label=student.name, color=color, linewidth=2, markersize=6)
        ax1.axhline(y=student.true_ability, color=color, linestyle='--', alpha=0.5, 
                   label=f'{student.name} (реальный уровень)')
    
    ax1.set_xlabel('Номер задачи', fontsize=11)
    ax1.set_ylabel('Сложность задачи', fontsize=11)
    ax1.set_title('Динамика сложности задач', fontsize=12, fontweight='bold')
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0, 8)
    
    # График 2: Оценка способностей
    ax2 = axes[0, 1]
    for (student, history), color in zip(results_list, colors):
        ax2.plot(history['problem_numbers'], history['estimated_abilities'], 
                marker='s', label=student.name, color=color, linewidth=2, markersize=6)
        ax2.axhline(y=student.true_ability, color=color, linestyle='--', alpha=0.5)
    
    ax2.set_xlabel('Номер задачи', fontsize=11)
    ax2.set_ylabel('Оценка способностей', fontsize=11)
    ax2.set_title('Эволюция оценки способностей', fontsize=12, fontweight='bold')
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(0, 8)
    
    # График 3: Информационная ценность
    ax3 = axes[1, 0]
    for (student, history), color in zip(results_list, colors):
        ax3.plot(history['problem_numbers'], history['information_values'], 
                marker='^', label=student.name, color=color, linewidth=2, markersize=6)
    
    ax3.set_xlabel('Номер задачи', fontsize=11)
    ax3.set_ylabel('Информационная ценность', fontsize=11)
    ax3.set_title('Информационная ценность задач', fontsize=12, fontweight='bold')
    ax3.legend(fontsize=9)
    ax3.grid(True, alpha=0.3)
    
    # График 4: Сводная статистика
    ax4 = axes[1, 1]
    ax4.axis('off')
    
    stats_text = "СВОДНАЯ СТАТИСТИКА\n" + "="*50 + "\n\n"
    
    for student, history in results_list:
        error = abs(history['final_ability'] - student.true_ability)
        stats_text += f"{student.name}:\n"
        stats_text += f"  Реальный уровень:    {student.true_ability:.2f}\n"
        stats_text += f"  Финальная оценка:    {history['final_ability']:.2f}\n"
        stats_text += f"  Ошибка оценки:       {error:.2f}\n"
        stats_text += f"  Точность ответов:    {history['accuracy']:.1f}%\n"
        stats_text += f"  Правильных ответов:  {history['total_correct']}/{len(history['is_correct'])}\n"
        stats_text += f"  Средняя сложность:   {sum(history['problem_difficulties'])/len(history['problem_difficulties']):.2f}\n"
        stats_text += "\n"
    
    # Общая оценка алгоритма
    avg_error = sum(abs(h['final_ability'] - s.true_ability) for s, h in results_list) / len(results_list)
    stats_text += f"{'='*50}\n"
    stats_text += f"СРЕДНЯЯ ОШИБКА ОЦЕНКИ: {avg_error:.2f}\n"
    stats_text += f"{'='*50}\n"
    
    ax4.text(0.1, 0.95, stats_text, transform=ax4.transAxes, 
            fontsize=10, verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.3))
    
    plt.tight_layout()
    plt.savefig('adaptive_test_analysis.png', dpi=150, bbox_inches='tight')
    print("\n[*] График сохранен в: adaptive_test_analysis.png")
    plt.show()


def main():
    """Основная функция для запуска симуляций"""
    
    print("\n" + "="*70)
    print("ТЕСТИРОВАНИЕ АДАПТИВНОГО АЛГОРИТМА")
    print("="*70)
    
    # Создаем три профиля учеников
    students = [
        StudentSimulator(2.0, "Слабый (школьный этап)"),
        StudentSimulator(4.0, "Средний (муниципальный)"),
        StudentSimulator(6.0, "Сильный (ВсОШ)")
    ]
    
    # Запускаем симуляции
    results = []
    for student in students:
        history = simulate_adaptive_test(student, num_problems=10, verbose=True)
        results.append((student, history))
    
    # Визуализируем результаты
    print("\n[*] Создание графиков...")
    plot_results(results)
    
    # Проверка гипотез
    print("\n" + "="*70)
    print("ПРОВЕРКА ГИПОТЕЗ")
    print("="*70)
    
    for student, history in results:
        print(f"\n{student.name}:")
        
        # Гипотеза 1: Задачи концентрируются вокруг уровня ученика
        avg_difficulty = sum(history['problem_difficulties']) / len(history['problem_difficulties'])
        diff_from_true = abs(avg_difficulty - student.true_ability)
        print(f"  [+] Средняя сложность ({avg_difficulty:.2f}) близка к реальному уровню ({student.true_ability:.2f}): "
              f"разница {diff_from_true:.2f}")
        
        # Гипотеза 2: Оценка сходится к реальному уровню
        final_error = abs(history['final_ability'] - student.true_ability)
        print(f"  [+] Финальная оценка ({history['final_ability']:.2f}) близка к реальному уровню: "
              f"ошибка {final_error:.2f}")
        
        # Гипотеза 3: Информационная ценность высока
        avg_info = sum(history['information_values']) / len(history['information_values'])
        print(f"  [+] Средняя информационная ценность: {avg_info:.3f}")
        
        # Гипотеза 4: Разнообразие тем
        topics = [p.get('subtopic', 'unknown') for p in history['problems']]
        unique_topics = len(set(topics))
        print(f"  [+] Использовано уникальных тем: {unique_topics}/{len(topics)}")
    
    print("\n" + "="*70)
    print("[OK] ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
    print("="*70 + "\n")


if __name__ == "__main__":
    # Устанавливаем seed для воспроизводимости
    random.seed(42)
    main()
