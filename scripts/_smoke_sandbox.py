# -*- coding: utf-8 -*-
"""Smoke test the sandbox executor with a minimal matplotlib snippet."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.sandbox import run_drawing_code

CODE = '''
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import math

A = (0.0, 0.0)
B = (5.0, 0.0)
C = (3.5, 7.0 * math.sin(math.radians(60)))

fig, ax = plt.subplots(figsize=(6, 6), dpi=128)
ax.set_aspect("equal")
ax.axis("off")
for p1, p2 in [(A, B), (A, C), (B, C)]:
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color="black", linewidth=2)

ax.text(A[0] - 0.3, A[1] - 0.3, "A", fontsize=22, weight="bold")
ax.text(B[0] + 0.2, B[1] - 0.3, "B", fontsize=22, weight="bold")
ax.text(C[0], C[1] + 0.3, "C", fontsize=22, weight="bold", ha="center")
'''

png = run_drawing_code(CODE, timeout=15.0)
out = os.path.join("static", "generated", "_test_sandbox.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "wb") as f:
    f.write(png)
print("OK bytes=", len(png), "saved to", out)
