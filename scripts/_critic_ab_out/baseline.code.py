import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(8, 8), dpi=128)
ax.set_aspect('equal')
ax.axis('off')

# Острый треугольник ABC. Известно свойство: AH = 2*OM всегда выполняется.
# Возьмём конкретные координаты для красивого чертежа.
A = np.array([0.5, 4.2])
B = np.array([-3.0, -1.0])
C = np.array([3.5, -1.0])

# Описанная окружность: центр O - пересечение серединных перпендикуляров
def circumcenter(A, B, C):
    ax_, ay_ = A; bx, by = B; cx, cy = C
    d = 2*(ax_*(by-cy) + bx*(cy-ay_) + cx*(ay_-by))
    ux = ((ax_**2+ay_**2)*(by-cy) + (bx**2+by**2)*(cy-ay_) + (cx**2+cy**2)*(ay_-by))/d
    uy = ((ax_**2+ay_**2)*(cx-bx) + (bx**2+by**2)*(ax_-cx) + (cx**2+cy**2)*(bx-ax_))/d
    return np.array([ux, uy])

O = circumcenter(A, B, C)
R = np.linalg.norm(A - O)

# Ортоцентр H = A + B + C - 2O (для центра O в произвольной точке: H = A+B+C-2O если O - центр)
# Точнее: если O - центр описанной, то H = A+B+C-2O в системе с O в начале: H_rel = A_rel+B_rel+C_rel
H = A + B + C - 2*O

# Середина BC
M = (B + C) / 2

# Основание высоты из A на BC
BC = C - B
t = np.dot(A - B, BC) / np.dot(BC, BC)
H1 = B + t * BC

# Окружность
theta = np.linspace(0, 2*np.pi, 200)
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

# Прямой угол в H1
def right_angle_mark(P, dir1, dir2, size=0.25):
    d1 = dir1/np.linalg.norm(dir1)
    d2 = dir2/np.linalg.norm(dir2)
    p1 = P + d1*size
    p2 = P + d1*size + d2*size
    p3 = P + d2*size
    ax.plot([p1[0],p2[0],p3[0]], [p1[1],p2[1],p3[1]], 'k-', linewidth=1.5)

right_angle_mark(H1, A-H1, C-H1, size=0.25)
right_angle_mark(M, O-M, C-M, size=0.25)

# Точки
pts = {'A': A, 'B': B, 'C': C, 'H': H, 'O': O, 'M': M}
H1_label = 'H_1'
for name, P in pts.items():
    ax.plot(P[0], P[1], 'ko', markersize=5)

ax.plot(H1[0], H1[1], 'ko', markersize=5)

# Подписи
ax.annotate('A', A, xytext=(A[0], A[1]+0.25), fontsize=20, ha='center')
ax.annotate('B', B, xytext=(B[0]-0.3, B[1]-0.1), fontsize=20, ha='right')
ax.annotate('C', C, xytext=(C[0]+0.3, C[1]-0.1), fontsize=20, ha='left')
ax.annotate('H', H, xytext=(H[0]+0.25, H[1]+0.1), fontsize=20)
ax.annotate('O', O, xytext=(O[0]+0.25, O[1]+0.1), fontsize=20)
ax.annotate('M', M, xytext=(M[0]+0.15, M[1]-0.45), fontsize=20)
ax.annotate(r'$H_1$', H1, xytext=(H1[0]-0.15, H1[1]-0.5), fontsize=20)

# Границы
all_x = [A[0], B[0], C[0], O[0]+R, O[0]-R]
all_y = [A[1], B[1], C[1], O[1]+R, O[1]-R]
xmin, xmax = min(all_x), max(all_x)
ymin, ymax = min(all_y), max(all_y)
dx = (xmax-xmin)*0.1
dy = (ymax-ymin)*0.1
ax.set_xlim(xmin-dx, xmax+dx)
ax.set_ylim(ymin-dy, ymax+dy)