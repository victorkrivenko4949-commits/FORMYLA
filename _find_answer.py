import json, sys

path = r"c:\Users\Redmi\Desktop\Новая папка (2)\FORMYLA_L1_L5_TOP5.jsonl"
found = []
with open(path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if i not in (1382,):
            continue
        data = json.loads(line)
        ans = repr(data.get('answer', ''))
        stmt = repr(data.get('statement', '')[:120])
        with open(r"c:\Users\Redmi\Desktop\Новая папка (2)\_ans_out.txt", 'w', encoding='utf-8') as out:
            out.write(f"Line {i}\nanswer={ans}\nstmt={stmt}\n")
        print(f"Line {i}: answer extracted to _ans_out.txt")
        break
