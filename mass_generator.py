#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mass Task Generation System
Generates thousands of olympiad math tasks with graceful shutdown support.
"""

import signal
import sys
import time
import logging
from typing import Dict, List
from ai.deepseek_client import DeepSeekClient
from generators.safe_writer import SafeJSONWriter
from generators.grade_6_7_generator import Grade6_7Generator
from generators.grade_8_generator import Grade8Generator
from generators.grade_10_11_generator import Grade10_11Generator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MassTaskGenerator:
    """
    Главный контроллер массовой генерации.
    
    Управляет:
    - Контекстом генерации (передает последние 10 задач для уникальности)
    - Связью между генераторами и SafeJSONWriter
    - Graceful shutdown при SIGTERM/SIGINT
    """
    
    def __init__(self, config: Dict):
        """
        Args:
            config: Конфигурация генерации
        """
        self.config = config
        self.client = DeepSeekClient()
        self.writer = None
        self.generators = {}
        self.shutdown_requested = False
        
        # Инициализация генераторов для каждого класса
        logger.info("Initializing generators...")
        self.generators['6-7'] = Grade6_7Generator(self.client)
        self.generators['8'] = Grade8Generator(self.client)
        self.generators['10-11'] = Grade10_11Generator(self.client)
        
        # Регистрация обработчиков сигналов для graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        logger.info("MassTaskGenerator initialized")
        
    def _signal_handler(self, signum, frame):
        """
        Обработчик сигналов для graceful shutdown.
        Устанавливает флаг для корректного завершения генерации.
        """
        print(f"\n⚠️  Received signal {signum}. Initiating graceful shutdown...")
        logger.warning(f"Signal {signum} received, initiating shutdown")
        self.shutdown_requested = True
        
    def generate_all(self):
        """
        Главный цикл генерации.
        Генерирует задачи для всех классов с батч-записью.
        """
        output_file = self.config.get('output_file', 'generated_tasks.json')
        self.writer = SafeJSONWriter(output_file)
        self.writer.open()
        
        try:
            for grade_key, generator in self.generators.items():
                if self.shutdown_requested:
                    logger.warning(f"Shutdown requested. Stopping at grade {grade_key}")
                    print(f"⚠️  Shutdown requested. Stopping at grade {grade_key}")
                    break
                    
                print(f"\n{'='*60}")
                print(f"📚 Generating tasks for grade {grade_key}...")
                print(f"{'='*60}")
                self._generate_for_grade(generator, grade_key)
                
        finally:
            # Гарантированное закрытие файла (даже при исключениях)
            if self.writer:
                self.writer.close()
                
    def _generate_for_grade(self, generator, grade_key: str):
        """
        PRODUCTION MATRIX GENERATION
        Генерация задач для одного класса по строгой матрице покрытия.
        
        Математика базы:
        - 6 тем (topics)
        - 7 уровней сложности (1-7)
        - 12 уникальных задач на каждое пересечение
        - ИТОГО: 6 × 7 × 12 = 504 задачи на класс
        
        Args:
            generator: Экземпляр TaskGenerator
            grade_key: Ключ класса (например, '6-7', '8', '10-11')
        """
        # PRODUCTION TOPICS: 6 разделов
        topics = [
            "Алгебра",
            "Геометрия",
            "Комбинаторика",
            "Теория чисел",
            "Задачи на движение",
            "Логика/Нестандартные"
        ]
        
        # Добавляем подтемы для нового раздела, если их нет
        if "Логика/Нестандартные" not in generator.subtopics:
            generator.subtopics["Логика/Нестандартные"] = [
                "логические_задачи",
                "взвешивания",
                "переливания",
                "раскраски"
            ]
        
        generated_tasks = []
        total_task_count = 0
        topic_context = {}  # Контекст для каждой темы отдельно
        
        # СТРОГАЯ МАТРИЦА: 6 тем × 7 уровней × 12 задач
        for topic_idx, topic in enumerate(topics, 1):
            if self.shutdown_requested:
                logger.warning(f"Shutdown requested at topic {topic}")
                break
            
            topic_context[topic] = []  # Инициализация контекста для темы
            subtopics = generator.subtopics[topic]
            
            print(f"\n{'='*70}")
            print(f"📚 Grade {grade_key} → Topic {topic_idx}/6: {topic}")
            print(f"{'='*70}")
            
            # 7 уровней сложности (от базового до Всероса)
            for difficulty in range(1, 8):
                if self.shutdown_requested:
                    break
                
                difficulty_context_desc = generator.get_difficulty_context(difficulty)
                print(f"\n  🎯 Difficulty Level {difficulty}/7: {difficulty_context_desc[:60]}...")
                
                # 12 уникальных задач на это пересечение
                for task_num in range(1, 13):
                    if self.shutdown_requested:
                        break
                    
                    # Ротация подтем для вариативности
                    subtopic = subtopics[(task_num - 1) % len(subtopics)]
                    
                    # Генерация с контекстом последних 10 задач ЭТОЙ ЖЕ ТЕМЫ
                    # (для глубокой вариативности подтем, избегаем клонов)
                    task = generator.generate_task(
                        topic=topic,
                        subtopic=subtopic,
                        difficulty=difficulty,
                        previous_tasks=[t['text'][:150] for t in topic_context[topic][-10:]]
                    )
                    
                    if task:
                        # Метаданные для трассировки
                        task['grade'] = grade_key
                        task['topic'] = topic
                        task['subtopic'] = subtopic
                        task['difficulty'] = difficulty
                        task['id'] = f"{grade_key}_{topic_idx}_{difficulty}_{task_num:02d}"
                        
                        generated_tasks.append(task)
                        topic_context[topic].append(task)
                        total_task_count += 1
                        
                        # Батч-запись каждые 10 задач (SafeJSONWriter защита от OOM)
                        if len(generated_tasks) >= 10:
                            self.writer.write_batch(generated_tasks)
                            self.writer.flush()  # Принудительный flush для защиты
                            generated_tasks = []
                        
                        print(f"    ✅ Task {task_num}/12 | Total: {total_task_count}/504 | {topic}/{subtopic}")
                    else:
                        print(f"    ❌ FAILED Task {task_num}/12 (will retry via max_retries)")
                
                # Пауза между уровнями сложности (снижение нагрузки на API)
                if not self.shutdown_requested and difficulty < 7:
                    time.sleep(0.5)
            
            # Пауза между темами
            if not self.shutdown_requested and topic_idx < len(topics):
                print(f"\n  ⏸️  Cooldown 2s before next topic...")
                time.sleep(2)
        
        # Запись оставшихся задач
        if generated_tasks:
            self.writer.write_batch(generated_tasks)
            self.writer.flush()
        
        print(f"\n{'='*70}")
        print(f"✅ COMPLETED Grade {grade_key}: {total_task_count}/504 tasks generated")
        print(f"{'='*70}")


def main():
    """Точка входа для массовой генерации."""
    print("="*60)
    print("FORMYLA Mass Task Generation System")
    print("="*60)
    
    config = {
        'output_file': 'generated_tasks.json',
        'tasks_per_grade': 50,  # Для тестирования используем 50 задач
    }
    
    print(f"\nConfiguration:")
    print(f"  Output file: {config['output_file']}")
    print(f"  Tasks per grade: {config['tasks_per_grade']}")
    print(f"  Total expected: {config['tasks_per_grade'] * 3} tasks (3 grades)")
    print("="*60)
    
    generator = MassTaskGenerator(config)
    
    try:
        generator.generate_all()
        print("\n" + "="*60)
        print("🎉 Generation completed successfully!")
        print("="*60)
    except KeyboardInterrupt:
        print("\n⚠️  KeyboardInterrupt caught in main()")
        logger.warning("KeyboardInterrupt in main()")
    except Exception as e:
        print(f"\n❌ Error during generation: {e}")
        logger.error(f"Error during generation: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
