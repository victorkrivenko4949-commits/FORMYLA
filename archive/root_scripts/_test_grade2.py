import json, sys  
with open('curated_bank_L1_L5_taxonomy_v2.json','r',encoding='utf-8') as f:  
    data = json.load(f)  
grade_topics = {}  
for item in data:  
    if isinstance(item, dict):  
        g = item.get('class_level') or item.get('grade')  
        t = item.get('topic','')  
        if g and t:  
            g = str(g).strip()  
            t = t.strip()  
            if g not in grade_topics:  
                grade_topics[g] = set()  
            grade_topics[g].add(t)  
for g in sorted(grade_topics.keys(), key=lambda x: int(x) if x.isdigit() else 999):  
    topics = sorted(grade_topics[g])  
    print(f'Grade {g}: {len(topics)} topics')  
    for t in topics:  
        print(f'  {t}')  
