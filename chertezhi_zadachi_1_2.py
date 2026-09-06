"""
Чертежи к задачам 1 и 2 (геометрия, выпуклое положение).

Задача 1: 8 точек общего положения без выпуклого пятиугольника.
Задача 2: пятиугольник, у которого ровно одна сторона опорная.

Запуск:
    pip install matplotlib numpy
    python chertezhi_zadachi_1_2.py

Результат: PNG-файлы zadacha1_8_tochek.png и zadacha2_pyatiugolnik.png
в подпапке output рядом со скриптом. Скрипт также проверяет обе конфигурации
перебором, чтобы чертёж гарантированно соответствовал условию.
"""

import os
from itertools import combinations

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# DejaVu Sans нужен для корректной кириллицы в подписях
matplotlib.rcParams["font.family"] = "DejaVu Sans"

OUT = "output"
os.makedirs(OUT, exist_ok=True)

# ----------------------------------------------------------------------
# Геометрические утилиты
# ----------------------------------------------------------------------

def cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def convex_hull(points):
    pts = sorted(set(points))
    if len(pts) < 3:
        return pts

    def half(seq):
        h = []
        for q in seq:
            while len(h) >= 2 and cross(h[-2], h[-1], q) <= 0:
                h.pop()
            h.append(q)
        return h

    lower = half(pts)
    upper = half(pts[::-1])
    return lower[:-1] + upper[:-1]


def general_position(points):
    return all(cross(a, b, c) != 0 for a, b, c in combinations(points, 3))


def count_convex_pentagons(points):
    return sum(1 for t in combinations(points, 5) if len(convex_hull(list(t))) == 5)


def supporting_sides(poly):
    """Индексы сторон, относительно прямой которых весь многоугольник лежит в одной полуплоскости."""
    n = len(poly)
    res = []
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        vals = [cross(a, b, p) for j, p in enumerate(poly) if j not in (i, (i + 1) % n)]
        if all(v >= 0 for v in vals) or all(v <= 0 for v in vals):
            res.append(i)
    return res


# ----------------------------------------------------------------------
# Задача 1: 8 точек, среди которых нет выпуклого пятиугольника
# ----------------------------------------------------------------------

OUTER = [(0, 13), (2, 4), (13, 6), (13, 13)]   # выпуклая оболочка
INNER = [(6, 10), (7, 9), (12, 8), (11, 11)]   # четыре точки внутри
EIGHT = OUTER + INNER

assert general_position(EIGHT), "есть три точки на одной прямой"
assert count_convex_pentagons(EIGHT) == 0, "нашёлся выпуклый пятиугольник"
assert len(convex_hull(EIGHT)) == 4


def draw_task1(path=os.path.join(OUT, "zadacha1_8_tochek.png")):
    ox = [p[0] for p in OUTER] + [OUTER[0][0]]
    oy = [p[1] for p in OUTER] + [OUTER[0][1]]
    ix = [p[0] for p in INNER] + [INNER[0][0]]
    iy = [p[1] for p in INNER] + [INNER[0][1]]

    fig, ax = plt.subplots(figsize=(7, 7))
    ax.plot(ox, oy, "-", color="#d98040", lw=2, label="внешний 4-угольник (оболочка)")
    ax.plot(ix, iy, "--", color="#6a3fbf", lw=2, label="внутренний 4-угольник")
    for p in EIGHT:
        ax.plot(*p, "o", color="#222", ms=7)
        ax.annotate(f"({p[0]},{p[1]})", p, textcoords="offset points",
                    xytext=(7, 6), fontsize=9)

    ax.set_title("Задача 1: 8 точек общего положения без выпуклого\n"
                 "пятиугольника (максимум в выпуклом положении — 4 точки)",
                 fontsize=11)
    ax.legend(fontsize=9, loc="lower left")
    ax.set_aspect("equal")
    ax.grid(alpha=0.25)
    ax.set_xlim(-1.5, 15.5)
    ax.set_ylim(2.5, 15.2)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


