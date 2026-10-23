"""
Умная проверка ответов через DeepSeek API.
Использует LLM для определения математической эквивалентности ответов.
"""

import os
import requests
from typing import Dict, List, Optional
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


def check_answer_with_llm(
    user_answer: str,
    correct_answer: str,
    question_text: Optional[str] = None
) -> Dict[str, any]:
    """
    Проверяет ответ ученика через DeepSeek API.
    
    Args:
        user_answer: Ответ ученика
        correct_answer: Правильный ответ из базы
        question_text: Текст задачи (опционально, для контекста)
    
    Returns:
        {
            'is_correct': bool,
            'comment': str,
            'confidence': float  # 0.0-1.0
        }
    """
    if not DEEPSEEK_API_KEY:
        # Fallback на простое сравнение
        from utils.math_answer_utils import compare_math_answers
        is_correct = compare_math_answers(user_answer, correct_answer)
        return {
            'is_correct': is_correct,
            'comment': 'Проверка без AI (ключ не настроен)',
            'confidence': 1.0 if is_correct else 0.0
        }
    
    # Формируем промпт для проверки
    context = f"\n\nТекст задачи: {question_text}" if question_text else ""
    
    user_prompt = f"""Правильный ответ: {correct_answer}
Ответ ученика: {user_answer}{context}

Определи, верен ли ответ ученика математически."""
    
    system_prompt = """Ты — строгий, но справедливый учитель математики (Smart Evaluator).
Твоя задача — сравнить ответ ученика с эталонным правильным ответом и определить, верный ли он математически.

ПРАВИЛА ОЦЕНИВАНИЯ:
1. Игнорируй регистр, лишние пробелы, опечатки в словах.
2. Игнорируй единицы измерения или пояснения, если само число верное (Эталон: "4". Ученик: "4 яблока", "4 км/ч" — это ВЕРНО).
3. Понимай алгебраическую эквивалентность (Эталон: "0.5". Ученик: "1/2" — это ВЕРНО).
4. Игнорируй вводные конструкции (Эталон: "4". Ученик: "x=4", "Ответ: 4", "я думаю что 4" — это ВЕРНО).
5. Понимай текст (Эталон: "4". Ученик: "четыре" — это ВЕРНО).
6. Если ответы содержат несколько чисел, порядок не важен (Эталон: "x=2, y=3". Ученик: "у=3; х=2" — это ВЕРНО).

ФОРМАТ ОТВЕТА:
Верни ТОЛЬКО валидный JSON без маркдауна и лишнего текста:
{
  "is_correct": true,
  "comment": "Короткий комментарий, почему ответ принят или отклонен"
}"""
    
    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1,  # Низкая температура для консистентности
                "max_tokens": 200
            },
            timeout=10
        )
        
        if response.status_code != 200:
            raise Exception(f"API error: {response.status_code}")
        
        content = response.json()["choices"][0]["message"]["content"]
        
        # Парсим JSON ответ
        import json
        import re
        
        # Убираем markdown
        content = content.strip()
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content)
        content = content.strip()
        
        result = json.loads(content)
        
        return {
            'is_correct': result.get('is_correct', False),
            'comment': result.get('comment', ''),
            'confidence': 0.95  # Высокая уверенность при использовании LLM
        }
        
    except Exception as e:
        print(f"[ERROR] LLM evaluation failed: {e}")
        # Fallback на простое сравнение
        from utils.math_answer_utils import compare_math_answers
        is_correct = compare_math_answers(user_answer, correct_answer)
        return {
            'is_correct': is_correct,
            'comment': f'Fallback проверка (ошибка AI: {str(e)})',
            'confidence': 0.7 if is_correct else 0.3
        }


def check_answers_batch(answers_data: List[Dict]) -> List[Dict]:
    """
    Проверяет несколько ответов одним батч-запросом к DeepSeek.
    
    Args:
        answers_data: Список словарей с ключами:
            - user_answer: str
            - correct_answer: str
            - question_text: str (опционально)
    
    Returns:
        Список результатов проверки
    """
    if not DEEPSEEK_API_KEY or not answers_data:
        # Fallback на простую проверку
        results = []
        from utils.math_answer_utils import compare_math_answers
        for data in answers_data:
            is_correct = compare_math_answers(
                data['user_answer'],
                data['correct_answer']
            )
            results.append({
                'is_correct': is_correct,
                'comment': 'Простая проверка (AI недоступен)',
                'confidence': 1.0 if is_correct else 0.0
            })
        return results
    
    # Формируем батч-промпт
    tasks_text = ""
    for i, data in enumerate(answers_data, 1):
        context = f" (Задача: {data.get('question_text', 'N/A')[:50]}...)" if data.get('question_text') else ""
        tasks_text += f"\n{i}. Эталон: '{data['correct_answer']}' | Ученик: '{data['user_answer']}'{context}"
    
    user_prompt = f"""Проверь {len(answers_data)} ответов:{tasks_text}

Для каждого ответа определи, верен ли он математически."""
    
    system_prompt = """Ты — учитель математики, проверяющий ответы учеников.

ПРАВИЛА: Игнорируй регистр, пробелы, единицы измерения, вводные слова. 
Понимай эквивалентность (0.5 = 1/2, x=4 = 4, четыре = 4).

ФОРМАТ: Верни JSON-массив:
[
  {"is_correct": true, "comment": "Верно"},
  {"is_correct": false, "comment": "Ошибка в вычислениях"}
]"""
    
    try:
        response = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 1000
            },
            timeout=30
        )
        
        content = response.json()["choices"][0]["message"]["content"]
        
        # Парсим JSON
        import json
        import re
        content = re.sub(r'```json\s*', '', content)
        content = re.sub(r'```\s*', '', content).strip()
        
        results = json.loads(content)
        
        # Добавляем confidence
        for r in results:
            r['confidence'] = 0.95
        
        return results
        
    except Exception as e:
        print(f"[ERROR] Batch LLM evaluation failed: {e}")
        # Fallback
        results = []
        from utils.math_answer_utils import compare_math_answers
        for data in answers_data:
            is_correct = compare_math_answers(
                data['user_answer'],
                data['correct_answer']
            )
            results.append({
                'is_correct': is_correct,
                'comment': f'Fallback (ошибка AI)',
                'confidence': 0.7 if is_correct else 0.3
            })
        return results
