# -*- coding: utf-8 -*-
# Drawing service: code-generation pipeline for geometry diagrams.
#
# Pipeline overview (HTTP surface lives in routes/drawing.py):
#
#   1. Hash the problem text and look it up in an on-disk PNG cache.
#   2. Ask Claude Sonnet to author matplotlib code (text-only LLM call,
#      conversation kept in `messages` so future critiques continue the same
#      dialog).
#   3. Run that code inside services.sandbox (AST whitelist + subprocess).
#      If the sandbox raises, feed the traceback back to Claude (self-repair
#      loop, MAX_REPAIR_ITERS = 2 iterations).
#   4. NEW: critique stage.  Send (problem, code, PNG) to Gemini 2.5 Pro
#      (vision-capable) and ask for a structured list of geometric errors.
#      Gemini answers with JSON of findings.
#      For each round (MAX_CRITIQUE_ROUNDS = 2):
#         - If findings == []  -> stop, the drawing is good.
#         - Else send the findings back into the SAME Claude dialog with the
#           instruction "по каждой ошибке: согласись и исправь или
#           мотивированно отклони".  Claude returns updated code.
#           We re-run the sandbox (self-repair allowed inside this round).
#   5. Persist PNG to cache and log the run to DrawingGeneration.

from __future__ import annotations

