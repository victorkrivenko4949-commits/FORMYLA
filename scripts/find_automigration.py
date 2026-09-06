# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
src = open("app.py", encoding="utf-8").read()
for i, l in enumerate(src.splitlines(), 1):
    if "figure_build" in l.lower() or "aux_" in l.lower() or "ALTER TABLE" in l:
        print(i, l.strip()[:140])
