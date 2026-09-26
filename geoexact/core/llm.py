"""Этапы 2 и 4: единственные места, где работает LLM.

Модель НЕ рисует и НЕ считает координаты. Она только:
  - классифицирует задачу (этап 2)
  - переводит текст в FigurePlan (этап 4)

Учёт стоимости честный, по фактическим токенам ответа API.
"""
from __future__ import annotations

import json
import os
import re
import time
import math
import threading
from datetime import datetime, timezone
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter

from .schema import FigurePlan, PlanError, plan_json_schema, validate_plan

BASE = "https://api.deepseek.com"

# Verified 2026-09-22: https://api-docs.deepseek.com/quick_start/pricing
# Off-peak USD / 1M; budget admission ALWAYS uses twice these (peak).
PRICES = {
    "deepseek-v4-flash": {"in": 0.15, "cached": 0.003, "out": 0.60},
    "deepseek-v4-pro": {"in": 0.66, "cached": 0.022, "out": 1.98},
}

# Маршрутизация: класс сложности -> (модель, лимит вывода) для каждого пути
ROUTES = {
    # путь A: без доп. построений — только формализация
    ("A", "S"):  ("deepseek-v4-flash", 4000),
    ("A", "M"):  ("deepseek-v4-flash", 6000),
    ("A", "L"):  ("deepseek-v4-flash", 8000),
    ("A", "XL"): ("deepseek-v4-pro", 10000),
    # путь B: с доп. построениями — модель обязана решить задачу
    ("B", "S"):  ("deepseek-v4-flash", 6000),
    ("B", "M"):  ("deepseek-v4-flash", 10000),
    ("B", "L"):  ("deepseek-v4-pro", 12000),
    ("B", "XL"): ("deepseek-v4-pro", 16000),
}

# ВАЖНО: в thinking mode токены рассуждения входят в completion_tokens и,
# значит, в max_tokens. Тесный лимит обрезает JSON на середине — отказ выглядит
# как BAD_JSON, хотя модель работала правильно. Лимиты пути B подняты с запасом;
# Вход и все повторные попытки тоже входят в бюджет.

BUDGET_HARD_CAP = 0.10  # $ на один запрос пользователя
_API_SLOTS = threading.BoundedSemaphore(4)
_START_LOCK = threading.Lock()
_LAST_START = 0.0

# Модели, для которых провайдер не принял параметр thinking
# (HTTP 400 с упоминанием «thinking») — повтор идёт без параметра.
_THINKING_UNSUPPORTED: set[str] = set()


def _post_limited(sess, payload):
    """Independent CPU workers, bounded API concurrency and safe 429 backoff."""
    global _LAST_START
    with _API_SLOTS:
        for attempt in range(3):
            with _START_LOCK:
                delay = .35 - (time.monotonic() - _LAST_START)
                if delay > 0:
                    time.sleep(delay)
                _LAST_START = time.monotonic()
            r = sess.post(f"{BASE}/chat/completions", timeout=(15, 180), json=payload)
            if r.status_code != 429 or attempt == 2:
                return r
            try:
                delay = min(20, max(1, float(r.headers.get("Retry-After", 2 ** (attempt + 1)))))
            except (ValueError, TypeError):
                delay = 2 ** (attempt + 1)
            time.sleep(delay)


def make_session() -> requests.Session:
    s = requests.Session()
    # Production package uses standard requests TLS validation, not sandbox CA.
    s.mount("https://", HTTPAdapter(pool_maxsize=8))
    # Optional deployment environment. Never embed this value in a client bundle.
    if os.getenv("DEEPSEEK_API_KEY"):
        s.headers["Authorization"] = "Bearer " + os.environ["DEEPSEEK_API_KEY"]
    return s


@dataclass
class Usage:
    model: str = ""
    stage: str = ""
    tok_in: int = 0
    tok_cached: int = 0
    tok_out: int = 0
    cost: float = 0.0
    seconds: float = 0.0
    rate_multiplier: float = 1.0

    @staticmethod
    def of(model: str, stage: str, u: dict, seconds: float,
           multiplier: float = 1.0) -> "Usage":
        p = PRICES[model]
        total = max(0, u.get("prompt_tokens", 0) or 0)
        cached = min(total, max(0, u.get("prompt_cache_hit_tokens", 0) or 0))
        fresh = total - cached
        out = u.get("completion_tokens", 0) or 0
        cost = multiplier * (fresh * p["in"] + cached * p["cached"] + out * p["out"]) / 1e6
        return Usage(model, stage, fresh, cached, out, cost, seconds, multiplier)


