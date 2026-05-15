import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.fix_bare_latex_in_db import fix_text

samples = [
    "В треугольнике ABC угол A равен 30^{\\circ}, а сторона AB равна 12 см.",
    "Найдите \\frac{1}{2} плюс \\frac{1}{3}.",
    "Уже хорошо: \\(x^2 + y^2 = z^2\\), без изменений.",
    "Решение: a_{1} + a_{2} = 5.",
    "Чисто текст без математики.",
    "Угол \\angle ABC равен 45^{\\circ} и сторона a^2 + b^2.",
    "Площадь S = \\frac{1}{2}ab\\sin C, где C - угол.",
]
for s in samples:
    print("IN: ", s)
    print("OUT:", fix_text(s))
    print()