import ast
import base64
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from services.openrouter_client import openrouter, OpenRouterError
from services.sandbox import (
    run_drawing_code,
    SandboxError,
    SandboxRejected,
    SandboxTimeout,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------- config

# Hard-coded per product decision: drawing pipeline runs on the newest Sonnet
# slug; do NOT make this env-configurable.  Fallback is DeepSeek (cheap) for
# the rare case the primary slug is unavailable on OpenRouter.
MODEL_PRIMARY = "anthropic/claude-opus-4.7"
MODEL_FALLBACK = None

# Critic model — vision-capable, geometry-aware.
# NOTE: in OpenRouter, Gemini 3.1 Pro is currently only exposed as the
# "-preview" SKU; the bare "google/gemini-3.1-pro" alias returns
# HTTP 400 "not a valid model ID".
MODEL_CRITIC = "google/gemini-3.1-pro-preview"

# Architect model: writes a detailed construction spec BEFORE Claude
# starts coding.  Same Gemini thinking model -- it spends a lot of
# tokens on reasoning, which is exactly what we want for "decompose
# the geometry problem into a step-by-step plan".  Output is plain
# Russian text, NOT JSON, because it goes into Claude's system context.
MODEL_ARCHITECT = "google/gemini-3.1-pro-preview"

# Critic stage is OFF by default (slow on Render Free Tier where the
# request timeout is ~100s).  Flip the env var to "1" / "true" to enable.
CRITIC_ENABLED = (os.environ.get("DRAWING_CRITIC_ENABLED", "0")
                  .strip().lower() in ("1", "true", "yes", "on"))

# Architect stage: runs BEFORE Claude.  Gemini (thinking) produces a
# detailed construction spec from the problem text, which is then fed
# to Claude as additional system context.  Adds ~15-25s and ~$0.05 per
# request but dramatically improves first-try success on multi-object
# problems (nine-point circle, inversion, etc.).  Defaults to whatever
# the critic toggle is set to -- "max quality" mode enables everything.
_arch_env = os.environ.get("DRAWING_ARCHITECT", "").strip().lower()
if _arch_env in ("1", "true", "yes", "on"):
    ARCHITECT_ENABLED = True
elif _arch_env in ("0", "false", "no", "off"):
    ARCHITECT_ENABLED = False
else:
    ARCHITECT_ENABLED = CRITIC_ENABLED

# Cosmetic critic is a SECOND pass that only looks at label/layout
# readability AFTER geometry is already clean.  It costs an extra
# ~$0.02-$0.04 + ~15-30 sec, so it has its own toggle.  When the env
# variable is missing, it defaults to ON whenever the main critic is
# also on -- that's the common production case where we want maximum
# quality.  Set DRAWING_COSMETIC_CRITIC=0 to disable it explicitly.
_cosmetic_env = os.environ.get("DRAWING_COSMETIC_CRITIC", "").strip().lower()
if _cosmetic_env in ("1", "true", "yes", "on"):
    COSMETIC_CRITIC_ENABLED = True
elif _cosmetic_env in ("0", "false", "no", "off"):
    COSMETIC_CRITIC_ENABLED = False
else:
    COSMETIC_CRITIC_ENABLED = CRITIC_ENABLED

# Repair budget for runtime/sandbox errors inside a single generation
# round. 4 is empirically enough to cover the long-tail of "Claude forgot
# a paren / missed a `:` / made a NameError" without burning the wall
# budget on the rare task where the model is fundamentally confused.
MAX_REPAIR_ITERS = 4
MAX_CRITIQUE_ROUNDS = 2       # how many times the critic is consulted
CACHE_TTL_SEC = 30 * 24 * 3600     # 30 days
CACHE_DIR_NAME = os.path.join("static", "generated", "cache")


SYSTEM_PROMPT = (
    "Ты пишешь Python-код на matplotlib для построения геометрических\n"
    "чертежей по русскоязычному условию задачи.\n"
    "\n"
    "ФОРМАТ ОТВЕТА: только ОДИН блок ```python ... ```. НИКАКОГО текста\n"
    "до этого блока. НИКАКОГО текста после этого блока. ПЛАН построения\n"
    "оформи как ПИТОНОВСКИЕ КОММЕНТАРИИ В НАЧАЛЕ КОДА, не как обычный\n"
    "русский абзац перед блоком. Если в твоём ответе нет блока\n"
    "```python``` — это критическая ошибка, ответ не будет принят.\n\n"
    "=== ОБЯЗАТЕЛЬНЫЙ ПЛАН ПОСТРОЕНИЯ (внутри кода как комментарии) ===\n"
    "Самой первой частью кода вставь блок-комментарий вида:\n"
    "    # === ПЛАН ПОСТРОЕНИЯ ===\n"
    "    # 1) <свободный параметр или базовая фигура и её координаты>\n"
    "    # 2) <следующая точка/линия и КАК она строится по условию>\n"
    "    # 3) ...\n"
    "    # === КОНЕЦ ПЛАНА ===\n"
    "В плане для КАЖДОЙ точки чертежа явно укажи:\n"
    "  (а) её роль из условия (середина BC, ортоцентр, основание высоты\n"
    "      из A на BC, центр описанной окружности, точка пересечения\n"
    "      двух окружностей и т.д.);\n"
    "  (б) точную формулу её координат через уже определённые точки\n"
    "      (через медианы/высоты/биссектрисы/центры окружностей).\n"
    "Свободные параметры (углы, начальные точки, радиусы окружностей,\n"
    "наклон секущих) ВЫБИРАЙ ОСМЫСЛЕННО, чтобы итоговые точки были\n"
    "ЯВНО РАЗДЕЛЕНЫ на чертеже (расстояние между любыми двумя\n"
    "именованными точками не меньше 12-15 процентов диагонали bounding\n"
    "box чертежа). НЕ выбирай параметры, которые делают прямую почти\n"
    "касательной к окружности, или две точки почти совпадающими.\n\n"
    "=== ПРОВЕРКА ПОСЛЕ КАЖДОЙ ТОЧКИ ===\n"
    "После определения каждой точки добавь assert-проверку, что\n"
    "построение действительно соответствует условию. Примеры:\n"
    "    assert abs(np.linalg.norm(M - B) - np.linalg.norm(M - C)) < 1e-6, \\\n"
    "        'M not midpoint of BC'\n"
    "    assert abs(np.linalg.norm(P - O) - R) < 1e-6, \\\n"
    "        'P not on circle (O, R)'\n"
    "    assert abs(np.dot(AH, BC)) < 1e-6, 'AH not perpendicular to BC'\n"
    "Если в условии явно дано численное соотношение (AH = 2*OM,\n"
    "угол A = 60°, AB = 5), добавь соответствующий assert.\n"
    "Asserts падают -> sandbox перезапросит код. Это лучше, чем\n"
    "молча выдать чертёж с ошибкой геометрии.\n\n"
    "=== ОГРАНИЧЕНИЯ КОДА ===\n"
    "- Разрешены только импорты: matplotlib, numpy, math.\n"
    "- Никаких import os/sys/subprocess/socket/requests, никаких open/exec/\n"
    "  eval, никаких сетевых вызовов или файловых операций.\n"
    "- Создавай ровно одну фигуру через plt.subplots(), без plt.show().\n"
    "- НЕ вызывай plt.savefig: обёртка сама сохранит plt.gcf() в PNG.\n\n"
    "=== СТИЛЬ ЧЕРТЕЖА ===\n"
    "- Чёрные линии 2 px на чисто белом фоне (#FFFFFF).\n"
    "- Шрифт подписей: sans-serif, 18-22 px, цвет чёрный.\n"
    "- Имена вершин — одиночные заглавные латинские буквы (A, B, C, …).\n"
    "- Двухбуквенные сочетания (AB, BC) — это отрезки, не вершины.\n"
    "- Длины подписывай числом без префикса (5, 7, …) рядом с серединой\n"
    "  соответствующего отрезка.\n"
    "- Углы рисуй дугами; подпись N° внутри угла.\n"
    "- Прямые углы — квадратиком, равные отрезки — короткими штрихами,\n"
    "  равные углы — двойными дугами.\n"
    "- Никаких теней, градиентов, цветных элементов кроме чёрного.\n\n"
    "=== ЧИТАЕМОСТЬ ПОДПИСЕЙ ===\n"
    "Подпись каждой именованной точки смещай от самой точки на 5-8\n"
    "процентов диагонали чертежа В СТОРОНУ, СВОБОДНУЮ ОТ ЛИНИЙ.\n"
    "После всех точек проверь попарные расстояния между подписями: если\n"
    "две подписи ближе 6 процентов диагонали друг к другу - разнеси их\n"
    "в разные стороны (одну вверх-влево, другую вниз-вправо). Подписи НЕ\n"
    "должны налегать на отрезки и дуги; если налегают - сдвинь подпись\n"
    "перпендикулярно линии.\n\n"
    "=== ГЕОМЕТРИЧЕСКАЯ КОРРЕКТНОСТЬ ===\n"
    "- Координаты вычисляй математически точно (теоремы синусов/косинусов,\n"
    "  свойства окружностей, формулы пересечений и т.д.).\n"
    "- Соблюдай пропорции: фигура должна выглядеть так, как описано в\n"
    "  условии, без визуальных искажений.\n"
    "- Не добавляй построений, которых нет в условии (высоты, биссектрисы\n"
    "  и т.п.), КРОМЕ тех, которые упомянуты явно.\n\n"
    "=== КАНВА ===\n"
    "plt.subplots(figsize=(10, 10), dpi=140), ax.set_aspect('equal'),\n"
    "ax.axis('off'). После рисования вычисли реальный bounding box всех\n"
    "объектов и подгоняй xlim/ylim с запасом 12 процентов от\n"
    "максимального габарита фигуры, чтобы НИ ОДНА точка/подпись не была\n"
    "обрезана краем."
)


CRITIC_SYSTEM_PROMPT = (
    "Ты — строгий ревьюер геометрических чертежей. Тебе дают:\n"
    "  (1) текст условия задачи на русском,\n"
    "  (2) исходный Python-код на matplotlib,\n"
    "  (3) PNG этого чертежа.\n"
    "\n"
    "Твоя задача — НАЙТИ ОШИБКИ ГЕОМЕТРИИ И ЧИТАЕМОСТИ. Тебя НЕ интересует\n"
    "стиль кода, его длина или эффективность. Не придирайся к незначительным\n"
    "косметическим мелочам.\n"
    "\n"
    "Ищи (в порядке важности):\n"
    "  * нарушения условия задачи (неверные длины, неверные углы, отсутствие\n"
    "    указанных в условии объектов, лишние построения, не упомянутые в\n"
    "    условии);\n"
    "  * математически неверное расположение точек (например, точка должна\n"
    "    лежать на окружности, но реально лежит вне её);\n"
    "  * несоответствие пропорций (фигура выглядит как другая фигура);\n"
    "  * перекрывающиеся подписи, нечитаемые названия вершин, отрезанные\n"
    "    краями полотна объекты.\n"
    "\n"
    "Не ищи микро-косметику (наклон шрифта, толщина линии в пикселе и т.п.).\n"
    "\n"
    "Верни ОТВЕТ СТРОГО В ВИДЕ ОДНОГО JSON-объекта без дополнительного текста\n"
    "и без markdown-fences, по схеме:\n"
    "\n"
    "  __OPEN_BRACE__\n"
    '    "findings": [ ... ]\n'
    "  __CLOSE_BRACE__\n"
    "\n"
    "где каждый элемент массива — объект:\n"
    "\n"
    "  __OPEN_BRACE__\n"
    '    "id": "f1",\n'
    '    "severity": "blocker" | "major" | "minor",\n'
    '    "title": "краткое название ошибки",\n'
    '    "detail": "конкретное описание: что в коде/чертеже неверно",\n'
    '    "fix_hint": "как именно нужно исправить"\n'
    "  __CLOSE_BRACE__\n"
    "\n"
    "ID должны быть уникальны (f1, f2, ...). Если ошибок не нашёл, верни\n"
    '__OPEN_BRACE__"findings": []__CLOSE_BRACE__.'
)
# `{` and `}` are kept as placeholders to avoid streaming-tool issues; they
# are substituted into real braces right after definition.
CRITIC_SYSTEM_PROMPT = (
    CRITIC_SYSTEM_PROMPT
    .replace("__OPEN_BRACE__", "{")
    .replace("__CLOSE_BRACE__", "}")
)


# Architect prompt: thinking model produces a fully-resolved
# construction spec.  We deliberately ask for plain Russian text in a
# numbered structure rather than JSON -- Claude reads it as natural
# language context.  The architect is allowed (and encouraged) to
# choose concrete numeric values for free parameters.
ARCHITECT_SYSTEM_PROMPT = (
    "Ты — архитектор геометрических чертежей. Тебе дают русскоязычное\n"
    "условие задачи. Твоя задача — НЕ рисовать и НЕ писать код, а выдать\n"
    "ДЕТАЛЬНОЕ ТЕХНИЧЕСКОЕ ЗАДАНИЕ для отдельного программиста, который\n"
    "потом напишет matplotlib-код. Программист — отличный кодер, но\n"
    "посредственный геометр; ему нужны разжёванные инструкции.\n"
    "\n"
    "Твой ответ — это PLAIN TEXT на русском (никакого JSON, никаких\n"
    "markdown-fences). Структура ответа ОБЯЗАТЕЛЬНО такая:\n"
    "\n"
    "## 1. КЛАССИФИКАЦИЯ ЗАДАЧИ\n"
    "Одно предложение: к какому классу относится задача (треугольник\n"
    "с описанной/вписанной/высотами, две пересекающиеся окружности,\n"
    "стереометрия и т.п.).\n"
    "\n"
    "## 2. ПЕРЕЧЕНЬ ВСЕХ ИМЕНОВАННЫХ ТОЧЕК\n"
    "Список вида:\n"
    "  A — вершина треугольника, свободный параметр (начнём с (0, 0))\n"
    "  B — вершина треугольника, свободный параметр (5, 0)\n"
    "  C — третья вершина, определяется из условия 'угол A = 60°, AC = 7'\n"
    "  H — ортоцентр, точка пересечения высот\n"
    "  H1 — основание высоты из A на BC\n"
    "  ...\n"
    "Для свободных параметров (точек/углов/радиусов, которые ты сам\n"
    "выбираешь) предложи КОНКРЕТНОЕ ЧИСЛЕННОЕ значение, выбранное так,\n"
    "чтобы все именованные точки на чертеже были ВИЗУАЛЬНО РАЗДЕЛЕНЫ\n"
    "(никаких 'почти касательных' и 'почти совпадающих' точек).\n"
    "\n"
    "## 3. ПОСЛЕДОВАТЕЛЬНОСТЬ ПОСТРОЕНИЯ\n"
    "Пронумерованный список шагов, в порядке зависимостей:\n"
    "  1. Зафиксировать координаты A и B как выше.\n"
    "  2. C = A + 7 * (cos 60°, sin 60°).\n"
    "  3. Высота из A: вектор перпендикулярный BC, основание H1 на BC.\n"
    "  4. ...\n"
    "Для каждой точки явно укажи ФОРМУЛУ её координат через предыдущие.\n"
    "Если требуется численный метод (пересечение прямой и окружности —\n"
    "квадратное уравнение, середина дуги — параметризация и т.п.) —\n"
    "распиши его кратко.\n"
    "\n"
    "## 4. ИНВАРИАНТЫ ДЛЯ ПРОВЕРКИ (asserts)\n"
    "Список условий, которые программист должен зафиксировать как\n"
    "assert после выполнения построения. Например:\n"
    "  - |M - B| = |M - C| (M — середина BC)\n"
    "  - |P - O| = R (P лежит на окружности с центром O и радиусом R)\n"
    "  - AH ⊥ BC (высота)\n"
    "  - угол A = 60° (по условию)\n"
    "Один инвариант — одна строка.\n"
    "\n"
    "## 5. ОБЪЕКТЫ ДЛЯ ОТРИСОВКИ\n"
    "Список того, что должно появиться на чертеже:\n"
    "  - треугольник ABC (три отрезка AB, BC, CA);\n"
    "  - описанная окружность с центром O радиуса R;\n"
    "  - вписанная окружность с центром I радиуса r;\n"
    "  - высота AH1 (отрезок A-H1);\n"
    "  - подписи всех именованных точек: A, B, C, H, H1, M, O.\n"
    "Если в условии явно требуется отметить угол, равенство отрезков,\n"
    "прямой угол — отметь это здесь же.\n"
    "\n"
    "## 6. ЗАМЕТКИ ПО ЧИТАЕМОСТИ\n"
    "Если предвидишь налегания подписей или другие косметические\n"
    "проблемы — укажи, в какую сторону смещать конкретные подписи\n"
    "(например, 'H ставить слева-вверху от точки H, потому что справа\n"
    "пройдёт высота AH1').\n"
    "\n"
    "Будь чёткими и конкретными. Никаких 'выберите подходящее\n"
    "значение' — выбирай сам и обосновывай. Никакого matplotlib-кода\n"
    "в ответе — это работа другого специалиста."
)


# Cosmetic critic: a SECOND pass run only after the geometry critic has
# converged (findings == []).  Its job is the opposite of the main critic
# above: it MUST ignore mathematics and ONLY look at readability --
# overlapping labels, labels colliding with lines, points/labels clipped
# by the canvas edge, illegible vertex names.  The follow-up revision is
# constrained to touch ONLY label offsets and xlim/ylim, never the
# geometry, so it cannot accidentally re-introduce geometric errors.
COSMETIC_CRITIC_SYSTEM_PROMPT = (
    "Ты — ревьюер ЧИТАЕМОСТИ геометрического чертежа. Тебе дают:\n"
    "  (1) текст условия задачи,\n"
    "  (2) исходный Python-код на matplotlib,\n"
    "  (3) PNG чертежа.\n"
    "\n"
    "Геометрия УЖЕ проверена другим ревьюером и признана правильной.\n"
    "Тебя НЕ интересуют: формулы координат, корректность построений,\n"
    "наличие/отсутствие элементов из условия. Об этом не сообщай.\n"
    "\n"
    "Ты ищешь ТОЛЬКО проблемы читаемости, в порядке важности:\n"
    "  * подписи точек, налегающие друг на друга;\n"
    "  * подписи, налегающие на линии/дуги, из-за чего буква неразличима;\n"
    "  * точки и подписи, обрезанные краем полотна;\n"
    "  * подпись находится с той же стороны, что и сходящиеся линии,\n"
    "    из-за чего читать сложно;\n"
    "  * слишком близко расположенные именованные точки.\n"
    "\n"
    "Если читаемость чертежа в норме — верни findings: []. Это нормально.\n"
    "\n"
    "Верни ОТВЕТ СТРОГО В ВИДЕ ОДНОГО JSON-объекта без markdown-fences:\n"
    "  __OPEN_BRACE__\n"
    '    "findings": [\n'
    "      __OPEN_BRACE__\n"
    '        "id": "c1",\n'
    '        "severity": "major" | "minor",\n'
    '        "title": "краткое название",\n'
    '        "detail": "что именно нечитаемо",\n'
    '        "fix_hint": "куда сдвинуть подпись или какой xlim/ylim"\n'
    "      __CLOSE_BRACE__\n"
    "    ]\n"
    "  __CLOSE_BRACE__\n"
)
COSMETIC_CRITIC_SYSTEM_PROMPT = (
    COSMETIC_CRITIC_SYSTEM_PROMPT
    .replace("__OPEN_BRACE__", "{")
    .replace("__CLOSE_BRACE__", "}")
)


# ------------------------------------------------------------------ result

@dataclass
class CritiqueFinding:
    id: str
    severity: str
    title: str
    detail: str
    fix_hint: str
    # filled after Claude responds
    claude_decision: Optional[str] = None      # "accepted" | "rejected"
    claude_reasoning: Optional[str] = None


@dataclass
class DrawingResult:
    image_bytes: bytes
    code: str
    model: Optional[str]
    cost_usd: float
    render_ms: int
    cache_hit: bool
    repair_iters: int
    critique_rounds: int = 0
    critique_findings: List[CritiqueFinding] = field(default_factory=list)
    critique_accepted: int = 0
    critique_rejected: int = 0
    attempts: List[dict] = field(default_factory=list)


# ------------------------------------------------------------------ helpers

_CODE_FENCE_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE
)
# Fallback: locate the first plausible matplotlib snippet inside an
# answer that forgot the markdown fence.  Anchored on `import matplotlib`
# or `import numpy` so we don't pick up shell text by accident.
_BARE_CODE_RE = re.compile(
    r"^[ \t]*(?:from\s+(?:matplotlib|numpy|math)|"
    r"import\s+(?:matplotlib|numpy|math))\b.*",
    re.MULTILINE | re.DOTALL,
)
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_code(text: str) -> Optional[str]:
    """Try multiple strategies to recover python from an LLM answer."""
    if not text:
        return None
    # 1) Standard markdown fence.
    m = _CODE_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    # 2) Whole answer starts with an import.
    s = text.strip()
    if s.startswith("import ") or s.startswith("from "):
        return s
    # 3) Answer has narrative text but an import appears later (Claude
    # sometimes forgets the fence after a long system-prompt update).
    # Grab everything from the first matplotlib/numpy/math import to
    # the end -- the sandbox will reject anything pathological.
    m2 = _BARE_CODE_RE.search(text)
    if m2:
        snippet = text[m2.start():].strip()
        # Strip trailing prose by chopping at a clearly non-python line
        # (a line that starts with a Cyrillic letter and ends with
        # punctuation other than ":" or ","). Heuristic, good enough.
        return snippet
    return None


