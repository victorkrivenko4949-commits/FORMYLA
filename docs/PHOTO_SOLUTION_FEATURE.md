# Функция загрузки фото решения с Vision API

## 📋 Обзор

Добавление возможности прикреплять фото черновика решения для анализа с помощью Vision AI.

## 🎯 Цели

1. Ученики могут загружать фото своих решений
2. Vision AI анализирует ход решения на фото
3. Система засчитывает правильные решения даже при опечатках в текстовом ответе
4. Адаптивный алгоритм учитывает результаты анализа фото

## ⚠️ Важное ограничение

**DeepSeek пока не поддерживает Vision API** (анализ изображений).

Альтернативы:
- OpenAI GPT-4 Vision (платно, $0.01-0.03 за изображение)
- Anthropic Claude 3 Vision (платно)
- Google Gemini Vision (бесплатный tier)
- Локальные модели (LLaVA, BLIP-2)

## 📝 План реализации

### Этап 1: Frontend (HTML/JS)

#### 1.1 Обновить `templates/adaptive_test.html`

```html
<!-- Добавить после поля ввода ответа -->
<div style="margin-bottom: 20px;">
    <label style="display: block; color: var(--text-soft); margin-bottom: 10px; font-weight: 500;">
        📷 Фото решения (опционально):
    </label>
    
    <input type="file" id="photoInput" accept="image/*" capture="environment" 
           style="display: none;" onchange="handlePhotoUpload(event)">
    
    <button onclick="document.getElementById('photoInput').click()" type="button"
            style="padding: 12px 24px; background: rgba(56, 189, 248, 0.1); color: var(--accent-2); border: 2px dashed var(--accent-2); border-radius: var(--radius-sm); cursor: pointer; font-weight: 600;">
        📎 Прикрепить фото черновика
    </button>
    
    <div id="photoPreview" style="margin-top: 15px; display: none;">
        <img id="previewImage" style="max-width: 200px; border-radius: var(--radius-sm); border: 2px solid var(--accent-2);">
        <button onclick="removePhoto()" type="button" style="margin-left: 10px; padding: 8px 16px; background: #ef4444; color: white; border: none; border-radius: 6px; cursor: pointer;">
            ✕ Удалить
        </button>
    </div>
</div>
```

#### 1.2 JavaScript функции

```javascript
let uploadedPhotoBase64 = null;

function handlePhotoUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    // Проверка размера (макс 5MB)
    if (file.size > 5 * 1024 * 1024) {
        alert('Файл слишком большой. Максимум 5MB');
        return;
    }
    
    // Конвертация в Base64
    const reader = new FileReader();
    reader.onload = function(e) {
        uploadedPhotoBase64 = e.target.result;
        
        // Показываем превью
        document.getElementById('previewImage').src = uploadedPhotoBase64;
        document.getElementById('photoPreview').style.display = 'block';
    };
    reader.readAsDataURL(file);
}

function removePhoto() {
    uploadedPhotoBase64 = null;
    document.getElementById('photoInput').value = '';
    document.getElementById('photoPreview').style.display = 'none';
}

// Обновить функцию submitAnswer
async function submitAnswer(problemId) {
    const answer = document.getElementById('userAnswer').value.trim();
    const solution = document.getElementById('userSolution').value.trim();
    
    if (!answer && !uploadedPhotoBase64) {
        alert('Введите ответ или прикрепите фото решения');
        return;
    }
    
    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    btn.textContent = 'Проверка...';
    
    try {
        const response = await fetch(`/api/adaptive-test/${testId}/submit`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                problem_id: problemId,
                answer: answer,
                solution: solution,
                photo_base64: uploadedPhotoBase64  // Отправляем фото
            })
        });
        
        // ... остальной код
        
        // Очищаем фото после отправки
        removePhoto();
        
    } catch (error) {
        // ... обработка ошибок
    }
}
```

### Этап 2: Backend (Python)

#### 2.1 Обновить модель `AdaptiveTestProblem` в `models.py`

```python
class AdaptiveTestProblem(db.Model):
    # ... существующие поля
    
    # Добавить новые поля
    photo_solution_url = db.Column(db.String(500))  # URL сохраненного фото
    vision_analysis = db.Column(db.Text)  # Результат анализа Vision AI
    vision_verdict = db.Column(db.String(20))  # CORRECT / WRONG / PARTIAL
```

#### 2.2 Создать сервис для Vision API

`services/vision_analyzer.py`:

```python
import base64
import requests
from typing import Dict, Optional

class VisionAnalyzer:
    """Анализ фото решений с помощью Vision AI"""
    
    def __init__(self, api_key: str, provider: str = 'openai'):
        self.api_key = api_key
        self.provider = provider
    
    def analyze_solution_photo(
        self, 
        problem_text: str, 
        correct_answer: str,
        photo_base64: str
    ) -> Dict[str, str]:
        """
        Анализирует фото решения задачи.
        
        Returns:
            {
                'verdict': 'CORRECT' | 'WRONG' | 'PARTIAL',
                'analysis': 'Текстовый анализ хода решения',
                'confidence': 0.0-1.0
            }
        """
        
        if self.provider == 'openai':
            return self._analyze_with_gpt4_vision(problem_text, correct_answer, photo_base64)
        elif self.provider == 'gemini':
            return self._analyze_with_gemini(problem_text, correct_answer, photo_base64)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")
    
    def _analyze_with_gpt4_vision(self, problem_text, correct_answer, photo_base64):
        """Анализ через GPT-4 Vision"""
        
        prompt = f"""Ты эксперт по олимпиадной математике. Проанализируй фото черновика решения.

УСЛОВИЕ ЗАДАЧИ:
{problem_text}

ПРАВИЛЬНЫЙ ОТВЕТ: {correct_answer}

ЗАДАНИЕ:
1. Изучи ход решения на фото
2. Оцени логику и правильность рассуждений
3. Верни вердикт:
   - CORRECT: если логика верная и ответ правильный
   - PARTIAL: если логика верная, но есть арифметическая ошибка
   - WRONG: если логика неверная

Формат ответа:
VERDICT: [CORRECT/PARTIAL/WRONG]
ANALYSIS: [Краткий анализ 2-3 предложения]
"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "gpt-4-vision-preview",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": photo_base64
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 500
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            text = result['choices'][0]['message']['content']
            
            # Парсим ответ
            verdict = 'WRONG'
            if 'VERDICT: CORRECT' in text:
                verdict = 'CORRECT'
            elif 'VERDICT: PARTIAL' in text:
                verdict = 'PARTIAL'
            
            analysis = text.split('ANALYSIS:')[1].strip() if 'ANALYSIS:' in text else text
            
            return {
                'verdict': verdict,
                'analysis': analysis,
                'confidence': 0.9
            }
        else:
            raise Exception(f"Vision API error: {response.status_code}")
```

