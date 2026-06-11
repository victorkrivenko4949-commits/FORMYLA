# -*- coding: utf-8 -*-
"""services/ai_tutor_review.py — единый сервис AI-проверки решения ученика.

Используется и из /api/check_adaptive_answer (адаптивный тест), и из
/daily_tasks/<id>/submit_ai (задачи дня), чтобы UX был «1-в-1».

Публичная функция: :func:`review_attempt`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Soft import sympy (optional) ────────────────────────────────────────
try:
    import sympy
    _HAS_SYMPY = True
except Exception:  # pragma: no cover
    sympy = None  # type: ignore[assignment]
    _HAS_SYMPY = False


# ── Промпты ───────────────────────────────────────────────────────────

SYSTEM_PROMPT_PROOF = (
    "Ты — проверяющий математических доказательств платформы FORMYLA.\n\n"
    "ЗАДАЧА УЧЕНИКА — ДОКАЗАТЬ УТВЕРЖДЕНИЕ.\n\n"
    "═══ ГЛАВНОЕ ПРАВИЛО: ЭТАЛОН — ИСТИНА ═══\n"
    "Эталонные solution и answer из базы — ИСТИНА. НЕ решай задачу заново\n"
    "и не пересчитывай. Сравнивай ответ/решение ученика с эталонным answer.\n"
    "Вывод о правильности и feedback строй ТОЛЬКО от эталона, а не от своих вычислений.\n\n"
    "АЛГОРИТМ:\n"
    "1. Прочитай условие — пойми, что нужно доказать.\n"
    "2. Прочитай эталонное решение — пойми идею.\n"
    "3. Прочитай решение ученика — проверь логику.\n"
    "4. У доказательства может быть много путей. Ученик не обязан повторять эталон.\n\n"
    "КРИТИЧЕСКИ ВАЖНО:\n"
    "- Утверждение верное (иначе его не просили бы доказать). НЕ опровергай его.\n"
    "- Оценивай логику ученика, а не совпадение с эталоном.\n"
    "- Корректное доказательство — answer_correct: true, method_correct: true.\n"
    "- Идея верная, но пробелы — answer_correct: false, method_correct: true.\n"
    "- Грубая ошибка / пустое — answer_correct: false, method_correct: false.\n\n"
    "ФОРМАТ ОТВЕТА — СТРОГО JSON (без markdown):\n"
    '{"answer_correct": true/false, "method_correct": true/false, '
    '"category": "correct|wrong_answer_wrong_method|wrong_answer_good_method|'
    'correct_no_justification|blank|suspicious", '
    '"confidence": 0.0-1.0, "error_location": "... или null", '
    '"feedback": "..."}\n\n'
    "ПОЛЯ:\n"
    "- answer_correct: верен ли ответ ученика.\n"
    "- method_correct: верен ли метод/рассуждение (даже если ответ неверен).\n"
    "- category: одна из: correct, wrong_answer_wrong_method, "
    "wrong_answer_good_method, correct_no_justification, blank, suspicious.\n"
    "- confidence: насколько уверен в оценке (0.0-1.0). "
    "Если сомневаешься (< 0.6) — укажи низкий confidence.\n"
    "- error_location: конкретное место ошибки (строка/шаг) или null.\n"
    "- feedback: 1-2 фразы ученику.\n\n"
    "FEEDBACK без LaTeX (никаких \\frac, \\sqrt, $...$, \\(...\\)).\n"
    "Используй простой текст: x^2, 1/2, sqrt(5), >=, <=, !=, alpha, pi.\n"
    "Будь конструктивным и понятным школьнику.\n"
)


SYSTEM_PROMPT_NUMERIC = (
    "Ты — проверяющий математических задач платформы FORMYLA.\n"
    "У тебя ЕСТЬ правильный ответ из БД. Сравни ответ ученика с каноном.\n\n"
    "═══ ГЛАВНОЕ ПРАВИЛО: ЭТАЛОН — ИСТИНА ═══\n"
    "Эталонные solution и answer из базы — ИСТИНА. НЕ решай задачу заново\n"
    "и не пересчитывай. Сравнивай ответ ученика с эталонным answer.\n"
    "Вывод о правильности и feedback строй ТОЛЬКО от эталона, а не от своих вычислений.\n\n"
    "КРИТИЧЕСКИ ВАЖНО:\n"
    "- ЗАПРЕЩЕНО решать заново своим способом.\n"
    "- ЗАПРЕЩЕНО утверждать, что канонический ответ неверен.\n"
    "- Доверяй полю \"Правильный ответ\" — это истина из БД.\n\n"
    "ФОРМАТ ОТВЕТА — СТРОГО JSON (без markdown):\n"
    '{"answer_correct": true/false, "method_correct": true/false, '
    '"category": "correct|wrong_answer_wrong_method|wrong_answer_good_method|'
    'correct_no_justification|blank|suspicious", '
    '"confidence": 0.0-1.0, "error_location": "... или null", '
    '"feedback": "..."}\n\n'
    "ПОЛЯ:\n"
    "- answer_correct: верен ли ответ ученика.\n"
    "- method_correct: верен ли метод/рассуждение (даже если ответ неверен).\n"
    "- category: одна из: correct, wrong_answer_wrong_method, "
    "wrong_answer_good_method, correct_no_justification, blank, suspicious.\n"
    "- confidence: насколько уверен в оценке (0.0-1.0). "
    "Если сомневаешься (< 0.6) — укажи низкий confidence.\n"
    "- error_location: конкретное место ошибки (строка/шаг) или null.\n"
    "- feedback: 1-2 фразы ученику.\n\n"
    "СРАВНЕНИЕ:\n"
    "- Ответ ученика в формате LaTeX или текстом.\n"
    "- Сравнивай МАТЕМАТИЧЕСКОЕ значение.\n"
    "- 20.23 == 20,23 == 20.230.\n"
    "- \\frac{1}{2} == 0.5 == 0,5.\n"
    "- \\sqrt{4} == 2.\n"
    "- Игнорируй пробелы, скобки, форматирование.\n\n"
    "FEEDBACK:\n"
    "- Если ответ совпал — начинай с \"Ответ верный!\".\n"
    "- НИКОГДА не пиши \"Ответ неверный\", если числа совпали.\n"
    "- Пиши математику простым текстом: x^2, 1/2, sqrt(5), >=, alpha, pi.\n"
    "- Никаких \\frac, \\sqrt, \\cdot, \\left, $, \\(, \\[ и т.п.\n"
    "- **жирный** для ключевых слов (Шаг 1:, Ответ:).\n"
    "- Переносы строк для шагов.\n"
    "- НЕ оборачивай JSON в markdown-блоки.\n"
)


def get_tutor_prompt(*, proof_mode: bool) -> str:
    """Вернуть system-промпт для AI-тьютора.

    Единая точка истины — используется и из services/ai_tutor_review,
    и из app.py (чтобы не было рассинхрона дублирующихся промптов).

    Args:
        proof_mode: True для задач-доказательств, False для числовых.
    Returns:
        Строка system_prompt.
    """
    return SYSTEM_PROMPT_PROOF if proof_mode else SYSTEM_PROMPT_NUMERIC


# ── Math-equivalence quick check ──────────────────────────────────────

def is_proof_task(task_text: str, correct_answer: str) -> bool:
    """True если задача — на доказательство (без числового ответа)."""
    ca = (correct_answer or "").strip().lower()
    tt = (task_text or "").lower()
    return (
        ca in ("доказательство", "доказать", "proof", "")
        or "докажите" in tt
        or "доказать" in tt
        or "покажите, что" in tt
        or "покажите что" in tt
        or "обоснуйте" in tt
    )


def math_equivalent(user: str, canon: str) -> bool:
    """Эквивалентны ли два ответа (числа/дроби/пробелы)."""
    if not user or not canon:
        return False
    u = user.strip()
    c = canon.strip()
    if not u or not c:
        return False
    norm = lambda s: re.sub(r"\s+", "", s).lower().replace(",", ".")
    if norm(u) == norm(c):
        return True
    num_re = re.compile(r"-?\d+(?:[.,]\d+)?(?:/\d+)?")

    def _to_floats(s: str) -> List[float]:
        out: List[float] = []
        for m in num_re.findall(s):
            t = m.replace(",", ".")
            try:
                if "/" in t:
                    a, b = t.split("/", 1)
                    out.append(float(a) / float(b))
                else:
                    out.append(float(t))
            except Exception:
                pass
        return out

    uns = _to_floats(u)
    cns = _to_floats(c)
    if not uns or not cns:
        return False
    if len(uns) == len(cns):
        if all(
            abs(a - b) <= max(1e-4, 1e-3 * max(abs(a), abs(b)))
            for a, b in zip(sorted(uns), sorted(cns))
        ):
            return True
    if len(cns) == 1 and any(
        abs(x - cns[0]) <= max(1e-4, 1e-3 * max(abs(x), abs(cns[0])))
        for x in uns
    ):
        return True
    return False


def _safe_truncate_solution(text: str, max_len: int = 1500) -> str:
    """Обрезает длинное эталонное решение, не рвём LaTeX."""
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    tail = text[:max_len]
    for marker in ("\\)", "\\]", ".\n", "\n\n", ". ", "\n"):
        idx = tail.rfind(marker)
        if idx > max_len * 0.6:
            return text[: idx + len(marker)] + " …"
    return tail + " …"


# ── OCR фото-решения через DeepSeek vision ────────────────────────────

def transcribe_photos(images_b64: List[str], task_text: str, deepseek_client_cls) -> str:
    """Распознаёт каждое фото и склеивает в строку."""
    if not images_b64 or deepseek_client_cls is None:
        return ""
    try:
        client = deepseek_client_cls()
    except Exception as e:
        logger.warning("transcribe_photos: cannot init client: %s", e)
        return ""
    parts: List[str] = []
    total = len(images_b64)
    for idx, img_b64 in enumerate(images_b64, start=1):
        try:
            part = client.transcribe_handwritten_solution(
                image_data=img_b64, task_text=task_text or ""
            )
        except Exception as e:
            logger.warning("transcribe photo #%d failed: %s", idx, e)
            part = ""
        if part:
            if total > 1:
                parts.append("--- Фото %d из %d ---\n%s" % (idx, total, part))
            else:
                parts.append(part)
    return "\n\n".join(parts).strip()


# ── Парсинг JSON-ответа DeepSeek ──────────────────────────────────────

def _safe_json_parse(raw: str) -> Dict[str, Any]:
    """Парсит JSON-ответ DeepSeek даже если внутри строк сырой LaTeX."""
    s = re.sub(r"```json\s*", "", (raw or "").strip())
    s = re.sub(r"```\s*", "", s).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    def _fix(m: "re.Match[str]") -> str:
        content = m.group(0)
        return re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", content)

    s_fixed = re.sub(r'"(?:[^"\\]|\\.)*"', _fix, s, flags=re.DOTALL)
    try:
        return json.loads(s_fixed)
    except json.JSONDecodeError:
        pass
    score_m = re.search(r'"score"\s*:\s*(-?\d+)', s)
    fb_m = re.search(r'"feedback"\s*:\s*"(.*?)"(?=\s*[,}])', s, re.DOTALL)
    if score_m:
        fb = fb_m.group(1) if fb_m else "Ответ проверен."
        fb = fb.replace("\\n", "\n").replace('\\"', '"')
        return {"score": int(score_m.group(1)), "feedback": fb}
    raise json.JSONDecodeError("Cannot parse AI response", s, 0)


# ── Sanitize feedback — убираем LaTeX ─────────────────────────────────

def sanitize_feedback_no_latex(s: str) -> str:
    """Конвертирует LaTeX в человекочитаемый текст для рендера без KaTeX."""
    if not s:
        return s
    t = s
    # 1) делимитеры
    t = t.replace("\\(", " ").replace("\\)", " ")
    t = t.replace("\\[", "\n").replace("\\]", "\n")
    t = re.sub(r"\$\$([^$]*)\$\$", r"\1", t, flags=re.DOTALL)
    t = re.sub(r"\$([^$\n]+)\$", r"\1", t)
    # 2) \frac{a}{b} -> (a)/(b)
    for cmd in ("dfrac", "tfrac", "frac"):
        pat = r"\\" + cmd + r"\s*\{([^{}]*)\}\s*\{([^{}]*)\}"
        for _ in range(4):
            new_t = re.sub(pat, r"(\1)/(\2)", t)
            if new_t == t:
                break
            t = new_t
    # 3) \sqrt
    t = re.sub(r"\\sqrt\s*\[([^\]]*)\]\s*\{([^{}]*)\}", r"root_\1(\2)", t)
    t = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"sqrt(\1)", t)
    # 4) \left \right
    t = t.replace("\\left", "").replace("\\right", "")
    # 5) операторы
    repl = [
        ("\\cdot", "·"), ("\\times", "×"), ("\\div", "÷"), ("\\pm", "±"),
        ("\\le", "≤"), ("\\leq", "≤"), ("\\ge", "≥"), ("\\geq", "≥"),
        ("\\ne", "≠"), ("\\neq", "≠"), ("\\approx", "≈"), ("\\equiv", "≡"),
        ("\\infty", "∞"), ("\\to", "→"), ("\\Rightarrow", "⇒"),
        ("\\Leftrightarrow", "⇔"), ("\\in", "∈"), ("\\notin", "∉"),
        ("\\subset", "⊂"), ("\\cup", "∪"), ("\\cap", "∩"),
        ("\\forall", "∀"), ("\\exists", "∃"), ("\\sum", "Σ"), ("\\prod", "∏"),
        ("\\int", "∫"), ("\\lim", "lim"), ("\\log", "log"), ("\\ln", "ln"),
        ("\\sin", "sin"), ("\\cos", "cos"), ("\\tan", "tg"), ("\\cot", "ctg"),
        ("\\alpha", "α"), ("\\beta", "β"), ("\\gamma", "γ"), ("\\delta", "δ"),
        ("\\epsilon", "ε"), ("\\theta", "θ"), ("\\lambda", "λ"), ("\\mu", "μ"),
        ("\\pi", "π"), ("\\rho", "ρ"), ("\\sigma", "σ"), ("\\tau", "τ"),
        ("\\phi", "φ"), ("\\omega", "ω"),
        ("\\overline", ""), ("\\underline", ""), ("\\vec", ""),
        ("\\hat", ""), ("\\bar", ""), ("\\tilde", ""),
        ("\\pmod", "mod"), ("\\bmod", "mod"),
        ("\\quad", " "), ("\\qquad", "  "), ("\\,", " "), ("\\;", " "),
        ("\\!", ""), ("\\:", " "), ("\\ ", " "),
    ]
    for src, dst in repl:
        t = t.replace(src, dst)
    # 6) \text{...}
    t = re.sub(r"\\text\s*\{([^{}]*)\}", r"\1", t)
    # 7) остальные команды
    t = re.sub(r"\\[A-Za-z]+\s*\{([^{}]*)\}", r"\1", t)
    t = re.sub(r"\\[A-Za-z]+", "", t)
    # 8) одинокие фигурные
    t = re.sub(r"\{([^{}]*)\}", r"\1", t)
    # 9) косметика
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


# ── Stage 2: sympy comparison helpers ──────────────────────────────────

def _clean_latex_for_sympy(text: str) -> str:
    """Очищает LaTeX-разметку перед передачей в sympy.sympify.

    Берёт подход из find_irrational_answers.py + answer_normalizer.py:
    - удаляет \\( \\), \\[ \\], $$, $
    - конвертит \\frac{a}{b} → (a)/(b), \\sqrt{x} → sqrt(x)
    - заменяет ^ → **, запятую-разделитель → точка
    - убирает лишние команды (\\cdot, \\left, \\right и т.п.)
    """
    if not text:
        return ""
    t = text.strip()
    # 1) LaTeX math-mode markers
    t = re.sub(r'\\\(|\\\)|\\\[|\\\]', '', t)
    t = re.sub(r'\$\$|\$', '', t)
    # 2) Trailing period (LaTeX sentence punctuation)
    t = t.rstrip('.')
    # 3) \frac{a}{b} → (a)/(b)
    t = re.sub(
        r'\\(?:dfrac|tfrac|frac)\s*\{([^{}]*)\}\s*\{([^{}]*)\}',
        r'(\1)/(\2)',
        t,
    )
    # 4) \sqrt{x} → sqrt(x)
    t = re.sub(r'\\sqrt\s*\{([^{}]*)\}', r'sqrt(\1)', t)
    # 5) ^ → ** (sympy exponentiation)
    t = t.replace('^', '**')
    # 6) Comma decimal → dot (only between digits)
    t = re.sub(r'(?<=\d),(?=\d)', '.', t)
    # 7) Remove leftover LaTeX commands (\cdot, \left, \right, \displaystyle, etc.)
    t = re.sub(
        r'\\(?:cdot|times|left|right|big|Big|bigg|Bigg|quad|qquad|displaystyle'
        r'|text|textbf|mathit|mathrm|underline)\s*',
        '',
        t,
    )
    # 8) Remove remaining backslash-commands (e.g. \alpha → alpha for sympy)
    #    But keep pi → pi, etc.
    t = re.sub(r'\\([a-zA-Z]+)', r'\1', t)
    # 9) Squeeze all whitespace
    t = re.sub(r'\s+', '', t)
    return t


def _compare_with_sympy(
    user_answer: str,
    correct_answer: str,
) -> Tuple[Optional[bool], bool]:
    """Сравнить ответ ученика с эталоном СЕМАНТИЧЕСКИ через sympy.

    Args:
        user_answer:     ответ ученика (строка, возможно с LaTeX).
        correct_answer:  канонический ответ из БД.

    Returns:
        Кортеж (is_correct, needs_ai):
            (None, False)   — пустой ответ → blank (ни sympy, ни ИИ не нужны).
            (True, False)   — sympy подтвердил равенство → ВЕРНО.
            (False, False)  — sympy опроверг равенство → НЕВЕРНО.
            (None, True)    — sympy не смог распарсить → нужен ИИ.
    """
    # --- Empty ---
    user = (user_answer or '').strip()
    canon = (correct_answer or '').strip()
    if not user or not canon:
        return None, False

    if not _HAS_SYMPY:
        return None, True  # sympy not installed → AI fallback

    # --- Clean LaTeX ---
    cleaned_user = _clean_latex_for_sympy(user)
    cleaned_canon = _clean_latex_for_sympy(canon)
    if not cleaned_user or not cleaned_canon:
        return None, False

    # Non-math answers (Russian words) → skip sympy
    if re.search(r'[а-яА-ЯёЁ]', cleaned_user):
        return None, True

    # --- Sympify ---
    try:
        expr_user = sympy.sympify(cleaned_user, strict=False)
        expr_canon = sympy.sympify(cleaned_canon, strict=False)
    except Exception:
        # sympy can't parse → AI fallback
        return None, True

    # --- Compare ---
    try:
        diff = sympy.simplify(expr_user - expr_canon)
        if diff == 0:
            return True, False   # structurally equal

        # Numeric fallback (handles surds where simplify fails)
        if getattr(expr_user, 'is_number', False) and getattr(expr_canon, 'is_number', False):
            try:
                numeric_diff = abs(complex(sympy.N(expr_user - expr_canon, 30)))
                if numeric_diff < 1e-9:
                    return True, False
            except Exception:
                pass

        # Set / multiset: if both are free of symbols and not equal → not correct
        return False, False

    except Exception:
        return None, True


# ── Score computation (единая шкала) ─────────────────────────────────

def _compute_score(
    *,
    answer_correct: bool,
    method_correct: bool,
    has_solution: bool,
    difficulty_level: int = 5,
) -> float:
    """Вычислить финальный балл по единой шкале.

    Изменено по ТЗ FORMYLA:
      • Верный ответ ВСЕГДА даёт минимум +1 балл (даже без обоснования),
        полное решение даёт +2 (1.0 во float-шкале).
      • Неверный ответ даёт 0 баллов (без отрицательных значений).

    Таблица:
      пусто/"не знаю"                              → 0.0
      answer_correct=False, method_correct=*       → 0.0  (минимум 0, не −1)
      answer_correct=True,  has_solution=True      → 1.0  (→ +2 балла во фронте)
      answer_correct=True,  has_solution=False     → 0.5  (→ +1 балл во фронте)
    """
    # Неверный ответ → 0. Никаких отрицательных оценок.
    if not answer_correct:
        return 0.0
    # answer_correct=True → минимум +1 балл (0.5 во float-шкале).
    if has_solution and method_correct:
        return 1.0
    # верный ответ без полного решения / без обоснования метода → +1 балл
    return 0.5


def _pick_category(
    *,
    answer_correct: bool,
    method_correct: bool,
    has_solution: bool,
    difficulty_level: int,
    score: float,
) -> str:
    """Выбрать категорию для JSON-ответа тьютора."""
    if score == 0.0:
        return "blank"
    if answer_correct and method_correct and has_solution:
        return "correct"
    if answer_correct and method_correct and not has_solution:
        if difficulty_level >= 7:
            return "suspicious"
        return "correct_no_justification"
    if not answer_correct and method_correct:
        return "wrong_answer_good_method"
    return "wrong_answer_wrong_method"


# ── Score badge ───────────────────────────────────────────────────────

def score_badge(score: float, has_solution: bool) -> str:
    """Бейдж результата для UI.

    После изменений по ТЗ FORMYLA шкала только положительная:
        1.0   → +2 балла (верный ответ + полное решение)
        ≥0.3  → +1 балл  (верный ответ; для high-diff без обоснования)
        0.0   → 0 баллов (неверный ответ или пусто)
        <0    → 0 баллов (на всякий случай: legacy-значения)
    """
    if score >= 1.0:
        return "🟢 **Оценка тьютора: +2 балла** (верный ответ + корректное решение)"
    if score >= 0.3:
        if has_solution:
            return "🟡 **Оценка тьютора: +1 балл** (верный ответ, добавь полное обоснование для +2 баллов)"
        return "🟡 **Оценка тьютора: +1 балл** (верный ответ, добавь обоснование для +2 баллов)"
    # 0.0 и ниже — нейтрально, без отрицательных оценок
    return "⚪ **Оценка тьютора: 0 баллов** (ответ не принят — попробуй ещё раз)"


# ── Главная функция: review_attempt ───────────────────────────────────

def review_attempt(
    *,
    task_text: str,
    correct_answer: str,
    solution_ref: str,
    user_answer: str,
    user_solution: str = "",
    images_b64: Optional[List[str]] = None,
    deepseek_client_cls: Any = None,
    deepseek_available: bool = True,
    max_tokens: int = 4096,
    difficulty_level: int = 5,
) -> Dict[str, Any]:
    """Полная AI-проверка ответа ученика.

    Args:
        task_text:        условие задачи.
        correct_answer:   канонический ответ из БД (может быть пуст).
        solution_ref:     эталонное решение из БД (может быть пуст).
        user_answer:      ответ ученика (строка, возможно LaTeX).
        user_solution:    текст решения ученика (опционально).
        images_b64:       список base64 фото-решений (без data: префикса).
        deepseek_client_cls: класс DeepSeekClient (или None — тогда fallback).
        deepseek_available: флаг доступности AI (на случай ImportError).
        max_tokens:       лимит генерации DeepSeek.
        difficulty_level: уровень сложности задачи (1-7, default 5).
                          Влияет на шкалу: correct без обоснования
                          на высоких уровнях снижает балл.

    Returns:
        dict с полями:
          score (float)       — финальный балл (-1.0, 0.0, 0.3, 0.5, 1.0).
          feedback (str)      — фидбек ученику.
          is_correct (bool)   — score >= 0.5.
          is_proof_task (bool).
          user_solution_enriched (str).
          answer_correct (bool|None) — верен ли ответ (если определено).
          method_correct (bool|None) — верен ли метод (если определено).
          category (str)      — категория результата.
          confidence (float|None) — уверенность AI (0.0-1.0).
          error_location (str|None) — место ошибки.
          needs_escalation (bool) — нужна ли проверка Claude.
          # TODO Stage 6: escalation router -> Claude-Sonnet, cost-tracked $4 max
    """
    user_answer = (user_answer or "").strip()
    user_solution = (user_solution or "").strip()
    images_b64 = list(images_b64 or [])
    correct_answer = (correct_answer or "").strip()
    solution_ref = solution_ref or ""

    proof_mode = is_proof_task(task_text, correct_answer)

    # 1) OCR фото — обогащаем user_solution
    if images_b64 and deepseek_available and deepseek_client_cls is not None:
        try:
            transcribed = transcribe_photos(
                images_b64=images_b64,
                task_text=task_text,
                deepseek_client_cls=deepseek_client_cls,
            )
            if transcribed:
                header = (
                    "[Распознанные фото-решения]"
                    if len(images_b64) > 1
                    else "[Распознанное фото-решение]"
                )
                if user_solution:
                    user_solution = f"{user_solution}\n\n{header}\n{transcribed}"
                else:
                    user_solution = f"{header}\n{transcribed}"
        except Exception as e:
            logger.warning("OCR photos failed: %s", e)

    # ── Stage 2: sympy computational verification ──────────────────
    sympy_determined = False  # True  → sympy parsed both → вердикт окончательный
    sympy_correct = False     # sympy's verdict

    if not proof_mode:
        # 2a) Empty answer → blank immediately (skip sympy + AI)
        if not user_answer:
            return {
                "score": 0.0,
                "feedback": (
                    "⏭️ **Ответ не предоставлен.**\n\n"
                    "Попробуй решить задачу и ввести ответ."
                ),
                "is_correct": False,
                "is_proof_task": False,
                "user_solution_enriched": user_solution,
                "answer_correct": False,
                "method_correct": False,
                "category": "blank",
                "confidence": 1.0,
                "error_location": None,
                "needs_escalation": False,
            }

        # 2b) Sympy semantic comparison
        if correct_answer and _HAS_SYMPY:
            try:
                _sc, _na = _compare_with_sympy(user_answer, correct_answer)
                if _sc is not None:
                    sympy_determined = True
                    sympy_correct = _sc
            except Exception as _exc:
                logger.debug("sympy comparison error: %s", _exc)

    # 3) Quick-check (для подсказки ИИ — НЕ для финального вердикта)
    #
    # ВАЖНО (по требованию продукта): вердикт +1/0/−1 принимает ТОЛЬКО ИИ-тьютор.
    # Ранее здесь были два «fast return»:
    #   3a) sympy_determined + sympy_correct → возвращали ВЕРНО без ИИ.
    #   3b) math_equivalent(user, canon)    → возвращали ВЕРНО без ИИ.
    # Из-за этого возникал «локальный кейс +1», параллельный с ИИ-тьютором,
    # и при разнице форматов ответа результаты расходились.
    # Теперь sympy/math-equivalent используются ИСКЛЮЧИТЕЛЬНО как hint
    # в промпте для модели — финальный вердикт всегда выдаёт DeepSeek.
    score = 0.0
    feedback = "Ваш ответ принят."

    # Подсказка для модели: если sympy не сработал, но строки совпадают
    # численно → пометим это и отдадим как hint.
    math_equiv_hint: Optional[bool] = None
    if not proof_mode and not sympy_determined and correct_answer:
        try:
            math_equiv_hint = math_equivalent(user_answer, correct_answer)
        except Exception:
            math_equiv_hint = None

    # 4) AI-проверка через DeepSeek — ЕДИНСТВЕННЫЙ источник вердикта.
    #
    # sympy / math_equivalent ниже идут ИСКЛЮЧИТЕЛЬНО как hint в промпте
    # (подсказка), а финальные answer_correct / method_correct берём из
    # ответа модели. Если ИИ недоступен или вернул не-JSON — ставим
    # НЕЙТРАЛЬНЫЙ результат (score=0.0, category="suspicious", confidence=0.0),
    # а вызывающий код (см. app.py:check_adaptive_answer) поймёт это
    # как is_ai_failure и НЕ изменит уровень/стрик ученика.

    # Defaults для нейтрального исхода — на случай любых сбоев ниже.
    has_sol = bool(user_solution.strip())
    answer_correct = False
    method_correct = False
    category = "suspicious"
    confidence = 0.0
    error_location = None
    needs_escalation = False

    if deepseek_available and deepseek_client_cls is not None:
        try:
            system_prompt = get_tutor_prompt(proof_mode=proof_mode)

            if proof_mode:
                etalon = solution_ref[:2000] if solution_ref else "(не загружено)"
                user_prompt = (
                    f"Задача (ДОКАЗАТЕЛЬСТВО): {task_text}\n\n"
                    f"Эталонное решение из БД:\n{etalon}\n\n"
                    f"Решение ученика: {user_answer}\n"
                )
                if user_solution:
                    user_prompt += f"Подробное решение:\n{user_solution}\n"
                user_prompt += "\nОцени доказательство и дай фидбек в формате JSON."
            else:
                # Computational: даём sympy/math_equivalent как ПОДСКАЗКУ,
                # но финальное решение — за моделью.
                hint_lines = []
                if sympy_determined:
                    hint_lines.append(
                        "Проверка кодом (sympy): "
                        + ("численно совпадает с эталоном." if sympy_correct
                           else "численно НЕ совпадает с эталоном.")
                    )
                if math_equiv_hint is True:
                    hint_lines.append(
                        "Простая численная проверка: ответ ученика численно "
                        "эквивалентен эталону."
                    )
                elif math_equiv_hint is False and not sympy_determined:
                    hint_lines.append(
                        "Простая численная проверка: совпадений не найдено "
                        "(не доверяй на 100%, формат записи мог отличаться)."
                    )
                hint_block = ""
                if hint_lines:
                    hint_block = (
                        "\n\n[ПОДСКАЗКИ ОТ КОДА — не вердикт; учитывай, но решай сам]\n- "
                        + "\n- ".join(hint_lines)
                        + "\nФинальный вердикт ВСЕГДА выноси сам и заполняй "
                          "answer_correct/method_correct по факту."
                    )

                user_prompt = (
                    f"Задача: {task_text}\n\n"
                    f"Правильный ответ: {correct_answer or 'не указан'}\n\n"
                    f"Ответ ученика: {user_answer}\n\n"
                    f"Решение ученика: {user_solution if user_solution else 'не предоставлено'}\n"
                    f"{hint_block}\n\n"
                    f"Оцени решение и дай фидбек в формате JSON."
                )

            client = deepseek_client_cls()
            ai_response = client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=max_tokens,
            )

            try:
                ai_data = _safe_json_parse(ai_response)
                # Берём вердикт ИСКЛЮЧИТЕЛЬНО от модели — никаких
                # forced-override от sympy/math_equivalent.
                answer_correct = bool(ai_data.get("answer_correct", False))
                method_correct = bool(ai_data.get("method_correct", False))
                score = _compute_score(
                    answer_correct=answer_correct,
                    method_correct=method_correct,
                    has_solution=has_sol,
                    difficulty_level=difficulty_level,
                )
                category = _pick_category(
                    answer_correct=answer_correct,
                    method_correct=method_correct,
                    has_solution=has_sol,
                    difficulty_level=difficulty_level,
                    score=score,
                )
                confidence = float(ai_data.get("confidence", 1.0))
                error_location = ai_data.get("error_location") or None
                feedback = str(ai_data.get("feedback", "Ответ проверен."))
                needs_escalation = (
                    confidence < 0.6 and proof_mode and difficulty_level >= 7
                )
            except (json.JSONDecodeError, ValueError) as parse_err:
                logger.error("Failed to parse AI response as JSON: %s", parse_err)
                # Сбой парсинга → НЕЙТРАЛЬНО (не −1!): уровень не падает.
                score = 0.0
                category = "suspicious"
                confidence = 0.0
                feedback = (
                    "AI-разбор временно недоступен — оценка нейтральная, "
                    "уровень не изменится.\n\n"
                    f"Правильный ответ: **{correct_answer or 'см. БД'}**\n\n"
                    f"Решение:\n{(solution_ref or 'см. учебник')[:600]}"
                )
        except Exception as e:
            logger.exception("DeepSeek call failed: %s", e)
            # API/сетевой сбой → НЕЙТРАЛЬНО (не −1!).
            score = 0.0
            category = "suspicious"
            confidence = 0.0
            feedback = (
                "AI-проверка временно недоступна — оценка нейтральная, "
                "уровень не изменится.\n\n"
                f"**Правильный ответ:** {correct_answer or 'см. БД'}\n\n"
                + (f"**Решение:**\n{solution_ref[:800]}" if solution_ref else "")
            )
    else:
        # ИИ не подключён в окружении → НЕЙТРАЛЬНО (не −1!).
        score = 0.0
        category = "suspicious"
        confidence = 0.0
        feedback = (
            "AI-проверка сейчас недоступна — оценка нейтральная, "
            "уровень не изменится.\n\n"
            f"**Правильный ответ:** {correct_answer or 'см. БД'}\n\n"
            + (f"**Решение:**\n{solution_ref[:800]}" if solution_ref else "")
        )

    # 5) Sanitize feedback (убираем LaTeX-команды)
    try:
        feedback = sanitize_feedback_no_latex(feedback)
    except Exception as e:
        logger.warning("sanitize_feedback failed: %s", e)

    # 6) Префикс с явной оценкой
    has_sol = bool(user_solution.strip())
    badge = score_badge(score, has_sol)
    if badge.split(":", 1)[0] not in (feedback or "")[:80]:
        feedback = f"{badge}\n\n{feedback or ''}".strip()

    return {
        "score": score,
        "feedback": feedback,
        "is_correct": (score >= 0.5),
        "is_proof_task": proof_mode,
        "user_solution_enriched": user_solution,
        "answer_correct": answer_correct,
        "method_correct": method_correct,
        "category": category,
        "confidence": confidence,
        "error_location": error_location,
        "needs_escalation": needs_escalation,
    }


__all__ = [
    "review_attempt",
    "is_proof_task",
    "math_equivalent",
    "transcribe_photos",
    "sanitize_feedback_no_latex",
    "score_badge",
    "SYSTEM_PROMPT_PROOF",
    "SYSTEM_PROMPT_NUMERIC",
    "get_tutor_prompt",
    "_compute_score",
    "_pick_category",
]
