import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(8, 8), dpi=128)
ax.set_aspect('equal')
ax.axis('off')

# Острый треугольник ABC. Известно, что AH = 2*OM всегда выполняется
# в любом треугольнике (классическое свойство). Возьмём конкретный острый треугольник.
A = np.array([1.2, 5.5])
B = np.array([-3.0, 0.0])
C = np.array([4.5, 0.0])

# Центр описанной окружности O
def circumcenter(A, B, C):
    ax_, ay = A; bx, by = B; cx, cy = C
    d = 2*(ax_*(by-cy) + bx*(cy-ay) + cx*(ay-by))
    ux = ((ax_**2+ay**2)*(by-cy) + (bx**2+by**2)*(cy-ay) + (cx**2+cy**2)*(ay-by))/d
    uy = ((ax_**2+ay**2)*(cx-bx) + (bx**2+by**2)*(ax_-cx) + (cx**2+cy**2)*(bx-ax_))/d
    return np.array([ux, uy])

O = circumcenter(A, B, C)
R = np.linalg.norm(A - O)

# Ортоцентр H = A + B + C - 2O (при O как центре)... используем H = A+B+C-2O для барицентрических соотношений? 
# Правильнее: H = A + B + C - 2*O неверно. Используем формулу: вектор OH = OA+OB+OC
H = O + (A - O) + (B - O) + (C - O)

# Середина BC
M = (B + C) / 2

# Основание высоты из A на BC
BC = C - B
t = np.dot(A - B, BC) / np.dot(BC, BC)
H1 = B + t * BC

# Окружность
theta = np.linspace(0, 2*np.pi, 400)
ax.plot(O[0] + R*np.cos(theta), O[1] + R*np.sin(theta), 'k-', linewidth=2)

# Треугольник
tri = np.array([A, B, C, A])
ax.plot(tri[:,0], tri[:,1], 'k-', linewidth=2)

# Высота AH1
ax.plot([A[0], H1[0]], [A[1], H1[1]], 'k-', linewidth=2)

# Медиана AM
ax.plot([A[0], M[0]], [A[1], M[1]], 'k-', linewidth=2)

# Отрезок OM
ax.plot([O[0], M[0]], [O[1], M[1]], 'k-', linewidth=2)

# Прямой угол в H1 (высота перпендикулярна BC)
def right_angle_mark(P, dir1, dir2, size=0.25):
    d1 = dir1/np.linalg.norm(dir1)
    d2 = dir2/np.linalg.norm(dir2)
    p1 = P + d1*size
    p2 = P + d1*size + d2*size
    p3 = P + d2*size
    ax.plot([p1[0], p2[0], p3[0]], [p1[1], p2[1], p3[1]], 'k-', linewidth=1.5)

right_angle_mark(H1, A - H1, C - H1, size=0.22)
# Прямой угол в M (OM перпендикулярна BC)
right_angle_mark(M, O - M, C - M, size=0.22)

# Точки
for P, name, off in [(A, 'A', (-0.1, 0.25)), (B, 'B', (-0.3, -0.05)),
                     (C, 'C', (0.15, -0.05)), (H, 'H', (0.15, 0.05)),
                     (O, 'O', (0.15, 0.15)), (M, 'M', (-0.05, -0.4)),
                     (H1, 'H_1', (0.1, -0.4))]:
    ax.plot(P[0], P[1], 'ko', markersize=5)
    ax.text(P[0]+off[0], P[1]+off[1], f'${name}$', fontsize=20, ha='left', va='bottom')

# Границы
allx = np.concatenate([tri[:,0], [O[0]-R, O[0]+R]])
ally = np.concatenate([tri[:,1], [O[1]-R, O[1]+R]])
xmin, xmax = allx.min(), allx.max()
ymin, ymax = ally.min(), ally.max()
dx = (xmax-xmin)*0.1; dy = (ymax-ymin)*0.1
ax.set_xlim(xmin-dx, xmax+dx)
ax.set_ylim(ymin-dy, ymax+dy)