# Intentionally broken: missing circumscribed circle, no H1 foot,
# H point placed at a wrong location (random), no right-angle mark.
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots(figsize=(8, 8), dpi=128)
ax.set_aspect('equal'); ax.axis('off')

A = np.array([0.0, 4.0])
B = np.array([-3.0, -1.0])
C = np.array([3.5, -1.0])
M = (B + C) / 2

# wrong H: just somewhere in the middle, not the orthocenter
H = np.array([0.5, 0.5])
# wrong O: nowhere near circumcenter
O = np.array([-1.5, 1.5])

tri = np.array([A, B, C, A])
ax.plot(tri[:,0], tri[:,1], 'k-', lw=2)
ax.plot([A[0], M[0]], [A[1], M[1]], 'k-', lw=2)  # median only

for name, P in {'A':A,'B':B,'C':C,'H':H,'O':O,'M':M}.items():
    ax.plot(P[0], P[1], 'ko', ms=5)
    ax.text(P[0]+0.15, P[1]+0.15, name, fontsize=20)

ax.set_xlim(-4.5, 4.5)
ax.set_ylim(-2.5, 5.0)
