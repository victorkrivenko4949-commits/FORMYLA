# === ПЛАН ПОСТРОЕНИЯ ===
# 1) Базовые вершины: B=(0,0), C=(10,0), A=(2,8) - остроугольный треугольник
# 2) M1 = (B+C)/2 - середина BC
# 3) M2 = (A+C)/2 - середина CA
# 4) M3 = (A+B)/2 - середина AB
# 5) H1 - проекция A на BC: H1=(A.x, 0)
# 6) H2 - проекция B на AC
# 7) H3 - проекция C на AB
# 8) H - ортоцентр
# 9) N1=(A+H)/2, N2=(B+H)/2, N3=(C+H)/2
# 10) Центр описанной O=(5,3); OE=(H+O)/2=(3.5,2.5)
# 11) RE = |OE - M1|
# === КОНЕЦ ПЛАНА ===

import numpy as np
import matplotlib.pyplot as plt

A = np.array([2.0, 8.0])
B = np.array([0.0, 0.0])
C = np.array([10.0, 0.0])

M1 = (B + C) / 2
M2 = (A + C) / 2
M3 = (A + B) / 2
assert np.linalg.norm(M1 - B) - np.linalg.norm(M1 - C) < 1e-9

def proj(P, X, Y):
    v = Y - X
    t = np.dot(P - X, v) / np.dot(v, v)
    return X + t * v

H1 = proj(A, B, C)
H2 = proj(B, A, C)
H3 = proj(C, A, B)

assert abs(np.dot(A - H1, C - B)) < 1e-9
assert abs(np.dot(B - H2, C - A)) < 1e-9
assert abs(np.dot(C - H3, A - B)) < 1e-9

def line_intersect(P1, P2, P3, P4):
    d1 = P2 - P1
    d2 = P4 - P3
    mat = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]])
    rhs = P3 - P1
    s, r = np.linalg.solve(mat, rhs)
    return P1 + s * d1

H = line_intersect(A, H1, B, H2)
assert np.linalg.norm(H - np.array([2.0, 2.0])) < 1e-9

N1 = (A + H) / 2
N2 = (B + H) / 2
N3 = (C + H) / 2

O = np.array([5.0, 3.0])
OE = (H + O) / 2
RE = np.linalg.norm(OE - M1)

for P in [M1, M2, M3, H1, H2, H3, N1, N2, N3]:
    assert abs(np.linalg.norm(OE - P) - RE) < 1e-6, 'point not on Euler circle'

fig, ax = plt.subplots(figsize=(10, 10), dpi=140)
ax.set_aspect('equal')
ax.axis('off')

tri = plt.Polygon([A, B, C], fill=False, edgecolor='black', linewidth=2)
ax.add_patch(tri)

ax.plot([A[0], H1[0]], [A[1], H1[1]], 'k--', linewidth=1.5)
ax.plot([B[0], H2[0]], [B[1], H2[1]], 'k--', linewidth=1.5)
ax.plot([C[0], H3[0]], [C[1], H3[1]], 'k--', linewidth=1.5)

theta = np.linspace(0, 2*np.pi, 400)
ax.plot(OE[0] + RE*np.cos(theta), OE[1] + RE*np.sin(theta), 'k-', linewidth=2)

points = {
    'A':  (A,  (0.0, 0.40)),
    'B':  (B,  (-0.4, -0.15)),
    'C':  (C,  (0.35, -0.1)),
    'H':  (H,  (0.40, -0.30)),
    'M1': (M1, (0.05, -0.55)),
    'M2': (M2, (0.55, 0.25)),
    'M3': (M3, (-0.75, 0.30)),
    'H1': (H1, (-0.50, -0.50)),
    'H2': (H2, (0.55, 0.35)),
    'H3': (H3, (-0.75, -0.05)),
    'N1': (N1, (0.35, 0.25)),
    'N2': (N2, (0.45, -0.30)),
    'N3': (N3, (0.25, 0.45)),
}

for name, (pt, off) in points.items():
    ax.plot(pt[0], pt[1], 'ko', markersize=5)
    label = name if len(name) == 1 else f'${name[0]}_{{{name[1:]}}}$'
    ax.text(pt[0] + off[0], pt[1] + off[1], label, fontsize=16, ha='center', va='center')

allx = [A[0], B[0], C[0], OE[0]-RE, OE[0]+RE]
ally = [A[1], B[1], C[1], OE[1]-RE, OE[1]+RE]
xmin, xmax = min(allx), max(allx)
ymin, ymax = min(ally), max(ally)
dx = xmax - xmin
dy = ymax - ymin
pad = 0.12 * max(dx, dy)
ax.set_xlim(xmin - pad, xmax + pad)
ax.set_ylim(ymin - pad, ymax + pad)