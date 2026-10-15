"""GeoExact core. Этот файл подключает к движку обёртки, не трогая llm.py,
solver.py и gates.py:
  * difficulty.install — оценка сложности задачи (Luna/Sol) и сторож первого токена;
  * general_position.install — чертёж в общем положении: без случайных равных
    сторон и прямых углов, без слипшихся точек;
  * formalize_rules.install — дополнительные правила формализатора (внешняя
    биссектриса, параллель через точку, запрет получать вершины треугольника
    конструкциями друг из друга).
Выключатели: GEOEXACT_DIFFICULTY_ROUTER=0, GEOEXACT_FIRST_TOKEN_LIMIT=0,
GEOEXACT_GENERAL_POSITION=0, GEOEXACT_FORMALIZE_RULES=0.
"""
from . import llm as _llm
from . import difficulty as _difficulty
from . import solver as _solver
from . import gates as _gates
from . import general_position as _general_position
from . import formalize_rules as _formalize_rules

_difficulty.install(_llm)
_general_position.install(_solver, _gates)
_formalize_rules.install(_llm)
