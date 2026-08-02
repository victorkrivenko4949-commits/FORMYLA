"""Code-first diagram generators for FORMYLA course assets.

Each generator is a pure function (params: dict) -> matplotlib.figure.Figure.
The caller saves to disk and runs QA. Generators must never call plt.show()
or touch the filesystem.

Strict geometry naming rules (Russian course):
    - окружность ω, окружность Ω
    - описанная окружность треугольника ABC
    - окружность с диаметром AB
    - окружность с центром O радиуса r
No decorative circle names. Latin single-letter vertex labels.
"""

from .registry import GENERATORS, get_generator

__all__ = ["GENERATORS", "get_generator"]
