=== РИСУНКИ ДЛЯ ОЛИМПИАДНЫХ ЗАДАЧ ===

Формула Единства 2018-2024: 60 уникальных рисунков, 153 привязки к задачам.

=== КАК УСТАНОВИТЬ ===

1. Скопируй папку static/images/problems/ в свой проект:
   Новая папка (2)/static/images/problems/

2. Скопируй problem_images.py в корень проекта:
   Новая папка (2)/problem_images.py

3. В app.py добавь импорт (после строки from problems import PROBLEMS_DB):

   from problem_images import IMAGE_MAP

4. В app.py добавь код для привязки рисунков к задачам (после загрузки OLYMPIADS_DB):

   # Добавляем рисунки к задачам
   for entry in COMBOS:
       entry_id = entry.get('id')
       for p in entry.get('problems', []):
           num = p.get('num')
           img = IMAGE_MAP.get((entry_id, num))
           if img:
               p['image'] = f'/static/images/problems/{img}'

5. В шаблоне problem_detail.html добавь показ рисунка:

   {% if problem.image %}
   <div style="text-align:center; margin:16px 0;">
       <img src="{{ problem.image }}" alt="Рисунок к задаче"
            style="max-width:100%; height:auto; border:1px solid #ddd; border-radius:8px; padding:8px; background:#fff;">
   </div>
   {% endif %}

   Поставь это ПОСЛЕ текста задачи ({{ problem.text }}).

6. Для страницы списка задач (problems.html), если хочешь показывать
   превью рисунков в карточках:

   {% if problem.image %}
   <img src="{{ problem.image }}" alt="" style="max-width:120px; float:right; margin-left:8px;">
   {% endif %}

