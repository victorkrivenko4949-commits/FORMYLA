import os
import requests
from bs4 import BeautifulSoup
import time
import json
from urllib.parse import urljoin

# Настройки
BASE_URL = "https://problems.ru/view_problem_details_new.php?id="
IMAGES_DIR = "static/images/new_base"
START_ID = 78000 # Начнем с актуальных олимпиадных задач
COUNT = 200 # Для начала спарсим 200 задач (потом увеличим)

os.makedirs(IMAGES_DIR, exist_ok=True)

def download_image(img_url, problem_id):
    try:
        response = requests.get(img_url, stream=True, timeout=10)
        if response.status_code == 200:
            filename = f"prob_{problem_id}_{os.path.basename(img_url)}"
            # Очищаем имя от параметров URL если они есть
            filename = filename.split('?')[0]
            filepath = os.path.join(IMAGES_DIR, filename)
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            return f"/static/images/new_base/{filename}"
    except Exception as e:
        print(f"Ошибка скачивания картинки {img_url}: {e}")
    return None

print(f"Начинаем парсинг {COUNT} задач с problems.ru...")
parsed_problems = []
success_count = 0

# Идем по ID задач
for pid in range(START_ID, START_ID + COUNT):
    url = f"{BASE_URL}{pid}"
    try:
        response = requests.get(url, timeout=10)
        response.encoding = 'windows-1251' # problems.ru использует эту кодировку
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Проверяем, существует ли задача (ищем заголовок Условие)
        condition_div = soup.find('div', string=lambda t: t and 'Условие' in t)
        if not condition_div:
            continue
            
        # Ищем текст условия (обычно следующий элемент после заголовка)
        condition_box = condition_div.find_next_sibling('div')
        if not condition_box:
            continue
            
        # Ищем решение
        solution_div = soup.find('div', string=lambda t: t and 'Решение' in t)
        solution_box = solution_div.find_next_sibling('div') if solution_div else None
        
        # Ищем источник (олимпиада, год, класс)
        source = ""
        source_box = soup.find('div', class_='componentbox')
        if source_box:
            source = source_box.text.strip()
            
        # Обрабатываем картинки в условии
        condition_html = str(condition_box)
        for img in condition_box.find_all('img'):
            if 'src' in img.attrs:
                img_url = urljoin("https://problems.ru/", img['src'])
                # Скачиваем картинку
                local_path = download_image(img_url, pid)
                if local_path:
                    # Заменяем URL в HTML
                    condition_html = condition_html.replace(img['src'], local_path)
                    
        # Собираем данные
        problem_data = {
            "id": pid,
            "source": source,
            "text": condition_html,
            "solution": str(solution_box) if solution_box else ""
        }
        
        parsed_problems.append(problem_data)
        success_count += 1
        print(f"[{success_count}] Спарсена задача {pid} ({source[:40]}...)")
        
    except Exception as e:
        print(f"Ошибка на задаче {pid}: {e}")
        
    time.sleep(0.5) # Пауза, чтобы не забанили IP

# Сохраняем в JSON для проверки
with open("temp_new_problems.json", "w", encoding="utf-8") as f:
    json.dump(parsed_problems, f, ensure_ascii=False, indent=4)

print(f"\nГОТОВО! Успешно спарсено {success_count} задач.")
print("Результат сохранен в temp_new_problems.json для проверки.")
