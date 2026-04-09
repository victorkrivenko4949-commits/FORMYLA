import os
import re
import sys
import time
import base64
import json
import requests

sys.path.insert(0, ".")
from olympiads import OLYMPIADS_DB

FOLDER = "static/images/problems/"
API_KEY = "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"

# Используем гарантированно бесплатную модель с Vision
MODEL = "google/gemini-2.0-flash-lite-preview-02-05:free"

def encode_image(image_path):
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"Ошибка чтения {image_path}: {e}")
        return None

def check_match(text, image_base64):
    prompt = f"""Перед тобой текст математической задачи и картинка.
Твоя цель - определить, является ли эта картинка иллюстрацией к этой задаче.
Ответь ТОЛЬКО одним словом: ДА или НЕТ. Больше ничего не пиши.

Текст задачи:
{text}
"""
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "HTTP-Referer": "http://localhost:5000",
        "X-Title": "Formyla Project",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}"
                        }
                    }
                ]
            }
        ]
    }
    
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        
        if response.status_code != 200:
            print(f"  [API ERROR {response.status_code}] {response.text}")
            return False
            
        data = response.json()
        if 'choices' in data and len(data['choices']) > 0:
            reply = data['choices'][0]['message']['content'].strip().upper()
            return "ДА" in reply
        else:
            print(f"  [UNEXPECTED RESPONSE] {data}")
            return False
            
    except Exception as e:
        print(f"  [REQUEST FAILED] {e}")
        return False

# Маппинг префиксов
OLYMPIAD_KEYS = {
    "fu": ["Формула Единства", "formula_unity"],
    "vsosh": ["ВсОШ", "vsosh"],
    "vysshaya_proba": ["Высшая проба", "vysshaya_proba"],
}

IMG_KEYWORDS = ["рис", "схем", "чертеж", "таблиц", "ниже", "справа", "изображен"]

print(f"Начинаем маппинг через модель: {MODEL}")
IMAGE_MAP = {}
processed_files = 0
matched_count = 0

files = [f for f in os.listdir(FOLDER) if f.lower().endswith(('.jpg', '.png')) and "копия" not in f.lower()]
files.sort()

tasks_with_images = []
for combo in OLYMPIADS_DB:
    c_id = combo.get('id')
    c_year = combo.get('year')
    c_grade = combo.get('grade')
    c_olympiad = combo.get('olympiad', '').lower()
    
    for p in combo.get('problems', []):
        text = p.get('text', '').lower()
        if any(kw in text for kw in IMG_KEYWORDS):
            tasks_with_images.append({
                'id': c_id,
                'num': p.get('num'),
                'year': c_year,
                'grade': c_grade,
                'olympiad': c_olympiad,
                'text': p.get('text', '')
            })

print(f"Найдено {len(tasks_with_images)} задач с упоминанием рисунка.")
print(f"Найдено {len(files)} файлов картинок.\n")

for filename in files[:5]:  # Тестируем на первых 5 файлах
    processed_files += 1
    match = re.match(r"([a-z_]+)_(\d{4})_g(\d+)_v?fig(\d+)", filename.replace(".jpeg", ".jpg"))
    if not match:
        continue
        
    prefix, year_str, grade_str, _ = match.groups()
    year, grade = int(year_str), int(grade_str)
    target_names = OLYMPIAD_KEYS.get(prefix, [prefix])
    
    filepath = os.path.join(FOLDER, filename)
    img_base64 = encode_image(filepath)
    if not img_base64:
        continue
        
    candidates = []
    for task in tasks_with_images:
        if task['year'] == year and str(task['grade']) == str(grade):
            if any(name.lower() in task['olympiad'] for name in target_names):
                candidates.append(task)
                
    if not candidates:
        continue
        
    print(f"[{processed_files}/5] Файл {filename} - кандидатов: {len(candidates)}")
    
    for cand in candidates[:2]:  # Проверяем только первых 2 кандидатов
        key = f"{cand['id']}_{cand['num']}"
        if key in IMAGE_MAP:
            continue
            
        print(f"  -> Спрашиваем API для задачи {cand['id']} №{cand['num']}...")
        is_match = check_match(cand['text'], img_base64)
        
        if is_match:
            print(f"  [+] API ответил ДА! Привязываем.")
            IMAGE_MAP[key] = f"/static/images/problems/{filename}"
            matched_count += 1
            break
        else:
            print(f"  [-] API ответил НЕТ.")
            
        time.sleep(3)

print(f"\nТЕСТ ЗАВЕРШЕН. Привязано: {matched_count} из 5 файлов")
print("Если все работает - увеличьте лимит в коде (files[:5] -> files)")