def _ast_check(code: str) -> Optional[str]:
    """Return None if the snippet parses, otherwise a short, actionable
    error message with the offending line.  Used as a cheap pre-flight
    before the heavyweight sandbox so a missing paren can be reported to
    Claude WITH the right line context instead of just the raw
    'SyntaxError: was never closed' which is hard to fix blind."""
    try:
        ast.parse(code)
    except SyntaxError as e:
        lineno = getattr(e, "lineno", None) or 0
        offset = getattr(e, "offset", None) or 0
        msg = (e.msg or "syntax error").strip()
        # Pull a few surrounding lines so Claude can locate the bug.
        lines = code.splitlines()
        start = max(0, lineno - 3)
        end = min(len(lines), lineno + 2)
        context = []
        for i in range(start, end):
            marker = " >>>" if (i + 1) == lineno else "    "
            context.append("%s %4d | %s" % (marker, i + 1, lines[i]))
        return (
            "SyntaxError: " + msg
            + " (line " + str(lineno) + ", col " + str(offset) + ")\n"
            + "\n".join(context)
        )
    except (ValueError, TypeError) as e:
        return "ParseError: " + str(e)
    return None


def _problem_hash(problem: str) -> str:
    payload = (MODEL_PRIMARY + "::" + problem.strip()).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _cache_paths(app_root: str, sha: str):
    base = os.path.join(app_root, CACHE_DIR_NAME)
    os.makedirs(base, exist_ok=True)
    png = os.path.join(base, sha + ".png")
    meta = os.path.join(base, sha + ".meta.txt")
    return png, meta