# ----------------------------------------------------------------------
# Задача 2: пятиугольник ровно с одной опорной стороной
# ----------------------------------------------------------------------

PENT = [(0, 0), (2, 0.5), (4, 0), (2, 2), (2, 3)]   # A, P, B, Q, C
LABELS = ["A", "P", "B", "Q", "C"]
HULL_TRI = [(0, 0), (4, 0), (2, 3), (0, 0)]

assert supporting_sides(PENT) == [4], "опорных сторон должно быть ровно одна (CA)"


def draw_task2(path=os.path.join(OUT, "zadacha2_pyatiugolnik.png")):
    xs = [p[0] for p in PENT] + [PENT[0][0]]
    ys = [p[1] for p in PENT] + [PENT[0][1]]

    fig, ax = plt.subplots(figsize=(7, 6.6))
    ax.fill(xs, ys, color="#f4d9c4", alpha=0.6)
    ax.plot(xs, ys, color="#c8621f", lw=2.2)
    ax.plot([t[0] for t in HULL_TRI], [t[1] for t in HULL_TRI], ":",
            color="#888", lw=1.4, label="оболочка — треугольник ABC")

    # опорная прямая CA, продолженная в обе стороны
    k = np.linspace(-0.6, 1.5, 2)
    ax.plot(2 * k, 3 * k, color="#1a7f37", lw=1.8,
            label="прямая CA — единственная опорная")

    # прямые остальных сторон: они рассекают пятиугольник
    for a, b in [((0, 0), (2, 0.5)), ((2, 0.5), (4, 0)),
                 ((4, 0), (2, 2)), ((2, 2), (2, 3))]:
        d = (b[0] - a[0], b[1] - a[1])
        s = np.linspace(-1.3, 2.3, 2)
        ax.plot([a[0] + d[0] * t for t in s], [a[1] + d[1] * t for t in s],
                "--", color="#2050c8", lw=1.0, alpha=0.75)

    offsets = [(-16, -14), (4, -16), (8, -12), (10, 2), (6, 8)]
    for p, name, off in zip(PENT, LABELS, offsets):
        ax.plot(*p, "o", color="#111", ms=7)
        ax.annotate(name, p, textcoords="offset points", xytext=off,
                    fontsize=13, weight="bold")

    ax.set_title("Задача 2: пятиугольник A–P–B–Q–C, точки P и Q внутри оболочки.\n"
                 "Прямые сторон AP, PB, BQ, QC рассекают пятиугольник",
                 fontsize=10.5)
    ax.legend(fontsize=8.5, loc="upper right")
    ax.set_aspect("equal")
    ax.grid(alpha=0.25)
    ax.set_xlim(-1.4, 5.4)
    ax.set_ylim(-1.5, 4.0)
    fig.tight_layout()
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


# ----------------------------------------------------------------------
# Поиск других 8-точечных примеров (по желанию)
# ----------------------------------------------------------------------

def search_eight_points(grid=14, restarts=200, steps=4000, seed=1):
    """Локальный поиск: 8 точек на сетке grid x grid без выпуклого пятиугольника."""
    import random
    rnd = random.Random(seed)
    cells = [(x, y) for x in range(grid) for y in range(grid)]

    def score(pts):
        return count_convex_pentagons(pts) + (0 if general_position(pts) else 100)

    for _ in range(restarts):
        cur = rnd.sample(cells, 8)
        val = score(cur)
        for _ in range(steps):
            if val == 0:
                return cur
            cand = list(cur)
            cand[rnd.randrange(8)] = (rnd.randrange(grid), rnd.randrange(grid))
            if len(set(cand)) < 8:
                continue
            v = score(cand)
            if v <= val:
                cur, val = cand, v
        if val == 0:
            return cur
    return None


if __name__ == "__main__":
    p1 = draw_task1()
    p2 = draw_task2()
    print("сохранено:", p1, p2)
    print("выпуклых пятиугольников среди 8 точек:", count_convex_pentagons(EIGHT))
    print("опорные стороны пятиугольника (индексы):", supporting_sides(PENT))
