#!/usr/bin/env python3
import os
with open('.env','r',encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line.startswith('OPENROUTER_API_KEY='):
            key = line.split('=',1)[1].strip().strip('"').strip("'")
            with open('l1_l3_generation/openrouter_key.txt','w') as kf:
                kf.write(key)
            print(f"Key saved: {key[:16]}...")
            break
    else:
        print("KEY NOT FOUND in .env")
