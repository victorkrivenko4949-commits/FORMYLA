import json  
with open('curated_bank_L1_L5_taxonomy_v2.json','r',encoding='utf-8') as f:  
    data = json.load(f)  
print(type(data), len(data))  
print(list(data[0].keys()))  
