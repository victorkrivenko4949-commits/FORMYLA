"""GeoExact core. Этот файл подключает к движку обёртки, не трогая llm.py,
solver.py и gates.py:
  * difficulty.install — оценка сложности задачи (Luna/Sol) и сторож первого токена;
  * general_position.install — чертёж в общем положении: без случайных равных
    сторон и прямых углов, без слипшихся точек;
  * formalize_rules.install — дополнительные правила формализатора (внешняя
    биссектриса, параллель через точку, запрет получать вершины треугольника
    конструкциями друг из друга);
  * convexity.install — выпуклость названных многоугольников: семантическая
    проверка контура, opposite_side для выпуклого четырёхугольника и гладкий
    штраф решателя для same_side/opposite_side;
  * incircle_tangents.install — касательные из точек прямой стороны к вписанной
    окружности: правила формализатора (reflect_line вместо tangent_point), точный
    план для семьи «биссектрисы угла и смежного → B1, B2 → касательные K1, K2»,
    причина исходного отказа в предупреждении эскиза (FALLBACK_FROM);
  * radius_claims.install — «XY равен радиусу/диаметру описанной (вписанной)
    окружности треугольника PQR» проверяется по координатам, правила 33–35
    формализатора (радиус через circumcenter/incenter + dist_eq);
  * label_subscripts.install — подписи точек B_1, K_2, I_A с настоящим нижним
    индексом вместо буквального «B_1».
  * given_order.install — «равны a и b соответственно»: правило формализатора и
    пост-проверка плана; перепутанный порядок данных длин исправляется сам
    (обмен значений двух dist-ограничений и их подписей) с пометкой в notes.
  * degenerate_policy.install — вырожденность с учётом семантики плана:
    совпадение построенных точек и коллинеарные «треугольники», объявленные
    конструкциями/ограничениями (D на продолжении CA, высота CH≡M при
    M=midpoint), больше не бракуют верный чертёж; отказ остаётся для
    совпадения двух свободных точек и необъявленного схлопнувшегося
    треугольника.
Выключатели: GEOEXACT_DIFFICULTY_ROUTER=0, GEOEXACT_FIRST_TOKEN_LIMIT=0,
GEOEXACT_GENERAL_POSITION=0, GEOEXACT_FORMALIZE_RULES=0, GEOEXACT_CONVEXITY=0,
GEOEXACT_INCIRCLE_TANGENTS=0, GEOEXACT_RADIUS_CLAIMS=0, GEOEXACT_LABEL_SUBSCRIPTS=0,
GEOEXACT_DEGENERATE_POLICY=0, GEOEXACT_GIVEN_ORDER=0.
"""
from . import llm as _llm
from . import difficulty as _difficulty
from . import solver as _solver
from . import gates as _gates
from . import general_position as _general_position
from . import formalize_rules as _formalize_rules
from . import render as _render
from . import bisector_marks as _bisector_marks
from . import semantics as _semantics
from . import convexity as _convexity
from . import incircle_tangents as _incircle_tangents
from . import radius_claims as _radius_claims
from . import degenerate_policy as _degenerate_policy
from . import label_subscripts as _label_subscripts
from . import given_order as _given_order
from . import angle_marks_layout as _angle_marks_layout
from . import aux_view_marks as _aux_view_marks

_difficulty.install(_llm)
_general_position.install(_solver, _gates)
_formalize_rules.install(_llm)
_bisector_marks.install(_render)
_convexity.install(_semantics, _llm, solver_module=_solver)
_degenerate_policy.install(_solver, _semantics)   # после convexity: свой суффикс версии
_incircle_tangents.install(_semantics, _llm)
_radius_claims.install(_semantics, _llm)
_label_subscripts.install(_render)   # после bisector_marks: самый внешний слой рендера
_angle_marks_layout.install(_render)   # после label_subscripts: дуга/подпись широкого угла
_aux_view_marks.install(_render)       # после angle_marks_layout: в виде с построением полная длина скрыта, если куски отмечены
_given_order.install(_llm)             # после formalize_rules: порядок «соответственно» данных длин
