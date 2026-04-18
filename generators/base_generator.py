#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TaskGenerator - Abstract Base Class for Task Generation
Provides retry logic, exponential backoff, and unified interface.
"""

import json
import time
import logging
import sys
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

# Add utils to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.math_formatter import format_task_math

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TaskGenerator(ABC):
    """
    Абстрактный базовый класс для генерации задач.
    Обеспечивает защиту от бесконечных циклов и единый интерфейс.
    """
    
    def __init__(self, deepseek_client, grade_range: tuple, max_retries: int = 3):
        """
        Args:
            deepseek_client: Экземпляр DeepSeekClient
            grade_range: Кортеж (min_grade, max_grade)
            max_retries: Максимальное количество попыток генерации (защита от зависаний)
        """
        self.client = deepseek_client
        self.grade_range = grade_range
        self.max_retries = max_retries
        self.generated_count = 0
        
        # Определение подтем для каждой основной темы
        self.subtopics = {
            "Алгебра": [
                "текстовые_задачи",
                "степени_и_корни",
                "последовательности",
                "системы_уравнений"
            ],
            "Геометрия": [
                "площади_фигур",
                "разрезания",
                "свойства_углов",
                "координаты"
            ],
            "Комбинаторика": [
                "графы",
                "принцип_дирихле",
                "подсчет_вариантов",
                "игры_и_стратегии"
            ],
            "Теория чисел": [
                "делимость",
                "остатки",
                "НОД_НОК",
                "диофантовы_уравнения"
            ],
            "Задачи на движение": [
                "навстречу_вдогонку",
                "движение_по_кругу",
                "по_течению",
                "средняя_скорость"
            ]
        }
        
        logger.info(f"TaskGenerator initialized for grades {grade_range[0]}-{grade_range[1]}")
    
    @staticmethod
    def get_difficulty_context(level: int) -> str:
        """
        Возвращает детальное текстовое описание уровня сложности для LLM.
        Критически важно для правильной интерпретации DeepSeek.
        
        Args:
            level: Уровень сложности (1-7)
            
        Returns:
            Строка с подробным описанием уровня сложности
        """
        contexts = {
            1: "БАЗОВЫЙ УРОВЕНЬ (Школьная программа). Задача решается в 1-2 простых логических шага. Идея лежит на поверхности.",
            2: "ЛЕГКИЙ УРОВЕНЬ. Требуется сделать 2-3 вывода. Уровень обычной школьной пятерки с небольшим подвохом.",
            3: "СРЕДНИЙ УРОВЕНЬ (Школьный этап олимпиады). Решение в 3-4 шага, возможно наличие одной логической ловушки.",
            4: "ПОВЫШЕННЫЙ УРОВЕНЬ (Муниципальный этап). Комбинирование двух тем или использование стандартных олимпиадных приемов (например, принцип Дирихле).",
            5: "СЛОЖНЫЙ УРОВЕНЬ (Региональный этап). Многоходовое решение, требующее глубокого понимания темы (сложные системы уравнений, свойства делимости).",
            6: "ОЧЕНЬ СЛОЖНЫЙ УРОВЕНЬ (Перечневые олимпиады 2 уровня). Сложный анализ, малоизвестные теоремы, построение математической модели.",
            7: "МАКСИМАЛЬНАЯ СЛОЖНОСТЬ (Заключительный этап Всероса). Экстремально сложная задача (хардкор). Искусственный синтез нескольких концепций (например, геометрия масс + графы) или сложная индукция. Решение требует гениальной догадки."
        }
        return contexts.get(level, contexts[1])
    
    @abstractmethod
    def get_allowed_concepts(self) -> List[str]:
        """Возвращает список разрешенных математических концепций для данного класса."""
        pass
    
    @abstractmethod
    def get_forbidden_concepts(self) -> List[str]:
        """Возвращает список запрещенных концепций для данного класса."""
        pass
    
    def generate_task(
        self,
        topic: str,
        subtopic: str,
        difficulty: int,
        previous_tasks: List[str]
    ) -> Optional[Dict]:
        """
        Генерирует одну задачу с защитой от бесконечных циклов.
        
        Args:
            topic: Основная тема (Алгебра, Геометрия и т.д.)
            subtopic: Подтема из self.subtopics[topic]
            difficulty: Уровень сложности (1-5)
            previous_tasks: Список предыдущих задач для избежания повторений
            
        Returns:
            Dict с полями: text, answer, solution, difficulty, topic, subtopic
            или None при неудаче после всех попыток
        """
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                logger.info(f"Generating task: {topic}/{subtopic}, difficulty={difficulty}, attempt={retry_count+1}/{self.max_retries}")
                
                # Формирование промпта с учетом возрастных ограничений
                prompt = self._build_prompt(
                    topic, subtopic, difficulty, previous_tasks
                )
                
                # Вызов AI с таймаутом (таймаут уже встроен в DeepSeekClient)
                response = self.client.generate(
                    prompt=prompt,
                    system_prompt=self._get_system_prompt(),
                    temperature=0.7,
                    max_tokens=2000
                )
                
                # Парсинг и валидация
                task = self._parse_and_validate(response)
                
                if task:
                    # Автоматическое форматирование математики в LaTeX
                    task = format_task_math(task)
                    
                    self.generated_count += 1
                    logger.info(f"✅ Task generated successfully (total: {self.generated_count})")
                    return task
                else:
                    logger.warning(f"Task validation failed, retrying...")
                    
            except Exception as e:
                logger.warning(f"Retry {retry_count + 1}/{self.max_retries}: {e}")
            
            # Exponential backoff
            retry_count += 1
            if retry_count < self.max_retries:
                wait_time = 2 ** retry_count
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
        
        logger.error(f"❌ Failed to generate task after {self.max_retries} retries")
        return None
    
    @abstractmethod
    def _build_prompt(self, topic: str, subtopic: str, difficulty: int, previous_tasks: List[str]) -> str:
        """Строит промпт с учетом специфики класса."""
        pass
    
    @abstractmethod
    def _get_system_prompt(self) -> str:
        """Возвращает системный промпт с ограничениями для класса."""
        pass
    
    def _parse_and_validate(self, response: str) -> Optional[Dict]:
        """
        Парсит JSON и валидирует структуру.
        
        Args:
            response: Ответ от AI
            
        Returns:
            Dict с задачей или None при ошибке
        """
        try:
            # Очистка от markdown
            response = response.strip()
            if response.startswith('```json'):
                response = response[7:]
            elif response.startswith('```'):
                response = response[3:]
            if response.endswith('```'):
                response = response[:-3]
            response = response.strip()
            
            # Парсинг JSON
            task = json.loads(response)
            
            # Валидация обязательных полей
            required_fields = ['text', 'answer', 'solution', 'difficulty', 'topic']
            if all(field in task for field in required_fields):
                # Дополнительная валидация: проверка на пустые значения
                if all(str(task[field]).strip() for field in required_fields):
                    return task
                else:
                    logger.warning(f"Empty values in task fields")
                    return None
            else:
                missing = [f for f in required_fields if f not in task]
                logger.warning(f"Missing required fields in task: {missing}")
                return None
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")
            return None
        except Exception as e:
            logger.warning(f"Validation error: {e}")
            return None