def _read_cache(png_path: str, meta_path: str) -> Optional[tuple]:
    if not os.path.exists(png_path):
        return None
    if time.time() - os.path.getmtime(png_path) > CACHE_TTL_SEC:
        return None
    try:
        with open(png_path, "rb") as f:
            data = f.read()
        if not data or data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        code = ""
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                code = f.read()
        return data, code
    except OSError:
        return None


def _write_cache(png_path: str, meta_path: str, image_bytes: bytes, code: str):
    try:
        with open(png_path, "wb") as f:
            f.write(image_bytes)
        with open(meta_path, "w", encoding="utf-8") as f:
            f.write(code)
    except OSError as e:
        logger.warning("[drawing] failed to write cache: %s", e)


# ------------------------------------------------------------------ LLM


def _call_llm(messages: list, model: str) -> dict:
    """Return openrouter.chat() result with low temperature, JSON ignored.

    NOTE: max_tokens MUST be generous. With the QW-1 plan-and-asserts
    prompt + the architect spec injected as system context, Claude's
    output is routinely 120-180 lines of Python.  At max_tokens=2048
    Anthropic truncates mid-line and the AST pre-check fails forever
    (see the 2026-05-16 nine-point-circle incident: every repair
    iteration came back truncated on the same line).  8000 leaves
    comfortable headroom for the longest realistic drawing programmes.
    """
    return openrouter.chat(
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=8000,
    )


