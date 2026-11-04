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
  * acute_triangle.install — качественные условия: «остроугольный
    треугольник» (углы < 90°), «диаметрально противоположная» (антипод через
    центр описанной окружности), «точка лежит на отрезке/стороне»
    (принадлежность без слипания). Независимые проверки по тексту условия +
    правило 37 формализатора (иллюстративные углы, антипод, серединный
    перпендикуляр).
  * equidistant_repair.install — «BX=XD»: равноудалённая точка на прямой —
    пересечение с серединным перпендикуляром (правило 38 + детерминированный
    ремонт планов, где равенство закодировано окружностью line_circle —
    это добавляет |XU|=|UV| и переограничивает фигуру; ремонт — только для
    полностью распознанной по закрытому шаблону конфигурации, иначе no-op);
  * diameter_claims.install — «(полу)окружность с диаметром XY»: концы
    диаметра лежат НА окружности, центр — середина XY, отрезок XY виден
    из названных точек под прямым углом (Фалес), полуокружность — одна
    сторона прямой XY; правило 39 + проверка плана против текста (прод-ошибка:
    окружность «диаметра AD», построенная с центром A);
  * model_routes.install — формализатор (оба пути) на deepseek-v4-pro: перевод
    по просьбе пользователя после вырожденной конфигурации; классификация и
    оценка сложности не меняются, бюджетная деградация pro→flash сохранена.
    GEOEXACT_PRO_FORMALIZE=0 выключает; к ENGINE_VERSION дописывается суффикс.
  * bisector_angle.install — «биссектриса угла XYZ пересекает ... в точке
    T» (трёхбуквенный угол, любая фигура): углы XYT и TYZ равны, луч внутри
    угла; правило 40 — каноническое bisector_point + line_intersect
    (прод-ошибка: биссектриса в параллелограмме ушла под 19° вместо 30°);
  * named_labels.install — названная в условии точка не может быть скрытой:
    после чистки выдуманных подписей точки из текста возвращаются в
    draw.hide_labels; правило 41 (прод-ошибка: A_1/B_1/C_1 без подписей);
  * trapezoid.install — «трапеция ABCD»: основания параллельны (явные или по
    нотации AD ∥ BC), боковые равны у «равнобедренной»; правило 42 —
    свободные точки + parallel + dist вместо углов (прод-ошибка: фолбэк в
    схематичный чертёж с пропорциями 1:2 вместо 3:8);
  * special_position.install — незаявленные равенства сторон названного
    четырёхугольника/трапеции — частное положение (прод-ошибка: «докажите
    ∠AKX = ∠CKY» с AB = BC нарисован дельтоидом AD = CD); правило 44 —
    без симметрий, которых нет в тексте;
  * degenerate_policy.install — вырожденность с учётом семантики плана:
    совпадение построенных точек и коллинеарные «треугольники», объявленные
    конструкциями/ограничениями (D на продолжении CA, высота CH≡M при
    M=midpoint), больше не бракуют верный чертёж; отказ остаётся для
    совпадения двух свободных точек и необъявленного схлопнувшегося
    треугольника.
Выключатели: GEOEXACT_DIFFICULTY_ROUTER=0, GEOEXACT_FIRST_TOKEN_LIMIT=0,
GEOEXACT_GENERAL_POSITION=0, GEOEXACT_FORMALIZE_RULES=0, GEOEXACT_CONVEXITY=0,
GEOEXACT_INCIRCLE_TANGENTS=0, GEOEXACT_RADIUS_CLAIMS=0, GEOEXACT_LABEL_SUBSCRIPTS=0,
GEOEXACT_DEGENERATE_POLICY=0, GEOEXACT_GIVEN_ORDER=0,
GEOEXACT_ACUTE_TRIANGLE=0, GEOEXACT_PRO_FORMALIZE=0,
GEOEXACT_EQUIDISTANT=0, GEOEXACT_BISECTOR_ANGLE=0, GEOEXACT_NAMED_LABELS=0.
"""
from . import llm as _llm
from . import pipeline as _pipeline
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
from . import equidistant_repair as _equidistant_repair
from . import acute_triangle as _acute_triangle
from . import diameter_claims as _diameter_claims
from . import statement as _statement
from . import model_routes as _model_routes
from . import angle_marks_layout as _angle_marks_layout
from . import aux_view_marks as _aux_view_marks
from . import bisector_angle as _bisector_angle
from . import named_labels as _named_labels
from . import trapezoid as _trapezoid
from . import isosceles as _isosceles
from . import special_position as _special_position
from . import simson_line as _simson_line
from . import external_figures as _external_figures
from . import plan_repair as _plan_repair
from . import median_parallel as _median_parallel
from . import median_point as _median_point
from . import diametral_plan as _diametral_plan
from . import claim_arms as _claim_arms
from . import aux_safety as _aux_safety
from . import warnings_polish as _warnings_polish

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
_equidistant_repair.install(_llm)        # после given_order: равноудалённая точка — серединный перпендикуляр
_acute_triangle.install(_semantics, _llm)    # после radius_claims: острота, антипод, принадлежность отрезку
_diameter_claims.install(_semantics, _llm, _pipeline, _statement)  # после acute_triangle: диаметр — Фалес, центр-середина и отрезок в чертеже
_model_routes.install(_llm, _pipeline)        # после acute_triangle: путь A формализатора на v4-pro
_bisector_angle.install(_semantics, _llm, _pipeline)   # после model_routes: биссектриса угла + суффикс кэша
_named_labels.install(_pipeline, _llm)       # после bisector_angle: названные точки с подписями + суффикс кэша
_trapezoid.install(_semantics, _llm, _pipeline)  # после named_labels: основания трапеции параллельны + суффикс кэша
_isosceles.install(_semantics, _llm, _pipeline)     # после trapezoid: боковые равнобедренного равны + суффикс кэша
_special_position.install(_semantics, _llm, _pipeline)  # после isosceles: незаявленные равенства сторон + суффикс кэша
_simson_line.install(_semantics, _llm, _pipeline)      # после special_position: прямая Симсона — спец-план без LLM, хорда line_circle — отказ + суффикс кэша
_external_figures.install(_semantics, _llm, _pipeline)  # после simson_line: внешние квадраты — правило 46 + проверка стороны + суффикс кэша
_plan_repair.install(_semantics, _llm, _pipeline)       # после external_figures: порядок конструкций (FORWARD_REF) + якорь line_circle_other + правила 47/48 + суффикс
_median_parallel.install(_semantics, _llm, _pipeline)    # после plan_repair: точка с отношением на медиане + параллель — спец-план без LLM + суффикс
_median_point.install(_llm, _pipeline)    # после median_parallel: ремонт медианы на середину правильной стороны + правило 49 + суффикс
_diametral_plan.install(_semantics, _llm, _pipeline)   # после median_parallel: диаметральная D + равноудалённые X/Y — канонический план без LLM + суффикс
_claim_arms.install(_semantics, _llm, _pipeline)      # после diametral_plan: плечи и дуги углов из утверждения — на чертёж + суффикс
_aux_safety.install(_pipeline)   # подстраховка aux-режима: провал со схемой -> базовый чертёж с объяснением
_warnings_polish.install(_pipeline)   # самый внешний слой: предупреждения — без кодов, нормальным языком
