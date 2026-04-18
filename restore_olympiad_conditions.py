"""
Скрипт-реставратор полных условий олимпиадных задач
Восстанавливает потерянные куски условий используя AI
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from olympiads import OLYMPIADS_DB
from ai.deepseek_client import DeepSeekClient
import json
import time

def restore_full_condition(client, broken_text):
    """Восстановить полное условие задачи"""
    
    system_prompt = r"""Ты — эксперт по математическим олимпиадам (ВсОШ, Турнир Городов, ММО, Физтех, Ломоносов).

Перед тобой текст известной олимпиадной задачи, который был поврежден или обрезан при копировании.

Твоя задача:
1. Узнай эту классическую задачу
2. Восстанови ее ПОЛНОЕ, ПРАВИЛЬНОЕ, ОРИГИНАЛЬНОЕ условие со всеми математическими тонкостями и ограничениями
3. СОХРАНИ ИДЕАЛЬНЫЙ LaTeX: все переменные и формулы оборачивай в \\( ... \\)
4. Индексы: p_n, x_i (с подчеркиванием)
5. Степени: x^2, сложные: x^{n+1}
6. Дроби: \\frac{a}{b}

В JSON используй ДВОЙНЫЕ слэши: "\\\\( p_n \\\\)"

Верни ТОЛЬКО JSON:
{
  "restored_text": "Полное восстановленное условие"
}"""
    
    user_prompt = f"""Восстанови полное условие этой олимпиадной задачи:

{broken_text}

Дополни потерянные части, сохрани правильный LaTeX."""
    
    try:
        response = client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=3000
        )
        
        # Парсим
        response_text = response.strip()
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        elif response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        response_text = response_text.strip()
        
        import re
        match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if match:
            response_text = match.group(0)
        
        data = json.loads(response_text)
        return data.get('restored_text', broken_text)
        
    except Exception as e:
        print(f"[ERROR] {e}")
        return broken_text

def main():
    print("="*80)
    print("RESTAVRATSIJA POLNYH USLOVIJ OLIMPIADNYH ZADACH")
    print("="*80)
    
    client = DeepSeekClient()
    
    # Берем первые 50 задач
    test_limit = 50
    processed = 0
    
    for combo in OLYMPIADS_DB:
        if processed >= test_limit:
            break
        
        for problem in combo.get('problems', []):
            if processed >= test_limit:
                break
            
            original_text = problem.get('text', '')
            
            # Пропускаем очень короткие (вероятно, уже полные)
            if len(original_text) > 200:
                processed += 1
                
                print(f"\n[ZADACHA {processed}] Combo ID={combo.get('id')}, Problem #{problem.get('num')}")
                print(f"[DO] (pervye 150 simvolov):")
                print(original_text[:150])
                
                print(f"\n[RESTORING]...")
                restored_text = restore_full_condition(client, original_text)
                
                print(f"\n[POSLE] (pervye 150 simvolov):")
                print(restored_text[:150])
                
                # Обновляем
                problem['text'] = restored_text
                
                print(f"\n[OK] Obnovleno")
                print("-"*80)
                
                time.sleep(2)  # Задержка между запросами
    
    print(f"\n[STATS] Obrabotano zadach: {processed}")
    
    # Сохраняем
    with open('olympiads_restored.py', 'w', encoding='utf-8') as f:
        f.write('# -*- coding: utf-8 -*-\n')
        f.write('# Baza olimpiad s vosstanovlennymi uslovijami\n\n')
        f.write('OLYMPIADS_DB = ')
        f.write(repr(OLYMPIADS_DB))
    
    print(f"\n[SAVE] Sohraneno v olympiads_restored.py")
    print("[INFO] Zamenite: move olympiads_restored.py olympiads.py")
    print("="*80)

if __name__ == '__main__':
    main()