def _build_initial_messages(
    problem: str,
    architect_spec: Optional[str] = None,
) -> list:
    """Build the first prompt for Claude.

    If architect_spec is given, we inject it as an extra system message
    so Claude sees the construction plan BEFORE the user's problem text.
    The order matters: system-rules first, architect-spec second (so
    Claude treats it as authoritative guidance from the project), the
    actual problem last.
    """
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    if architect_spec:
        msgs.append({
            "role": "system",
            "content": (
                "Дополнительный контекст: внешний архитектор уже\n"
                "проанализировал задачу и составил техническое задание\n"
                "для построения. Используй его как АВТОРИТЕТНЫЙ источник\n"
                "координат, формул и инвариантов. Если найдёшь в нём\n"
                "ошибку — исправь, но используй структуру и список\n"
                "элементов оттуда.\n\n"
                "--- ТЕХНИЧЕСКОЕ ЗАДАНИЕ АРХИТЕКТОРА ---\n"
                + architect_spec.strip()
                + "\n--- КОНЕЦ ТЕХНИЧЕСКОГО ЗАДАНИЯ ---"
            ),
        })
    msgs.append({"role": "user", "content": problem.strip()})
    return msgs


def _get_architect_spec(problem: str) -> Tuple[Optional[str], float]:
    """Ask the architect model to produce a detailed construction spec.

    Returns: (spec_text or None, cost_usd).  Network/API failures are
    swallowed -- caller falls back to the no-spec path so the architect
    is strictly an enhancement, never a single point of failure.
    """
    try:
        resp = openrouter.chat(
            model=MODEL_ARCHITECT,
            messages=[
                {"role": "system", "content": ARCHITECT_SYSTEM_PROMPT},
                {"role": "user", "content": problem.strip()},
            ],
            temperature=0.0,
            # Architect is a thinking model: it spends ~1500-3000 tokens
            # on hidden reasoning before producing the spec.  Give it
            # plenty of headroom so the spec itself isn't truncated.
            max_tokens=8000,
        )
        content = (resp.get("content") or "").strip()
        cost = float(resp.get("cost_usd") or 0.0)
        # A useful spec contains at least the section headers we asked
        # for; if not, treat it as a degraded response and skip.
        if "ПЕРЕЧЕНЬ" not in content and "ПОСЛЕДОВАТЕЛЬНОСТЬ" not in content:
            logger.warning(
                "[drawing] architect returned content without expected "
                "section headers (%d chars); falling back to no-spec mode",
                len(content),
            )
            return None, cost
        return content, cost
    except OpenRouterError as e:
        logger.warning("[drawing] architect call failed: %s", e)
        return None, 0.0
    except Exception as e:  # pragma: no cover
        logger.warning("[drawing] architect unexpected error: %s", e)
        return None, 0.0


def _build_repair_user_msg(error_text: str) -> dict:
    return {
        "role": "user",
        "content": (
            "Код упал при выполнении. Вот traceback:\n"
            "```\n" + error_text.strip() + "\n```\n"
            "Исправь ошибку и верни ПОЛНЫЙ обновлённый код в одном\n"
            "блоке ```python```. Никаких пояснений."
        ),
    }


