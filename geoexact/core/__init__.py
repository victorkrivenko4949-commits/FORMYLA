"""GeoExact core. Единственная задача этого файла — подключить к эксперту оценку
сложности и сторож первого токена (difficulty.install), не трогая llm.py.
GEOEXACT_DIFFICULTY_ROUTER=0 выключает оценку, GEOEXACT_FIRST_TOKEN_LIMIT=0 — сторож.
"""
from . import llm as _llm
from . import difficulty as _difficulty

_difficulty.install(_llm)
