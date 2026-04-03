#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DeepSeek API Client with Exponential Backoff and Retry Logic
Provides reliable communication with DeepSeek API for content generation.
"""

import os
import sys
import time
import json
import logging
import requests
from typing import Optional, Dict, Any

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DeepSeekAPIError(Exception):
    """Custom exception for DeepSeek API errors."""
    pass


class DeepSeekClient:
    """
    Client for DeepSeek API with automatic retry and exponential backoff.
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize DeepSeek client.
        
        Args:
            api_key: DeepSeek API key. If None, reads from DEEPSEEK_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get('DEEPSEEK_API_KEY')
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not provided and not found in environment")
        
        self.base_url = "https://api.deepseek.com/v1/chat/completions"
        self.max_retries = 5
        self.base_delay = 2  # seconds
        self.timeout = 60  # seconds
        
    def generate(
        self, 
        prompt: str, 
        system_prompt: str = "", 
        temperature: float = 0.3,
        max_tokens: int = 2000
    ) -> str:
        """
        Generate text using DeepSeek API with retry logic.
        
        Args:
            prompt: User prompt
            system_prompt: System prompt (optional)
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens to generate
            
        Returns:
            Generated text
            
        Raises:
            DeepSeekAPIError: If all retries failed
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": "deepseek-chat",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Attempt {attempt + 1}/{self.max_retries}: Sending request to DeepSeek API")
                
                response = requests.post(
                    self.base_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                # Check HTTP status
                if response.status_code == 200:
                    data = response.json()
                    
                    # Validate response structure
                    if 'choices' in data and len(data['choices']) > 0:
                        content = data['choices'][0].get('message', {}).get('content')
                        if content:
                            logger.info("✓ Request successful")
                            return content
                        else:
                            logger.warning("Response missing content field")
                            raise ValueError("Invalid response structure")
                    else:
                        logger.warning("Response missing choices field")
                        raise ValueError("Invalid response structure")
                
                elif response.status_code == 429:
                    # Rate limit - wait longer
                    wait_time = 60
                    logger.warning(f"Rate limit (429). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                elif response.status_code in [500, 502, 503, 504]:
                    # Server error - retry with backoff
                    wait_time = self.base_delay * (2 ** attempt)
                    logger.warning(f"Server error ({response.status_code}). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                
                elif response.status_code == 401:
                    # Authentication error - no retry
                    logger.error("Authentication failed (401). Check API key.")
                    raise DeepSeekAPIError(f"Authentication failed: {response.text}")
                
                else:
                    # Other error
                    logger.error(f"HTTP {response.status_code}: {response.text}")
                    raise DeepSeekAPIError(f"HTTP {response.status_code}: {response.text}")
                    
            except requests.exceptions.Timeout:
                wait_time = self.base_delay * (2 ** attempt)
                logger.warning(f"Timeout. Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                
            except requests.exceptions.ConnectionError as e:
                wait_time = self.base_delay * (2 ** attempt)
                logger.warning(f"Connection error: {e}. Waiting {wait_time}s...")
                time.sleep(wait_time)
                
            except ValueError as e:
                # Invalid JSON or structure
                wait_time = self.base_delay * (2 ** attempt)
                logger.warning(f"Invalid response: {e}. Waiting {wait_time}s...")
                time.sleep(wait_time)
        
        # All retries exhausted
        logger.error(f"All {self.max_retries} retries exhausted")
        raise DeepSeekAPIError(f"Failed after {self.max_retries} attempts")
    
    def analyze_user_background(self, user_text: str) -> Dict[str, Any]:
        """
        Анализирует математический опыт пользователя и дает рекомендации.
        
        Args:
            user_text: Текст пользователя о его математическом опыте
            
        Returns:
            Dict с ключами:
                - level: str (beginner, intermediate, advanced)
                - report: str (персональный отчет для пользователя)
                - recommended_topics: list (рекомендуемые темы)
                
        Raises:
            DeepSeekAPIError: If analysis failed
        """
        system_prompt = """Ты — профессиональный тренер по олимпиадной математике.