def _build_critique_user_msg(findings: List[CritiqueFinding]) -> dict:
    # Forward the structured critique back to Claude in the same dialog.
    lines = [
        "Внешний ревьюер (Gemini) посмотрел условие задачи, твой код и",
        "сгенерированный PNG. Он нашёл следующие замечания:",
        "",
    ]
    for f in findings:
        lines.append("[" + f.id + " | " + f.severity + "] " + f.title)
        lines.append("  Описание: " + f.detail)
        lines.append("  Подсказка по исправлению: " + f.fix_hint)
        lines.append("")
    lines.extend([
        "По каждой ошибке прими решение:",
        '  - если согласен — исправь её в коде;',
        '  - если НЕ согласен (ревьюер не прав) — оставь как было',
        "    и кратко объясни, почему отклонил.",
        "",
        "Верни ОТВЕТ В ДВУХ ЧАСТЯХ И ИМЕННО В ЭТОМ ПОРЯДКЕ:",
        "",
        "(1) Сводка решений в JSON-объекте без дополнительного текста:",
        '    {"decisions": [{"id": "f1", "decision": "accepted" | "rejected",',
        '                    "reason": "коротко"}]}',
        "",
        "(2) ПОЛНЫЙ обновлённый Python-код в блоке ```python```.",
        "    Если ты со всеми замечаниями не согласен — всё равно",
        "    выложи ТЕКУЩИЙ полный код (без изменений), не пропуская блок.",
    ])
    return {"role": "user", "content": "\n".join(lines)}


def _parse_decisions(text: str, findings: List[CritiqueFinding]) -> None:
    # Mutates `findings` in-place: sets claude_decision and claude_reasoning.
    if not text:
        return
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return
    by_id = {f.id: f for f in findings}
    for d in obj.get("decisions") or []:
        fid = d.get("id")
        if fid in by_id:
            decision = d.get("decision")
            if decision in ("accepted", "rejected"):
                by_id[fid].claude_decision = decision
            by_id[fid].claude_reasoning = (d.get("reason") or "")[:300]


# ------------------------------------------------------------------ critic


