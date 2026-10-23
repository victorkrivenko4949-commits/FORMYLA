# -*- coding: utf-8 -*-
import io, sys, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
for r, d, fs in os.walk("tests"):
    for f in fs:
        if not f.endswith(".py"):
            continue
        p = os.path.join(r, f)
        for i, l in enumerate(open(p, encoding="utf-8", errors="replace"), 1):
            if "bg_color" in l or "background-color" in l or "0f172a" in l or "070C18" in l or "#0F1729" in l.lower():
                print(p, i, l.strip()[:100])
