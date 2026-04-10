# -*- coding: utf-8 -*-
import json
import os
import glob

"""
Данные для адаптивного тестирования
Скрипт автоматически собирает все JSON-файлы из папки adaptive_data
и объединяет их в единый список ADAPTIVE_DB.
"""

ADAPTIVE_DB = []

# Путь к папке с твоими JSON-файлами
# Если файлы лежат прямо в папке проекта, укажи '.' 
# Если в папке adaptive_data, укажи 'adaptive_data'
json_folder = 'adaptive_data' 

# Ищем все .json файлы в указанной папке
json_pattern = os.path.join(json_folder, '*.json')
file_list = glob.glob(json_pattern)

# Игнорируем лишний файл, про который ты говорил
ignore_files = ['kl_movement_90401_90480-6.json']

print(f"Загрузка задач для адаптивного теста из {json_folder}...")

for file_path in file_list:
    file_name = os.path.basename(file_path)
    
    if file_name in ignore_files:
        print(f"  [Пропуск] {file_name} (в списке исключений)")
        continue
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                ADAPTIVE_DB.extend(data)
                print(f"  [Успех] {file_name}: добавлено {len(data)} задач")
            else:
                print(f"  [Ошибка] {file_name}: файл не содержит массив (список)")
    except Exception as e:
        print(f"  [Ошибка] Не удалось прочитать {file_name}: {e}")

print(f"Всего загружено {len(ADAPTIVE_DB)} задач для адаптивного теста.")