Твоя задача — проанализировать опыт нового ученика и дать ему персональные рекомендации.

Верни ответ СТРОГО в виде валидного JSON без markdown форматирования:
{
  "level": "beginner|intermediate|advanced",
  "report": "Персональный мотивирующий ответ на 2-3 абзаца",
  "recommended_topics": ["algebra", "geometry", ...]
}

Доступные темы: algebra, geometry, combinatorics, number_theory, movement, knights_liars

Уровни:
- beginner: новичок, мало опыта с олимпиадами
- intermediate: есть опыт, участвовал в олимпиадах
- advanced: сильный уровень, призер олимпиад"""

        user_prompt = f"""Новый ученик рассказывает о своем опыте:

"{user_text}"

Проанализируй его текст и дай персональные рекомендации."""

        try:
            response = self.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=1000
            )
            
            # Очистка от markdown
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            # Парсинг JSON
            result = json.loads(response)
            
            # Валидация
            if 'level' not in result or 'report' not in result or 'recommended_topics' not in result:
                raise ValueError("Missing required fields in AI response")
            
            if result['level'] not in ['beginner', 'intermediate', 'advanced']:
                result['level'] = 'intermediate'  # default
            
            logger.info(f"User background analyzed: level={result['level']}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response: {e}")
            # Возвращаем дефолтный ответ
            return {
                'level': 'intermediate',
                'report': 'Спасибо за ваш рассказ! Мы подберем для вас подходящие задачи.',
                'recommended_topics': ['algebra', 'geometry']
            }
        except Exception as e:
            logger.error(f"Error analyzing user background: {e}")
            raise DeepSeekAPIError(f"Failed to analyze user background: {e}")
    
    def chat_with_tutor(self, user, new_message: str, chat_history: list) -> str:
        """
        Чат с персональным AI-тьютором.
        
        Args:
            user: объект User с профилем
            new_message: новое сообщение от пользователя
            chat_history: список последних сообщений [{role, content}, ...]
            
        Returns:
            str: ответ тьютора
        """
        # Формируем системный промпт с учетом профиля
        system_prompt = f"""Ты — личный ИИ-репетитор по математике на платформе FORMYLA.

Твой ученик: {user.email}
Уровень: {user.math_level or 'не определен'}
Твои заметки: {user.ai_report or 'Новый ученик'}

Твоя задача:
- Помогать с олимпиадными задачами
- Давать НАВОДЯЩИЕ вопросы, а не прямые ответы
- Хвалить за успехи
- Мотивировать продолжать

ВАЖНО: НИКОГДА не давай прямой числовой ответ сразу. Задавай вопросы, чтобы ученик сам дошел до решения."""

        # Формируем историю для контекста
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # Добавляем последние 20 сообщений из истории
        for msg in chat_history[-20:]:
            messages.append({
                "role": msg.get('role', 'user'),
                "content": msg.get('content', '')
            })
        
        # Добавляем новое сообщение
        messages.append({"role": "user", "content": new_message})
        
        print(f">>> Messages count: {len(messages)}", flush=True)
        logger.info(f"Sending {len(messages)} messages to DeepSeek (including system prompt)")
        
        try:
            # Отправляем всю историю в DeepSeek
            payload = {
                "model": "deepseek-chat",
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 500
            }
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                self.base_url,
                headers=headers,
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    content = data['choices'][0]['message']['content']
                    logger.info(f"Tutor response generated for user {user.id}")
                    return content
            
            raise DeepSeekAPIError(f"API error: {response.status_code}")
            
            logger.info(f"Tutor response generated for user {user.id}")
            return response
            
        except Exception as e:
            logger.error(f"Error in tutor chat: {e}")
            return "Извините, возникла ошибка. Попробуйте еще раз!"
    
    def grade_exam(self, exam_tasks: list) -> Dict[str, Any]:
        """
        Проверка пробника через AI.
        
        Args:
            exam_tasks: список задач с ответами пользователя
            
        Returns:
            Dict с оценками и комментариями
        """
        # Формируем промпт
        tasks_text = ""
        for i, task in enumerate(exam_tasks, 1):
            tasks_text += f"\n\n=== Задача {i} ===\n"
            tasks_text += f"Условие: {task['text']}\n"
            tasks_text += f"Правильный ответ: {task['correct_answer']}\n"
            tasks_text += f"Правильное решение: {task['correct_solution']}\n"
            tasks_text += f"Ответ ученика: {task['user_answer']}\n"
            tasks_text += f"Решение ученика: {task['user_solution']}\n"
        
        system_prompt = """Ты — эксперт по проверке олимпиадных работ по математике.

