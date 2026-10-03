"""GeoExact core. Единственная задача этого файла — подключить оценку
сложности к эксперту (difficulty.install), не трогая llm.py.
GEOEXACT_DIFFICULTY_ROUTER=0 выключает этап.
"""
from . import llm as _llm
from . import difficulty as _difficulty

_difficulty.install(_llm)
