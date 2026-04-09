# Быстрое исправление: Отображение условий задач

## Проблема
В adaptive_test.html не отображается текст задачи (problem.text)

## Решение

### 1. Добавить счетчик и контейнер для условия

В `templates/adaptive_test.html` после строки 32 (после прогресс-бара) добавить:

```html
<!-- Счетчик задач и раздел -->
<div style="text-align: center; margin-bottom: 25px;">
    <h3 id="progressCounter" style="color: var(--text-main); font-size: 1.4em; margin-bottom: 10px;">
        Задача <span id="currentTaskNum">1</span> из <span id="totalTasks">25</span>
    </h3>
    <div id="currentSection" style="color: var(--accent-2); font-size: 1.1em; font-weight: 600;">
        Раздел: <span id="sectionName">Загрузка...</span>
    </div>
</div>
```

### 2. Обновить функцию displayProblem (строка ~105)

Заменить весь блок `container.innerHTML` на:

```javascript
function displayProblem(problemId, number) {
    const container = document.getElementById('problemContainer');
    
    container.innerHTML = `
        <div class="fade-in" style="background: var(--bg-card); backdrop-filter: blur(12px); padding: 35px; border-radius: var(--radius-lg); border: 1px solid var(--border-soft);">
            
            <!-- УСЛОВИЕ ЗАДАЧИ - КРУПНО -->
            <div id="problemTextDisplay" style="
                color: var(--text-soft); 
                line-height: 1.9; 
                margin-bottom: 30px; 
                font-size: 1.2rem;
                text-align: left;
                padding: 25px;
                background: rgba(0, 0, 0, 0.3);
                border-radius: var(--radius-md);
                border-left: 4px solid var(--accent-2);
                white-space: pre-wrap;
            ">
                Загрузка условия задачи...
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: block; color: var(--text-soft); margin-bottom: 10px; font-weight: 500;">Ваш ответ:</label>
                <input type="text" id="userAnswer" placeholder="Введите ответ" 
                       style="width: 100%; padding: 14px; background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-mid); border-radius: var(--radius-sm); color: var(--text-main); caret-color: var(--accent-2); font-size: 16px;">
            </div>
            
            <div style="margin-bottom: 25px;">
                <label style="display: block; color: var(--text-soft); margin-bottom: 10px; font-weight: 500;">Ход решения (опционально):</label>
                <textarea id="userSolution" placeholder="Опишите как вы решали задачу..." 
                          style="width: 100%; min-height: 120px; padding: 14px; background: rgba(15, 23, 42, 0.6); border: 1px solid var(--border-mid); border-radius: var(--radius-sm); color: var(--text-main); caret-color: var(--accent-2); resize: vertical; font-size: 15px;"></textarea>
            </div>
            
            <div style="text-align: center;">
                <button onclick="submitAnswer(${problemId})" id="submitBtn" 
                        style="padding: 14px 40px; background: linear-gradient(135deg, var(--accent-2) 0%, var(--accent-1) 100%); color: white; border: none; border-radius: var(--radius-sm); font-size: 17px; font-weight: 600; cursor: pointer; box-shadow: 0 4px 12px rgba(56, 189, 248, 0.3); transition: all 0.3s;">
                    Ответить →
                </button>
            </div>
        </div>
    `;
    
    // Загружаем текст задачи
    loadProblemText(problemId);
}
```

### 3. Обновить loadProblemText (строка ~146)

Заменить на:

```javascript
async function loadProblemText(problemId) {
    // Находим задачу в problems_list
    const problem = problems_list.find(p => p.problem_id === problemId);
    
    if (problem) {
        // Получаем полные данные задачи из PROBLEMS_DB через API или из контекста
        // Для простоты используем fetch к существующему endpoint
        try {
            const response = await fetch(`/api/problem/${problemId}`);
            if (response.ok) {
                const data = await response.json();
                document.getElementById('problemTextDisplay').textContent = data.text || 'Условие задачи недоступно';
                
                // Обновляем раздел
                const subjectNames = {
                    'algebra': 'Алгебра',
                    'geometry': 'Геометрия',
                    'combinatorics': 'Комбинаторика',
                    'number_theory': 'Теория чисел',
                    'movement': 'Задачи на движение',
                    'knights_liars': 'Рыцари и лжецы'
                };
                document.getElementById('sectionName').textContent = subjectNames[data.subject] || data.subject;
            }
        } catch (error) {
            console.error('Error loading problem:', error);
            document.getElementById('problemTextDisplay').textContent = 'Ошибка загрузки условия';
        }
    }
}
```

### 4. Добавить API endpoint в app.py

После строки 1352 добавить:

```python
@app.route("/api/problem/<int:problem_id>")
@login_required
def get_problem(problem_id):
    """Получить данные задачи по ID"""
    problem = next((p for p in PROBLEMS_DB if p['id'] == problem_id), None)
    if problem:
        return jsonify(problem)
    return jsonify({'error': 'Problem not found'}), 404
```

### 5. Обновить счетчик при загрузке

В функции `loadCurrentProblem` (строка ~74) после строки 102 добавить:

```javascript
// Обновляем счетчик
document.getElementById('currentTaskNum').textContent = currentNumber;
document.getElementById('totalTasks').textContent = totalProblems;
```

## Готово!

После этих изменений:
- ✅ Условие задачи отображается крупно
- ✅ Счетчик "Задача X из 25"
- ✅ Название раздела
- ✅ Поддержка многострочности (white-space: pre-wrap)

Запускайте и тестируйте!