@dataclass
class Budget:
    """Контроль лимита на уровне запроса, а не отдельного вызова."""
    cap: float = BUDGET_HARD_CAP
    spent: float = 0.0
    calls: list[Usage] = field(default_factory=list)
    uncertain: bool = False

    def __post_init__(self):
        if not math.isfinite(self.cap) or self.cap <= 0 or self.cap > BUDGET_HARD_CAP:
            raise PlanError("BAD_BUDGET", "лимит должен быть в (0, 0.10]")

    def add(self, u: Usage) -> None:
        self.spent += u.cost
        self.calls.append(u)

    @property
    def left(self) -> float:
        return self.cap - self.spent

    def can_afford(self, model: str, max_out: int, input_bound: int = 16000) -> bool:
        """Peak rates, no cache discount; byte bound on the COMPLETE prompt."""
        p = PRICES[model]
        est = 2 * (input_bound * p["in"] + max_out * p["out"]) / 1e6
        return not self.uncertain and est <= self.left

    @property
    def seconds(self) -> float:
        return sum(c.seconds for c in self.calls)


# ------------------------------------------------------------------ промпты
# Статика идёт ПЕРВОЙ и неизменной — так работает кэш промпта (в 10 раз дешевле).
SYS_FORMALIZE = """Ты переводишь условие планиметрической задачи в JSON-план построения чертежа.
Ты НЕ вычисляешь координаты. Координаты найдёт геометрический движок по твоим ограничениям.

Доступны ТОЛЬКО следующие операции. Ничего другого использовать нельзя:

""" + plan_json_schema() + """

ФОРМАТ ОТВЕТА — один JSON-объект, без markdown-обёртки:
{
  "space": "plane",
  "points": ["A","B","C"],
  "constructions": [{"op":"free_point","out":"A"}, ...],
  "constraints": [{"type":"dist","args":["A","B"],"value":6}, ...],
  "draw": {"segments":[["A","B"],["B","C"],["C","A"]], "aux_segments":[],
           "circles":[], "aux_circles":[], "right_angles":[],
           "angle_marks":[{"pts":["B","A","C"],"text":"60°"}],
           "length_marks":[{"pts":["A","B"],"text":"6"}], "hide_labels":[]},
  "target": {"kind":"angle","args":["B","A","C"]},
  "scale_free": false,
  "notes": ""
}

ЖЁСТКИЕ ПРАВИЛА:
1. Каждая точка из points обязана быть построена ровно одной конструкцией.
2. Конструкции идут в топологическом порядке: ссылаться можно только на уже построенные точки.
3. Базовую фигуру задавай через free_point + ограничения. Всё, что выводится
   однозначно (середина, основание перпендикуляра, центр окружности, пересечение) —
   через конструкцию, а НЕ через ограничения. Конструкция точна, ограничение приближённо.
4. Сохраняй ВСЕ условия, включая принадлежность отрезку и сторону прямой.
   Недостаток уравнений допускает иллюстративный пример; избыток не обязательно
   противоречив. НЕ добавляй равенства или симметрию, которых нет в условии.
5. Если в условии нет конкретных длин (задача на подобие) — поставь scale_free: true
   и задай удобный масштаб через одну dist, чтобы фигура была определена.
6. angle всегда в ГРАДУСАХ, вершина угла — ВТОРАЯ точка в args.
7. Подписывай на чертеже только то, что дано в условии: length_marks и angle_marks
   для известных величин. Искомую величину НЕ подписывай.
8. Окружность задаётся РОВНО двумя ИМЕНАМИ точек из points: [центр, точка на окружности].
   Радиус числом ЗАПРЕЩЁН. Если точки на окружности нет — объяви её в points
   и построй. В draw, constraints и target разрешены ТОЛЬКО имена из points:
   слова вроде "center", "O1", "tangent" без объявления — ошибка.
9. Если условие противоречиво либо нужная операция не поддерживается, верни
   {"error":"UNSUPPORTED_CONSTRUCTION", "notes":"объяснение"} и ничего больше.
10. Можно рисовать бесконечные lines и rays (пары точек), aux_lines/aux_rays,
    aux_points (новые точки только для решения); equal_marks:
    [{"pts":["A","B"],"count":1,"layer":"main"}] ставит засечки равных длин.
    arcs: [{"center":"O","start":"A","end":"B","reflex":false,"layer":"main"}].
    У angle_marks допустимы count (1..3), reflex (true для >180°), layer.
    У length_marks допустим layer. Числовые метки должны совпадать с геометрией.
11. Все отрезки, точки, биссектрисы и высоты, которые УЖЕ даны в условии,
    принадлежат основному слою, даже в режиме B. В A не добавляй решение.
    Отметки прямых углов задавай right_angles; не заменяй ими непрямые углы.
12. Для точки НА ОТРЕЗКЕ используй on_segment, а не только collinear.
    Для выпуклого четырёхугольника контролируй расположение по сторонам
    диагоналей с помощью opposite_side. Не подменяй его перекрещенным.
13. circle_circle(out,[O,R1,P,R2],value): центры O и P, радиусы |OR1| и |PR2|.
    Это НЕ список двух центров, повторённый дважды! Для числовых радиусов создай
    R1=perp_point(O,O,P,r1), R2=perp_point(P,O,P,r2); скрой их подписи.
    Радиусные служебные точки не надо рисовать как самостоятельные объекты.
    Для двух точек пересечения используй одну пару окружностей и value=0 и 1.
14. Условие может быть просто фигурой без чисел и вопроса («треугольник ABC»,
    «трапеция ABCD», «окружность с центром O»). Это НЕ ошибка: построй типовую
    невырожденную конфигурацию через free_point, задай масштаб одной удобной
    dist и поставь scale_free: true. Выдуманных подписей длин и углов не ставь.
15. Если точка P лежит на стороне UV, а угол между OP и OQ известен, НЕ
    оставляй P свободной точкой с on_segment + angle: это тяжёлая
    плохо обусловленная система. Построй вспомогательную точку R на луче:
    {"op":"angle_ray","out":"R","args":["O","Q"],"value":theta}.
    angle_ray принимает РОВНО ДВА аргумента: вершину O и точку Q,
    задающую базовый луч OQ; value — ЗНАКОВЫЙ поворот в градусах против
    часовой стрелки. Затем P = пересечение прямых UV и OR:
    {"op":"line_intersect","out":"P","args":["U","V","O","R"]}.
    R добавь в points и draw.hide_labels, P строй только один раз;
    on_segment(P,U,V) и angle(P,O,Q)=abs(theta) оставь ограничениями
    для проверки выбранной ветви. Если P оказывается вне UV, смени знак
    theta для этой точки. Для двух таких точек нужны ДВА разных
    вспомогательных имени R и S. Пример: D на AC при угле DBC=60°:
    R=angle_ray(B,C,+60); D=line_intersect(A,C,B,R), если ABC
    ориентирован против часовой стрелки. E на AB при ECB=50°:
    S=angle_ray(C,B,-50); E=line_intersect(A,B,C,S).
    Не выдумывай длины в length_marks; произвольный dist для масштаба
    допустим только как не подписанная калибровка.
16. bisector_point(A,B,C) возвращает точку НА BC, а НЕ на описанной
    окружности. Для второго пересечения биссектрисы угла A с описанной
    окружностью ABC используй bisector_circumcircle(out=W,args=[A,B,C]).
    Если длины сторон в условии не заданы, НЕ выдумывай три длины:
    scale_free=true и не больше одной произвольной dist для масштаба."""