Проверь решения ученика и верни JSON:
{
  "tasks": [
    {
      "task_number": 1,
      "is_correct": true/false,
      "comment": "Комментарий к решению"
    },
    ...
  ],
  "overall_feedback": "Общий анализ и рекомендации",
  "score": 85
}

Оценивай строго но справедливо. Хвали за правильные решения."""

        try:
            response = self.generate(
                prompt=f"Проверь решения:{tasks_text}",
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=2000
            )
            
            # Парсинг
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            
            result = json.loads(response.strip())
            return result
            
        except Exception as e:
            logger.error(f"Error grading exam: {e}")
            # Fallback
            return {
                'tasks': [{'task_number': i+1, 'is_correct': False, 'comment': 'Ошибка проверки'} for i in range(len(exam_tasks))],
                'overall_feedback': 'Не удалось проверить работу',
                'score': 0
            }


class CheckpointManager:
    """
    Manager for saving and loading generation progress.
    """
    
    def __init__(self, checkpoint_file: str = "checkpoint.json"):
        """
        Initialize checkpoint manager.
        
        Args:
            checkpoint_file: Path to checkpoint file
        """
        self.checkpoint_file = checkpoint_file
        
    def load(self) -> Dict[str, Any]:
        """
        Load checkpoint data from file.
        
        Returns:
            Checkpoint data dict or empty dict if file doesn't exist
        """
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Loaded checkpoint: {len(data.get('processed', []))} items processed")
                    return data
            except Exception as e:
                logger.error(f"Failed to load checkpoint: {e}")
                return {}
        return {}
    
    def save(self, data: Dict[str, Any]):
        """
        Save checkpoint data to file.
        
        Args:
            data: Checkpoint data to save
        """
        try:
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Checkpoint saved: {len(data.get('processed', []))} items")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            raise
    
    def clear(self):
        """Remove checkpoint file."""
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
            logger.info("Checkpoint cleared")


# Test block
if __name__ == '__main__':
    print("=" * 60)
    print("DeepSeek Client Test")
    print("=" * 60)
    
    # Test with invalid API key to demonstrate retry logic
    print("\n[TEST 1] Testing with INVALID API key (should fail after retries)...")
    try:
        client = DeepSeekClient(api_key="invalid_key_for_testing")
        result = client.generate("Сколько будет 2+2?")
        print(f"Result: {result}")
    except DeepSeekAPIError as e:
        print(f"\n[OK] Expected error caught: {e}")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
    
    print("\n" + "=" * 60)
    print("\n[TEST 2] Testing CheckpointManager...")
    
    # Test checkpoint manager
    checkpoint = CheckpointManager("test_checkpoint.json")
    
    # Save test data
    test_data = {
        'processed': [1, 2, 3, 4, 5],
        'last_id': 5,
        'timestamp': time.time()
    }
    checkpoint.save(test_data)
    print("[OK] Checkpoint saved")
    
    # Load test data
    loaded = checkpoint.load()
    print(f"[OK] Checkpoint loaded: {loaded}")
    
    # Clear
    checkpoint.clear()
    print("[OK] Checkpoint cleared")
    
    print("\n" + "=" * 60)
    print("Tests complete!")
    print("=" * 60)