#### 2.3 Обновить роут `/api/adaptive-test/<id>/submit` в `app.py`

```python
@app.route("/api/adaptive-test/<int:test_id>/submit", methods=["POST"])
@login_required
def submit_adaptive_answer(test_id):
    from models import AdaptiveTest, AdaptiveTestProblem
    from services.adaptive_test import AdaptiveTestEngine
    from services.vision_analyzer import VisionAnalyzer
    
    test = AdaptiveTest.query.get_or_404(test_id)
    
    if test.user_id != current_user.id:
        abort(403)
    
    data = request.get_json() or {}
    problem_id = data.get('problem_id')
    user_answer = data.get('answer', '').strip()
    user_solution = data.get('solution', '').strip()
    photo_base64 = data.get('photo_base64')  # Новое поле
    
    # ... существующий код проверки задачи
    
    # Проверяем текстовый ответ
    correct_answer = str(problem.get('answer', '')).strip().lower()
    user_answer_normalized = user_answer.lower()
    is_correct = (user_answer_normalized == correct_answer)
    
    # Если есть фото и ответ неправильный, проверяем фото
    if photo_base64 and not is_correct:
        try:
            vision_api_key = os.environ.get('OPENAI_API_KEY')  # или GEMINI_API_KEY
            if vision_api_key:
                analyzer = VisionAnalyzer(vision_api_key, provider='openai')
                
                vision_result = analyzer.analyze_solution_photo(
                    problem_text=problem.get('text', ''),
                    correct_answer=correct_answer,
                    photo_base64=photo_base64
                )
                
                # Сохраняем результат анализа
                current_problem_record.vision_analysis = vision_result['analysis']
                current_problem_record.vision_verdict = vision_result['verdict']
                
                # Если Vision AI говорит что решение правильное, засчитываем
                if vision_result['verdict'] in ['CORRECT', 'PARTIAL']:
                    is_correct = True
                    logger.info(f"Vision AI override: answer marked as correct based on photo analysis")
        
        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            # Продолжаем без Vision анализа
    
    # ... остальной код обновления способностей
```

### Этап 3: Хранение фото

#### Опции:
1. **Base64 в БД** (простой, но неэффективный)
2. **Локальное хранилище** (`static/uploads/solutions/`)
3. **S3/Cloud Storage** (рекомендуется для продакшена)

```python
import os
import uuid
from werkzeug.utils import secure_filename

def save_solution_photo(photo_base64: str, test_id: int, problem_id: int) -> str:
    """Сохраняет фото решения и возвращает URL"""
    
    # Декодируем Base64
    import base64
    header, encoded = photo_base64.split(',', 1)
    photo_data = base64.b64decode(encoded)
    
    # Генерируем уникальное имя
    filename = f"solution_{test_id}_{problem_id}_{uuid.uuid4().hex[:8]}.jpg"
    filepath = os.path.join('static', 'uploads', 'solutions', filename)
    
    # Создаем директорию если нужно
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    # Сохраняем файл
    with open(filepath, 'wb') as f:
        f.write(photo_data)
    
    return f"/static/uploads/solutions/{filename}"
```

## 🔧 Конфигурация

### Переменные окружения

```env
# Vision API (выбрать один)
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...

# Настройки загрузки
MAX_PHOTO_SIZE_MB=5
ALLOWED_PHOTO_FORMATS=jpg,jpeg,png,webp
```

## 📊 Стоимость

### OpenAI GPT-4 Vision
- $0.01 за изображение (низкое разрешение)
- $0.03 за изображение (высокое разрешение)

### Google Gemini Vision
- Бесплатно до 60 запросов/минуту
- $0.00025 за изображение после лимита

## ✅ Чеклист реализации

- [ ] Добавить UI для загрузки фото
- [ ] Реализовать превью изображения
- [ ] Добавить поля в модель БД
- [ ] Создать VisionAnalyzer сервис
- [ ] Обновить API endpoint
- [ ] Настроить хранение фото
- [ ] Добавить обработку ошибок
- [ ] Протестировать с реальными фото
- [ ] Оптимизировать размер изображений
- [ ] Добавить rate limiting

## 🚀 Альтернативный подход (без Vision API)

Если Vision API недоступен:
1. Сохранять фото для ручной проверки преподавателем
2. Показывать фото в результатах теста
3. Добавить функцию "Запросить ручную проверку"
4. Использовать OCR для извлечения текста (Tesseract)

## 📝 Примечания

- Vision API требует значительных вычислительных ресурсов
- Рекомендуется кэшировать результаты анализа
- Нужна валидация формата и размера изображений
- Важно обрабатывать таймауты API
- Следует логировать все Vision запросы для отладки