SYS_AUX = SYS_FORMALIZE + """

РЕЖИМ ДОПОЛНИТЕЛЬНЫХ ПОСТРОЕНИЙ.
Сначала реши задачу про себя. Затем определи, какое вспомогательное построение
действительно нужно для решения (высота, медиана, продолжение стороны, средняя линия,
описанная окружность, поворот, симметрия, параллельная прямая).
Это построение добавь конструкциями и положи в aux_segments / aux_circles —
НЕ в основной слой segments. В notes одной строкой напиши идею решения
на русском: зачем нужно это построение.

В segments идёт ВСЯ исходная фигура из условия, включая уже заданные
высоты, биссектрисы, медианы и диагонали. Всё, чего в условии нет, а ты добавил для решения
— высота, медиана, биссектриса, средняя линия, описанная окружность, радиус,
продолжение стороны, параллельная прямая — идёт только в aux_*.
Если дополнительное построение НЕ нужно, оставь aux_* пустыми и объясни в notes.
Нельзя искусственно переносить данную биссектрису в aux или придумывать лишнюю.
Все добавленные точки перечисли в draw.aux_points. Метки на новых построениях
должны иметь layer:"aux", чтобы их можно было скрыть вместе с построением."""

SYS_CLASSIFY = """Классифицируй геометрическую задачу. Ответ — только JSON, без пояснений:
{"space":"plane"|"space","class":"S"|"M"|"L"|"XL","needs_aux":true|false,"ok":true|false,"reason":""}
space: "space" для стереометрии (куб, призма, пирамида, сфера, тетраэдр).
class: S — 1-2 объекта, прямое применение формулы; M — стандартная задача, 3-5 объектов;
L — много объектов или неочевидная конфигурация; XL — олимпиадная, нестандартная.
needs_aux: нужно ли для решения вспомогательное построение.
ok: true для ЛЮБОГО связного геометрического описания, даже короткого и без
вопроса или числовых данных: «треугольник ABC», «ромб ABCD», «окружность с
диаметром AB» — это запрос чертежа фигуры, а не ошибка. Отсутствие вопроса,
длин или углов НЕ делает условие некорректным.
ok: false только если текст вообще не про геометрию, это бессмысленный набор
символов или условие внутренне противоречиво."""