def _build_critic_messages(problem: str, code: str, png_bytes: bytes) -> list:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    data_url = "data:image/png;base64," + b64
    user_blocks = [
        {
            "type": "text",
            "text": (
                "Условие задачи:\n"
                "\"\"\"\n" + problem.strip() + "\n\"\"\"\n\n"
                "Исходный код, который нарисовал чертёж:\n"
                "```python\n" + code + "\n```\n\n"
                "Сам PNG прикреплён ниже. Проанализируй чертёж и верни\n"
                "findings строго в требуемом JSON-формате."
            ),
        },
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    return [
        {"role": "system", "content": CRITIC_SYSTEM_PROMPT},
        {"role": "user", "content": user_blocks},
    ]


def _parse_critique_response(text: str) -> List[CritiqueFinding]:
    if not text:
        return []
    m = _JSON_OBJECT_RE.search(text)
    if not m:
        return []
    try:
        obj = json.loads(m.group(0))
    except (ValueError, TypeError):
        return []
    out: List[CritiqueFinding] = []
    for i, f in enumerate(obj.get("findings") or []):
        out.append(CritiqueFinding(
            id=str(f.get("id") or ("f" + str(i + 1))),
            severity=str(f.get("severity") or "minor"),
            title=str(f.get("title") or "")[:200],
            detail=str(f.get("detail") or "")[:1000],
            fix_hint=str(f.get("fix_hint") or "")[:500],
        ))
    return out


def _critique_with_gemini(
    problem: str, code: str, png_bytes: bytes
) -> Tuple[List[CritiqueFinding], float]:
    """Returns (findings, cost_usd).  Raises OpenRouterError on transport
    failure — caller decides whether to swallow."""
    messages = _build_critic_messages(problem, code, png_bytes)
    # IMPORTANT: Gemini 3.x are "thinking" models -- they spend a sizeable
    # chunk of the completion budget on internal reasoning tokens that are
    # billed but NOT returned in `content`. Empirically the critic eats
    # ~2000 reasoning tokens before producing the JSON answer; with
    # max_tokens=1500 the visible content gets truncated mid-string and
    # `_parse_critique_response` silently returns []. 6000 leaves headroom
    # for reasoning + a long findings list and still caps cost at ~$0.04.
    resp = openrouter.chat(
        model=MODEL_CRITIC,
        messages=messages,
        temperature=0.0,
        max_tokens=6000,
    )
    content = (resp.get("content") or "").strip()
    findings = _parse_critique_response(content)
    return findings, float(resp.get("cost_usd") or 0.0)


def _build_cosmetic_critic_messages(
    problem: str, code: str, png_bytes: bytes
) -> list:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    data_url = "data:image/png;base64," + b64
    user_blocks = [
        {
            "type": "text",
            "text": (
                "Условие задачи:\n"
                "\"\"\"\n" + problem.strip() + "\n\"\"\"\n\n"
                "Исходный код (геометрия уже проверена и правильна):\n"
                "```python\n" + code + "\n```\n\n"
                "PNG прикреплён ниже. Найди ТОЛЬКО проблемы читаемости и\n"
                "верни findings в требуемом JSON-формате."
            ),
        },
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    return [
        {"role": "system", "content": COSMETIC_CRITIC_SYSTEM_PROMPT},
        {"role": "user", "content": user_blocks},
    ]


def _cosmetic_critique_with_gemini(
    problem: str, code: str, png_bytes: bytes
) -> Tuple[List[CritiqueFinding], float]:
    """Same shape as _critique_with_gemini, but uses the COSMETIC prompt."""
    messages = _build_cosmetic_critic_messages(problem, code, png_bytes)
    resp = openrouter.chat(
        model=MODEL_CRITIC,
        messages=messages,
        temperature=0.0,
        max_tokens=6000,
    )
    content = (resp.get("content") or "").strip()
    findings = _parse_critique_response(content)
    # Tag IDs so they don't collide with geometric findings when logged.
    for f in findings:
        if not f.id.startswith("c"):
            f.id = "c" + f.id
    return findings, float(resp.get("cost_usd") or 0.0)


def _build_cosmetic_revise_user_msg(findings: List[CritiqueFinding]) -> dict:
    """Ask Claude to fix ONLY label/layout issues, never geometry."""
    lines = [
        "Геометрия чертежа уже признана правильной и тебе её менять",
        "ЗАПРЕЩЕНО. Косметический ревьюер нашёл проблемы ЧИТАЕМОСТИ:",
        "",
    ]
    for f in findings:
        lines.append("[" + f.id + " | " + f.severity + "] " + f.title)
        lines.append("  Описание: " + f.detail)
        lines.append("  Подсказка: " + f.fix_hint)
        lines.append("")
    lines.extend([
        "СТРОГИЕ ОГРАНИЧЕНИЯ при исправлении:",
        "  - Координаты ИМЕНОВАННЫХ ТОЧЕК НЕ ТРОГАЙ (A, B, C, M, H, O, ...).",
        "  - Радиусы и центры окружностей НЕ ТРОГАЙ.",
        "  - Углы/наклоны/параметры построения НЕ ТРОГАЙ.",
        "  - Менять можно ТОЛЬКО:",
        "      * смещения подписей (ax.text(x, y, 'A', ...) — координаты\n"
        "        текста, но не координаты самой точки);",
        "      * xlim/ylim (расширить, если что-то обрезано);",
        "      * fontsize подписей в пределах 16-22;",
        "      * horizontalalignment / verticalalignment подписей.",
        "",
        "Верни ОТВЕТ В ДВУХ ЧАСТЯХ:",
        "(1) Сводка решений в JSON:",
        '    {"decisions": [{"id": "c1", "decision": "accepted" | "rejected",',
        '                    "reason": "коротко"}]}',
        "(2) ПОЛНЫЙ обновлённый код в блоке ```python```.",
    ])
    return {"role": "user", "content": "\n".join(lines)}


# ------------------------------------------------------------------ main flow


def _generate_code_until_renders(
    problem: str,
    messages: list,
    attempts: list,
    chosen_model: str,
) -> Tuple[bytes, str, str, list, float, int]:
    """
    Runs the LLM + sandbox + self-repair sub-loop.

    Returns: (png, code, used_model, messages_history, cost_usd_added, repair_iters_used)
    Raises:  SandboxError if the loop exhausts MAX_REPAIR_ITERS.
             OpenRouterError if every model candidate fails to respond at all.
    """
    total_cost = 0.0
    last_error = "unknown"
    last_code = ""

    for iteration in range(MAX_REPAIR_ITERS + 1):
        # --- LLM call (primary, then fallback) ---
        llm_resp = None
        for candidate in [c for c in (chosen_model, MODEL_FALLBACK) if c]:
            try:
                llm_resp = _call_llm(messages, candidate)
                chosen_model = candidate
                break
            except OpenRouterError as e:
                attempts.append({
                    "stage": "llm",
                    "iter": iteration,
                    "model": candidate,
                    "ok": False,
                    "error": str(e)[:300],
                })
                continue

        if llm_resp is None:
            raise OpenRouterError(
                "all LLMs failed for drawing code generation"
            )

        total_cost += float(llm_resp.get("cost_usd") or 0.0)
        content = (llm_resp.get("content") or "").strip()
        # keep dialog history honest
        messages = messages + [{"role": "assistant", "content": content}]

        code = _extract_code(content)
        if not code:
            last_error = "no python code block in LLM response"
            attempts.append({
                "stage": "extract",
                "iter": iteration,
                "model": chosen_model,
                "ok": False,
                "error": last_error,
            })
            messages = messages + [_build_repair_user_msg(last_error)]
            continue

        last_code = code

        # --- AST pre-flight (cheap, catches forgot-a-paren bugs without
        # spinning a subprocess; gives Claude the line number so the
        # repair iteration converges faster). ---
        ast_err = _ast_check(code)
        if ast_err is not None:
            last_error = ast_err
            attempts.append({
                "stage": "ast-check",
                "iter": iteration,
                "model": chosen_model,
                "ok": False,
                "error": last_error[:2000],
            })
            messages = messages + [_build_repair_user_msg(last_error)]
            continue

        # --- Sandbox execution ---
        try:
            image_bytes = run_drawing_code(code, timeout=12.0)
            attempts.append({
                "stage": "sandbox",
                "iter": iteration,
                "model": chosen_model,
                "ok": True,
            })
            return image_bytes, code, chosen_model, messages, total_cost, iteration
        except (SandboxRejected, SandboxTimeout, SandboxError) as e:
            last_error = type(e).__name__ + ": " + str(e)
            attempts.append({
                "stage": "sandbox",
                "iter": iteration,
                "model": chosen_model,
                "ok": False,
                "error": last_error[:2000],
            })
            messages = messages + [_build_repair_user_msg(last_error)]
            continue

    raise SandboxError(
        "drawing code-generation failed after "
        + str(MAX_REPAIR_ITERS)
        + " repair iterations; last error: "
        + last_error[:500]
    )


# ------------------------------------------------------------------ public


def generate_drawing(
    problem: str,
    *,
    app_root: Optional[str] = None,
    use_cache: bool = True,
) -> DrawingResult:
    """Run the full pipeline. Raises OpenRouterError or SandboxError."""
    started = time.time()
    problem = (problem or "").strip()
    if not problem:
        raise ValueError("empty problem")

    app_root = app_root or os.getcwd()
    sha = _problem_hash(problem)
    png_path, meta_path = _cache_paths(app_root, sha)

    # 1) Cache
    if use_cache:
        cached = _read_cache(png_path, meta_path)
        if cached is not None:
            data, code = cached
            return DrawingResult(
                image_bytes=data,
                code=code,
                model=None,
                cost_usd=0.0,
                render_ms=int((time.time() - started) * 1000),
                cache_hit=True,
                repair_iters=0,
                attempts=[{"stage": "cache", "ok": True}],
            )

    attempts: List[dict] = []
    total_cost = 0.0

    # 1.5) Architect stage (optional): Gemini produces a detailed
    # construction spec which is then fed to Claude as extra system
    # context.  Strictly additive -- if the architect call fails we
    # fall through to the legacy "Claude sees only the problem" path.
    architect_spec = None
    if ARCHITECT_ENABLED:
        arch_started = time.time()
        architect_spec, arch_cost = _get_architect_spec(problem)
        total_cost += arch_cost
        attempts.append({
            "stage": "architect",
            "model": MODEL_ARCHITECT,
            "ok": architect_spec is not None,
            "cost_usd": round(arch_cost, 6),
            "wall_ms": int((time.time() - arch_started) * 1000),
            "spec_chars": (len(architect_spec) if architect_spec else 0),
        })

    messages = _build_initial_messages(problem, architect_spec=architect_spec)

    # 2) First successful render
    image_bytes, code, used_model, messages, cost_added, repair_used = (
        _generate_code_until_renders(
            problem, messages, attempts, MODEL_PRIMARY,
        )
    )
    total_cost += cost_added
    total_repair_iters = repair_used

    # 3) Critique loop (Gemini Vision)
    all_findings: List[CritiqueFinding] = []
    rounds_done = 0
    accepted_total = 0
    rejected_total = 0

    _eff_rounds = MAX_CRITIQUE_ROUNDS if CRITIC_ENABLED else 0
    for round_idx in range(_eff_rounds):
        try:
            findings, critic_cost = _critique_with_gemini(
                problem, code, image_bytes
            )
            total_cost += critic_cost
            attempts.append({
                "stage": "critic",
                "round": round_idx,
                "model": MODEL_CRITIC,
                "ok": True,
                "findings_count": len(findings),
            })
        except OpenRouterError as e:
            # Critic failed — degrade gracefully, keep the current PNG.
            attempts.append({
                "stage": "critic",
                "round": round_idx,
                "model": MODEL_CRITIC,
                "ok": False,
                "error": str(e)[:300],
            })
            break

        if not findings:
            break  # drawing is clean
        rounds_done += 1

        # Ask Claude to revise (same dialog).
        messages = messages + [_build_critique_user_msg(findings)]
        try:
            new_png, new_code, used_model, messages, cost2, repair2 = (
                _generate_code_until_renders(
                    problem, messages, attempts, used_model,
                )
            )
        except (SandboxError, OpenRouterError) as e:
            # Revision failed.  Keep last good PNG.
            attempts.append({
                "stage": "critique-revise",
                "round": round_idx,
                "ok": False,
                "error": str(e)[:300],
            })
            all_findings.extend(findings)
            break

        total_cost += cost2
        total_repair_iters += repair2

        # Parse Claude's decision summary (the JSON before the code block).
        last_assistant_msg = next(
            (m for m in reversed(messages) if m.get("role") == "assistant"),
            None,
        )
        if last_assistant_msg:
            _parse_decisions(last_assistant_msg.get("content", ""), findings)

        # Tally decisions
        for f in findings:
            if f.claude_decision == "accepted":
                accepted_total += 1
            elif f.claude_decision == "rejected":
                rejected_total += 1
        all_findings.extend(findings)

        code = new_code
        image_bytes = new_png

    # 3b) Cosmetic critique pass (single round, after geometry is clean).
    # Runs only when the geometric critic produced no further findings
    # in its last call, so we know the math is already accepted.  Behind
    # its own toggle so unit tests that only stub _critique_with_gemini
    # don't accidentally hit the real OpenRouter API.
    cosmetic_findings_n = 0
    if COSMETIC_CRITIC_ENABLED:
        try:
            cos_findings, cos_cost = _cosmetic_critique_with_gemini(
                problem, code, image_bytes
            )
            total_cost += cos_cost
            cosmetic_findings_n = len(cos_findings)
            attempts.append({
                "stage": "cosmetic-critic",
                "model": MODEL_CRITIC,
                "ok": True,
                "findings_count": cosmetic_findings_n,
            })
            if cos_findings:
                # ONE revision round, no further cosmetic checks afterwards
                # (avoid endless ping-pong; cost cap ~$0.10 per revision).
                messages = messages + [
                    _build_cosmetic_revise_user_msg(cos_findings)
                ]
                try:
                    new_png, new_code, used_model, messages, cost3, repair3 = (
                        _generate_code_until_renders(
                            problem, messages, attempts, used_model,
                        )
                    )
                    total_cost += cost3
                    total_repair_iters += repair3
                    last_assistant_msg = next(
                        (m for m in reversed(messages)
                         if m.get("role") == "assistant"),
                        None,
                    )
                    if last_assistant_msg:
                        _parse_decisions(
                            last_assistant_msg.get("content", ""),
                            cos_findings,
                        )
                    for f in cos_findings:
                        if f.claude_decision == "accepted":
                            accepted_total += 1
                        elif f.claude_decision == "rejected":
                            rejected_total += 1
                    all_findings.extend(cos_findings)
                    code = new_code
                    image_bytes = new_png
                except (SandboxError, OpenRouterError) as e:
                    attempts.append({
                        "stage": "cosmetic-revise",
                        "ok": False,
                        "error": str(e)[:300],
                    })
                    all_findings.extend(cos_findings)
        except OpenRouterError as e:
            attempts.append({
                "stage": "cosmetic-critic",
                "model": MODEL_CRITIC,
                "ok": False,
                "error": str(e)[:300],
            })

    # 4) Cache + return
    if use_cache:
        _write_cache(png_path, meta_path, image_bytes, code)

    return DrawingResult(
        image_bytes=image_bytes,
        code=code,
        model=used_model,
        cost_usd=round(total_cost, 6),
        render_ms=int((time.time() - started) * 1000),
        cache_hit=False,
        repair_iters=total_repair_iters,
        critique_rounds=rounds_done,
        critique_findings=all_findings,
        critique_accepted=accepted_total,
        critique_rejected=rejected_total,
        attempts=attempts,
    )
