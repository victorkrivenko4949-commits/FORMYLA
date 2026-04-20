"""
Промышленный генератор полной базы задач (7350 задач)
Архитектура: XML-парсинг, Chain of Thought, асинхронность, retry-механизм
"""

import asyncio
import aiohttp
import json
import re
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('generation_full_db.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Константы
API_KEY = os.getenv('DEEPSEEK_API_KEY')
API_URL = 'https://api.deepseek.com/v1/chat/completions'
OUTPUT_FILE = 'data/adaptive_full_db.json'
MAX_CONCURRENT = 40
MAX_RETRIES = 5
INITIAL_RETRY_DELAY = 5

# Структура: 7 классов × 6 тем × 7 уровней × 25 шагов = 7350 задач
GRADES = [5, 6, 7, 8, 9, 10, 11]

# Темы для каждого класса (6 тем на класс)
TOPICS_BY_GRADE = {
    5: [
        "Натуральные числа и действия с ними",
        "Обыкновенные дроби",
        "Десятичные дроби",
        "Проценты",
        "Площади и объемы",
        "Уравнения и задачи"
    ],
    6: [
        "Делимость чисел",
        "Положительные и отрицательные числа",
        "Рациональные числа и действия с ними",
        "Отношения и пропорции",
        "Координаты на плоскости",
        "Линейные уравнения"
    ],
    7: [
        "Алгебраические выражения",
        "Линейные уравнения и системы",
        "Степени и одночлены",
        "Многочлены и формулы сокращенного умножения",
        "Функции и графики",
        "Геометрия: треугольники и параллельные прямые"
    ],
    8: [
        "Рациональные дроби",
        "Квадратные корни",
        "Квадратные уравнения",
        "Неравенства",
        "Степени с целым показателем",
        "Геометрия: четырехугольники и площади"
    ],
    9: [
        "Квадратичная функция",
        "Уравнения и неравенства с одной переменной",
        "Системы уравнений",
        "Арифметическая и геометрическая прогрессии",
        "Элементы комбинаторики и теории вероятностей",
        "Геометрия: окружность и векторы"
    ],
    10: [
        "Тригонометрия",
        "Производная и её применение",
        "Показательная и логарифмическая функции",
        "Стереометрия: параллельность и перпендикулярность",
        "Многогранники",
        "Комбинаторика и вероятность"
    ],
    11: [
        "Первообразная и интеграл",
        "Показательные и логарифмические уравнения",
        "Тела вращения",
        "Объемы тел",
        "Комплексные числа и уравнения",
        "Задачи на оптимизацию"
    ]
}

LEVELS = list(range(1, 8))  # 1-7
STEPS = list(range(1, 26))  # 1-25

# Системный промпт с Chain of Thought
SYSTEM_PROMPT = """Ты — эксперт-математик и методист высшей категории. Твоя цель — создать идеальную математическую задачу по заданным параметрам.

КРИТИЧЕСКИ ВАЖНО: Твой ответ СТРОГО должен состоять из четырех XML-тегов:

<draft>
Здесь ты пошагово:
1. АНАЛИЗ ТЕМЫ: Сначала проанализируй указанную тему и напиши, какие математические концепции в нее входят
2. ПРОВЕРКА СООТВЕТСТВИЯ: Убедись, что твоя задача СТРОГО соответствует этой теме (не используй концепции из других тем!)
3. СОЗДАНИЕ ЗАДАЧИ: Придумываешь задачу, используя ТОЛЬКО концепции из указанной темы
4. РЕШЕНИЕ: Решаешь её сам полностью
5. ПРОВЕРКА ВЫЧИСЛЕНИЙ: Проверяешь все вычисления
6. ФИНАЛЬНАЯ ПРОВЕРКА: Убеждаешься, что ответ получается красивым и логичным, и задача соответствует указанному шагу прогрессии сложности

КРИТИЧЕСКИ ВАЖНО - СООТВЕТСТВИЕ ТЕМЕ:
- Твоя задача ДОЛЖНА СТРОГО соответствовать указанной теме
- Если тема "Комбинаторика и вероятность", задача должна быть на факториалы, перестановки, сочетания, размещения или вероятность
- Если тема "Квадратные уравнения", задача должна быть на решение квадратных уравнений, дискриминант, теорему Виета
- Если тема "Тригонометрия", задача должна быть на синусы, косинусы, тангенсы, тригонометрические формулы
- ЗАПРЕЩЕНО использовать функции, геометрию или уравнения, если они не относятся к указанной теме напрямую
- ЗАПРЕЩЕНО смешивать темы (например, делать задачу на функции, когда тема "Комбинаторика")
</draft>

<question>
Итоговый текст задачи. Безупречный русский язык. 
Все математические формулы СТРОГО оборачивай в LaTeX:
- Строчные формулы: \\( ... \\)
- Блочные формулы: \\[ ... \\]
Используй ОДИНАРНЫЕ слеши (например: \\frac{1}{2}, \\sqrt{x}, \\cdot)
</question>

<answer>
Только сам ответ (например: 42, \\frac{1}{2}, x=5, или несколько значений через запятую).
Используй LaTeX для математических выражений с ОДИНАРНЫМИ слешами.
</answer>

<explanation>
Подробное, понятное решение шаг за шагом.
Используй LaTeX для всех формул с ОДИНАРНЫМИ слешами.
Объясни каждый шаг так, чтобы ученик понял логику решения.
</explanation>

УРОВНИ СЛОЖНОСТИ:
1 - Одно простое действие (например: вычислить 5 + 3)
2 - Два-три действия (например: решить простое уравнение)
3 - Несколько действий, базовые формулы
4 - Средняя сложность, применение нескольких правил
5 - Сложная задача, требующая анализа
6 - Очень сложная задача, нестандартный подход
7 - Олимпиадный уровень, творческое мышление

ВАЖНО: Шаг (step) от 1 до 25 означает постепенное усложнение внутри уровня. Шаг 1 - самый простой вариант уровня, шаг 25 - самый сложный вариант этого же уровня."""


class TaskGenerator:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self.session: Optional[aiohttp.ClientSession] = None
        self.generated_count = 0
        self.failed_count = 0
        self.existing_tasks: Dict[str, dict] = {}
        self.total_tasks = len(GRADES) * 6 * len(LEVELS) * len(STEPS)
        
    def load_existing_tasks(self):
        """Загрузка существующих задач из файла"""
        if os.path.exists(OUTPUT_FILE):
            try:
                with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for task in data:
                        key = self._make_key(
                            task['grade'],
                            task['topic'],
                            task['level'],
                            task['step']
                        )
                        self.existing_tasks[key] = task
                logger.info(f"Загружено {len(self.existing_tasks)} существующих задач")
            except Exception as e:
                logger.error(f"Ошибка загрузки существующих задач: {e}")
        else:
            logger.info("Файл БД не найден, начинаем с нуля")
    
    def _make_key(self, grade: int, topic: str, level: int, step: int) -> str:
        """Создание уникального ключа для задачи"""
        return f"{grade}_{topic}_{level}_{step}"
    
    def save_progress(self):
        """Сохранение прогресса в файл"""
        try:
            os.makedirs('data', exist_ok=True)
            tasks_list = list(self.existing_tasks.values())
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(tasks_list, f, ensure_ascii=False, indent=2)
            logger.info(f"Прогресс сохранен: {len(tasks_list)} задач")
        except Exception as e:
            logger.error(f"Ошибка сохранения прогресса: {e}")
    
    async def create_session(self):
        """Создание HTTP сессии"""
        timeout = aiohttp.ClientTimeout(total=120)
        self.session = aiohttp.ClientSession(timeout=timeout)
    
    async def close_session(self):
        """Закрытие HTTP сессии"""
        if self.session:
            await self.session.close()
    
    def parse_xml_response(self, text: str) -> Optional[Dict[str, str]]:
        """Парсинг XML-тегов из ответа ИИ"""
        try:
            # Извлекаем содержимое тегов (draft игнорируем)
            question_match = re.search(r'<question>(.*?)</question>', text, re.DOTALL)
            answer_match = re.search(r'<answer>(.*?)</answer>', text, re.DOTALL)
            explanation_match = re.search(r'<explanation>(.*?)</explanation>', text, re.DOTALL)
            
            if not (question_match and answer_match and explanation_match):
                logger.error("Не все обязательные теги найдены в ответе")
                return None
            
            return {
                'question': question_match.group(1).strip(),
                'answer': answer_match.group(1).strip(),
                'explanation': explanation_match.group(1).strip()
            }
        except Exception as e:
            logger.error(f"Ошибка парсинга XML: {e}")
            return None
    
    async def generate_task_with_retry(
        self,
        grade: int,
        topic: str,
        level: int,
        step: int
    ) -> Optional[dict]:
        """Генерация одной задачи с механизмом retry"""
        
        user_prompt = f"""Создай задачу со следующими параметрами:
- Класс: {grade}
- Тема: {topic}
- Уровень сложности: {level}
- Шаг: {step}

КРИТИЧЕСКИ ВАЖНО: Задача ДОЛЖНА СТРОГО соответствовать теме "{topic}".
В теге <draft> ОБЯЗАТЕЛЬНО сначала проанализируй, какие математические концепции входят в тему "{topic}", и только потом создавай задачу СТРОГО по этим концепциям.

Помни: ответ должен содержать ВСЕ четыре XML-тега: <draft>, <question>, <answer>, <explanation>"""
        
        for attempt in range(MAX_RETRIES):
            try:
                async with self.semaphore:
                    async with self.session.post(
                        API_URL,
                        headers={
                            'Authorization': f'Bearer {API_KEY}',
                            'Content-Type': 'application/json'
                        },
                        json={
                            'model': 'deepseek-chat',
                            'messages': [
                                {'role': 'system', 'content': SYSTEM_PROMPT},
                                {'role': 'user', 'content': user_prompt}
                            ],
                            'temperature': 0.7,
                            'max_tokens': 2000
                        }
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            content = data['choices'][0]['message']['content']
                            
                            # Парсим XML
                            parsed = self.parse_xml_response(content)
                            if parsed:
                                task = {
                                    'grade': grade,
                                    'topic': topic,
                                    'level': level,
                                    'step': step,
                                    'question': parsed['question'],
                                    'answer': parsed['answer'],
                                    'explanation': parsed['explanation'],
                                    'generated_at': datetime.utcnow().isoformat()
                                }
                                return task
                            else:
                                logger.warning(f"Не удалось распарсить ответ для {grade}/{topic}/{level}/{step}")
                                
                        elif response.status == 429:
                            delay = INITIAL_RETRY_DELAY * (2 ** attempt)
                            logger.warning(f"Rate limit, ожидание {delay}с (попытка {attempt + 1}/{MAX_RETRIES})")
                            await asyncio.sleep(delay)
                            
                        elif response.status in [502, 503]:
                            delay = INITIAL_RETRY_DELAY * (2 ** attempt)
                            logger.warning(f"Ошибка сервера {response.status}, ожидание {delay}с")
                            await asyncio.sleep(delay)
                            
                        else:
                            error_text = await response.text()
                            logger.error(f"HTTP {response.status}: {error_text}")
                            
            except asyncio.TimeoutError:
                delay = INITIAL_RETRY_DELAY * (2 ** attempt)
                logger.warning(f"Timeout, повтор через {delay}с (попытка {attempt + 1}/{MAX_RETRIES})")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"Ошибка генерации задачи: {e}")
                await asyncio.sleep(INITIAL_RETRY_DELAY)
        
        return None
    
    async def generate_task_wrapper(
        self,
        grade: int,
        topic: str,
        level: int,
        step: int
    ):
        """Обертка для генерации с проверкой существования"""
        key = self._make_key(grade, topic, level, step)
        
        # Пропускаем, если уже есть
        if key in self.existing_tasks:
            return
        
        task = await self.generate_task_with_retry(grade, topic, level, step)
        
        if task:
            self.existing_tasks[key] = task
            self.generated_count += 1
            
            # Сохраняем каждые 50 задач
            if self.generated_count % 50 == 0:
                self.save_progress()
                
            logger.info(
                f"✓ Успешно: {len(self.existing_tasks)} / {self.total_tasks} | "
                f"Класс {grade}, Уровень {level}, Шаг {step}"
            )
        else:
            self.failed_count += 1
            logger.error(
                f"✗ Не удалось сгенерировать: {grade}/{topic}/{level}/{step} | "
                f"Неудач: {self.failed_count}"
            )
    
    async def generate_all(self):
        """Генерация всех 7350 задач"""
        logger.info("=" * 80)
        logger.info("ЗАПУСК ГЕНЕРАТОРА ПОЛНОЙ БАЗЫ ДАННЫХ")
        logger.info(f"Всего задач к генерации: {self.total_tasks}")
        logger.info(f"Максимум одновременных запросов: {MAX_CONCURRENT}")
        logger.info("=" * 80)
        
        # Загружаем существующие задачи
        self.load_existing_tasks()
        
        # Создаем сессию
        await self.create_session()
        
        try:
            # Создаем список всех задач для генерации
            tasks = []
            for grade in GRADES:
                topics = TOPICS_BY_GRADE[grade]
                for topic in topics:
                    for level in LEVELS:
                        for step in STEPS:
                            tasks.append(
                                self.generate_task_wrapper(grade, topic, level, step)
                            )
            
            # Запускаем все задачи асинхронно
            await asyncio.gather(*tasks)
            
            # Финальное сохранение
            self.save_progress()
            
            logger.info("=" * 80)
            logger.info("ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
            logger.info(f"Всего задач в БД: {len(self.existing_tasks)}")
            logger.info(f"Сгенерировано в этом запуске: {self.generated_count}")
            logger.info(f"Неудачных попыток: {self.failed_count}")
            logger.info(f"Файл сохранен: {OUTPUT_FILE}")
            logger.info("=" * 80)
            
        finally:
            await self.close_session()


async def main():
    """Главная функция"""
    if not API_KEY:
        logger.error("ОШИБКА: Не установлена переменная окружения DEEPSEEK_API_KEY")
        return
    
    generator = TaskGenerator()
    await generator.generate_all()


if __name__ == '__main__':
    asyncio.run(main())