def _chat(sess, model: str, system: str, user: str, max_out: int,
          stage: str, budget: Budget, temperature: float = 0.0,
          thinking: bool = False) -> tuple[str, Usage]:
    # thinking здесь больше не управляет запросом: см. _THINKING_FIX ниже.
    input_bound = len((system + user).encode("utf-8")) + 512
    if not budget.can_afford(model, max_out, input_bound):
        raise PlanError("BUDGET_EXCEEDED", f"остаток ${budget.left:.4f} не покрывает вызов {model}")
    t0 = time.time()
    now = datetime.now(timezone.utc)
    multiplier = 2.0 if now.weekday() < 5 and (1 <= now.hour < 4 or 6 <= now.hour < 10) else 1.0
    reserve = 2 * (input_bound * PRICES[model]["in"] + max_out * PRICES[model]["out"]) / 1e6
    # GEOEXACT_MODEL_FIX: тело запроса повторяет проверенную форму AI-тьютора
    # (services/atlas_tutor.py): model/messages/temperature/max_tokens
    # (+ response_format json_object — сайт уже использует это в проде).
    # GEOEXACT_THINKING_FIX: модели DeepSeek v4 по умолчанию «думают» перед
    # ответом: reasoning-токены входят в completion_tokens (обрезка JSON —
    # TRUNCATED) и растягивают каждый вызов на минуты. Для JSON-планов мышление
    # не нужно — отключаем тем же параметром, что и services/llm_router.py
    # (работает в проде на api.deepseek.com). Если провайдер параметр не знает —
    # помечаем и повторяем без него.
    payload = {"model": model, "max_tokens": max_out, "temperature": temperature,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}],
               "response_format": {"type": "json_object"}}
    if model not in _THINKING_UNSUPPORTED:
        payload["thinking"] = {"type": "disabled"}
    try:
        r = _post_limited(sess, payload)
    except requests.RequestException as e:
        budget.uncertain = True
        budget.spent += reserve  # upper-bound reservation, NOT a verified API charge
        raise PlanError("NETWORK_UNCERTAIN", "ответ API не получен; стоимость неизвестна, автоповтор запрещён") from e
    if r.status_code == 400 and model not in _THINKING_UNSUPPORTED \
            and "thinking" in (r.text or "").lower():
        # Провайдер не знает параметр thinking — повторяем без него.
        _THINKING_UNSUPPORTED.add(model)
        payload.pop("thinking", None)
        try:
            r = _post_limited(sess, payload)
        except requests.RequestException as e:
            budget.uncertain = True
            budget.spent += reserve
            raise PlanError("NETWORK_UNCERTAIN", "ответ API не получен; стоимость неизвестна, автоповтор запрещён") from e
    dt = time.time() - t0
    if r.status_code != 200:
        if r.status_code >= 500:
            budget.uncertain = True
            budget.spent += reserve
        raise PlanError("API_ERROR", f"HTTP {r.status_code}")
    try:
        d = r.json()
        if not isinstance(d.get("usage"), dict):
            raise ValueError("missing usage")
        raw_usage = d["usage"]
        for key in ("prompt_tokens", "completion_tokens"):
            if type(raw_usage.get(key)) is not int or raw_usage[key] < 0:
                raise ValueError("invalid usage counters")
        if "prompt_cache_hit_tokens" in raw_usage:
            cached = raw_usage["prompt_cache_hit_tokens"]
            if type(cached) is not int or not 0 <= cached <= raw_usage["prompt_tokens"]:
                raise ValueError("invalid cached count")
        u = Usage.of(model, stage, d["usage"], dt, multiplier)
    except (ValueError, KeyError, TypeError) as e:
        budget.uncertain = True
        budget.spent += reserve
        raise PlanError("API_BAD_RESPONSE", "нет достоверного учёта токенов; автоповтор запрещён") from e
    budget.add(u)
    try:
        ch = d["choices"][0]
        content = ch["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise PlanError("API_BAD_RESPONSE", "в ответе API нет content") from e
    if ch.get("finish_reason") == "length":
        raise PlanError("TRUNCATED",
                        f"ответ обрезан лимитом {max_out} токенов "
                        f"(модель {model} израсходовала {u.tok_out})")
    return content, u


def _parse_json(text: str) -> dict:
    if not isinstance(text, str):
        raise PlanError("BAD_JSON", "ответ должен быть текстом JSON")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text)
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise PlanError("BAD_JSON", "модель вернула не JSON")
        try:
            d = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise PlanError("BAD_JSON", "повреждённый JSON") from e
    if not isinstance(d, dict):
        raise PlanError("BAD_JSON", "ожидался JSON-объект, не массив")
    return d


# ------------------------------------------------------------------ этап 2
def classify(sess, problem: str, budget: Budget) -> dict:
    """Классификация с запасом лимита и одним повтором.

    Раньше лимит был 300 токенов: reasoning-токены модели входят в
    completion_tokens и съедали весь лимит, JSON обрезался — TRUNCATED
    БЕЗ права на повтор (этап 2 не ретраится в конвейере). Теперь
    стартовый запас 4000 и повтор на 12000.
    """
    d = None
    for max_out in (4000, 12000):
        try:
            txt, _ = _chat(sess, "deepseek-v4-flash", SYS_CLASSIFY, problem,
                            max_out, "classify", budget)
            d = _parse_json(txt)
            break
        except PlanError as e:
            # Повтор имеет смысл только для обрезки/битого JSON;
            # бюджет и сбои API повторять бессмысленно или опасно.
            if e.code not in ("TRUNCATED", "BAD_JSON", "BAD_CLASSIFICATION"):
                raise
    if d is None:
        raise PlanError("BAD_CLASSIFICATION", "классификация не удалась после повтора")
    d.setdefault("space", "plane")
    d.setdefault("class", "M")
    d.setdefault("needs_aux", False)
    d.setdefault("ok", True)
    if d["class"] not in ("S", "M", "L", "XL") or d["space"] not in ("plane", "space"):
        raise PlanError("BAD_CLASSIFICATION", "недопустимый класс или пространство")
    if not isinstance(d["ok"], bool):
        raise PlanError("BAD_CLASSIFICATION", "ok должен быть boolean")
    return d


# ------------------------------------------------------------------ этап 4
def formalize(sess, problem: str, cls: str, with_aux: bool, budget: Budget,
              feedback: str = "", prev_code: str = "") -> tuple[FigurePlan, list[str]]:
    path = "B" if with_aux else "A"
    model, max_out = ROUTES.get((path, cls), ROUTES[(path, "M")])
    if feedback:
        # A repeated malformed formalization needs reasoning, not the same
        # deterministic non-thinking response with a slightly longer prompt.
        max_out = max(max_out, 8000)
    if prev_code == "TRUNCATED":
        # Предыдущий ответ упёрся в лимит токенов и был обрезан —
        # повтор с тем же лимитом обрежется так же. Даём заметно больше места.
        max_out = min(max(max_out * 2, 8000), 24000)
    # деградация модели, если бюджета не хватает
    if not budget.can_afford(model, max_out) and model == "deepseek-v4-pro":
        model, max_out = "deepseek-v4-flash", min(max_out, 16000)
    system = SYS_AUX if with_aux else SYS_FORMALIZE
    user = problem if not feedback else (
        f"{problem}\n\nПРЕДЫДУЩАЯ ПОПЫТКА ОТКЛОНЕНА ДВИЖКОМ: {feedback}\n"
        "Исправь план. Верни полный JSON заново.")
    bound = len((system + user).encode("utf-8")) + 512
    if not budget.can_afford(model, max_out, bound) and model == "deepseek-v4-pro":
        model, max_out = "deepseek-v4-flash", min(max_out, 16000)
    txt, _ = _chat(sess, model, system, user, max_out, f"formalize-{path}", budget,
                  thinking=(bool(feedback) or cls in ("L", "XL") or (with_aux and cls == "M")))
    d = _parse_json(txt)
    if "error" in d:
        raise PlanError(str(d["error"]), d.get("notes", ""))
    plan = FigurePlan.from_dict(d)
    warn = validate_plan(plan)          # этап 5
    if not (plan.draw.segments or plan.draw.lines or plan.draw.rays
            or plan.draw.circles or any(a.get("layer", "main") == "main" for a in plan.draw.arcs)):
        raise PlanError("EMPTY_DRAW", "план не содержит основной геометрии для рисунка")
    aux_marks = any(m.get("layer") == "aux"
                    for group in (plan.draw.arcs, plan.draw.angle_marks,
                                  plan.draw.length_marks, plan.draw.equal_marks)
                    for m in group)
    if not with_aux and (plan.draw.aux_segments or plan.draw.aux_circles
                         or plan.draw.aux_lines or plan.draw.aux_rays or plan.draw.aux_points or aux_marks):
        raise PlanError("UNREQUESTED_AUX", "режим A не должен содержать дополнительные построения")
    return plan, warn


def formalize_space(sess, problem: str, cls: str, with_aux: bool, budget: Budget,
                    feedback: str = "", prev_code: str = "") -> dict:
    from .space3d import scene_schema_prompt
    model, max_out = ROUTES.get(("B" if with_aux else "A", cls), ROUTES[("A", "M")])
    if feedback:
        # Повторная формализация после отказа движка — нужен запас на рассуждение.
        max_out = max(max_out, 8000)
    if prev_code == "TRUNCATED":
        # Предыдущий ответ был обрезан лимитом токенов — повтор с тем же
        # лимитом обрежется так же, даём заметно больше места.
        max_out = min(max(max_out * 2, 8000), 24000)
    system = ("Переведи геометрическую задачу в точную параметрическую 3D-сцену. "
              "Никаких координат от модели. НЕ заменяй произвольную пирамиду правильной. "
              "Не выдумывай размеры. Если данных мало, верни error: NEEDS_CLARIFICATION. "
              "Если фигура не поддерживается, верни error: UNSUPPORTED_SOLID. "
              "Данные в условии линии относятся к main, только новые к aux. "
              "Режим aux=" + str(with_aux) + ". Только JSON.\n" + scene_schema_prompt())
    user = problem + (("\nИсправь отказ движка: " + feedback) if feedback else "")
    bound = len((system + user).encode()) + 512
    if not budget.can_afford(model, max_out, bound) and model == "deepseek-v4-pro":
        model, max_out = "deepseek-v4-flash", min(max_out, 8000)
    text, _ = _chat(sess, model, system, user, max_out, "formalize-3D", budget,
                    thinking=cls in ("L", "XL"))
    d = _parse_json(text)
    if "error" in d:
        raise PlanError(str(d["error"]), str(d.get("notes", "")))
    return d
