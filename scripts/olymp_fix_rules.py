# -*- coding: utf-8 -*-
"""
Правила, регулярки и словари для пайплайна чистки каталога олимпиадных задач.

Содержит:
  - этап 1: отображения математических Unicode-символов;
  - этап 2: паттерны PDF-мусора;
  - этап 3: паттерны Markdown-мусора;
  - этап 4: конвертация LaTeX-разделителей;
  - этап 8-10: маркеры решения/ответа/критериев, мусорные ответы;
  - этап 12: паттерны решений-заглушек;
  - этап 17: таблица соответствий названий этапов олимпиад;
  - список официальных доменов;
  - детекторы проблем для отчёта «было/стало».
"""

import re
import unicodedata

# =====================================================================
# ЭТАП 1. Математические Unicode-символы
# =====================================================================

def _build_math_letter_map() -> dict:
    """Строит отображение математических букв (U+1D400–U+1D7FF) в ASCII.

    Использует имена символов в Unicode: «MATHEMATICAL BOLD CAPITAL A» -> 'A' и т.д.
    """
    mapping = {}
    for cp in range(0x1D400, 0x1D800):
        ch = chr(cp)
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        # Пример имени: «MATHEMATICAL BOLD CAPITAL Z», «MATHEMATICAL ITALIC SMALL A»
        m = re.search(r"(CAPITAL|SMALL) ([A-Z])$", name)
        if m:
            letter = m.group(2)
            if m.group(1) == "SMALL":
                letter = letter.lower()
            mapping[ch] = letter
            continue
        try:
            mapping[ch] = str(unicodedata.digit(ch))
            continue
        except (ValueError, TypeError):
            pass
        # Греческие математические символы (𝛼, 𝛽, 𝛾, 𝛿, 𝜀, 𝜋, 𝜑, 𝜙 и др.) в U+1D400–U+1D7FF
        decomposed = unicodedata.normalize("NFKC", ch)
        if decomposed and decomposed != ch and all(ord(c) < 0x1D400 for c in decomposed):
            mapping[ch] = decomposed
    return mapping


MATH_LETTER_MAP = _build_math_letter_map()

# Верхние и нижние индексы -> LaTeX-команды
SUPERSCRIPT_MAP = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6",
    "⁷": "7", "⁸": "8", "⁹": "9", "⁺": "+", "⁻": "-", "ⁿ": "n", "ᵏ": "k",
    "ᵐ": "m", "ᵃ": "a", "ᵇ": "b", "ᶜ": "c", "ᵈ": "d", "ᵗ": "t", "ˣ": "x",
    "ᵞ": "γ", "ᵟ": "δ", "ᵠ": "φ",
}
SUBSCRIPT_MAP = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4", "₅": "5", "₆": "6",
    "₇": "7", "₈": "8", "₉": "9", "₊": "+", "₋": "-", "ₙ": "n", "ₖ": "k",
    "ₘ": "m", "ₓ": "x", "ᵢ": "i", "ⱼ": "j",
}

# Лигатуры
LIGATURE_MAP = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
}

# PUA-символы шрифтов Windows Symbol (\uF020..\uF0FF), встречающиеся в PDF
# (formula-unity, mmo, pvg, vsosh). Переводятся в Юникод ДО удаления прочих PUA.
PUA_SYMBOL_MAP = {
    "\uf020": " ", "\uf022": "∀", "\uf024": "∃", "\uf027": "∋", "\uf02a": "*",
    "\uf02b": "+", "\uf02d": "-", "\uf03d": "=", "\uf03c": "<", "\uf03e": ">",
    "\uf040": "≅", "\uf044": "△", "\uf056": "V", "\uf057": "Ω", "\uf05e": "⊥",
    "\uf061": "α", "\uf062": "β", "\uf063": "χ", "\uf064": "δ", "\uf065": "ε",
    "\uf066": "φ", "\uf067": "γ", "\uf068": "η", "\uf069": "ι", "\uf06a": "φ",
    "\uf06b": "κ", "\uf06c": "λ", "\uf06d": "μ", "\uf06e": "ν", "\uf06f": "°",
    "\uf070": "π", "\uf071": "θ", "\uf072": "ρ", "\uf073": "σ", "\uf074": "τ",
    "\uf075": "υ", "\uf077": "ω", "\uf078": "ξ", "\uf079": "ψ", "\uf07a": "ζ",
    "\uf07e": "∼", "\uf0a2": "′", "\uf0a3": "≤", "\uf0a5": "∞", "\uf0ab": "↔",
    "\uf0ac": "←", "\uf0ad": "↑", "\uf0ae": "→", "\uf0af": "↓", "\uf0b0": "°",
    "\uf0b1": "±", "\uf0b2": "″", "\uf0b3": "≥", "\uf0b4": "×", "\uf0b5": "∝",
    "\uf0b7": "⋅", "\uf0b8": "÷", "\uf0b9": "≠", "\uf0ba": "≡", "\uf0bb": "≈",
    "\uf0bc": "…", "\uf0be": "—", "\uf0c4": "⊗", "\uf0c5": "⊕", "\uf0c6": "∅",
    "\uf0c7": "∩", "\uf0c8": "∪", "\uf0c9": "⊃", "\uf0ca": "⊇", "\uf0cb": "⊄",
    "\uf0cc": "⊂", "\uf0cd": "⊆", "\uf0ce": "∈", "\uf0cf": "∉", "\uf0d0": "∠",
    "\uf0d5": "∏", "\uf0d6": "√", "\uf0d7": "⋅", "\uf0d8": "¬", "\uf0d9": "∧",
    "\uf0da": "∨", "\uf0db": "⇔", "\uf0dc": "⇐", "\uf0de": "⇒", "\uf0e5": "∑",
    "\uf0f2": "∫", "\uffff": "— ",
}

# Приватные/непечатные символы — удалить
PRIVATE_USE_RE = re.compile("[\uE000-\uF8FF\uFFFD\uFFFF\uFEFF]")
CONTROL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Математический минус и разные тире
MINUS_RE = re.compile("[\u2212\u2012\u2013\u2014\u2015]")
# Дефис-минус, окружённый цифрами/скобками (формульный контекст)
DASH_IN_MATH_RE = re.compile(
    r"(?<=[\d\)\]])\s*[\u2012\u2013\u2014\u2015]\s*(?=[\d\(])"
)
# Схлопывание пробелов
MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")


def normalize_unicode_math(text: str) -> str:
    """Этап 1: нормализация символов без изменения математики."""
    if not text:
        return text
    # T2A-артефакты PDF: ¼ внутри русских слов → ё, ¾...¿ и \x11...\x11 → «...», \x16 → —, \x15 → –
    text = re.sub(r"(?<=[а-яА-ЯёЁ])¼", "ё", text)
    text = re.sub(r"¾([^¿\n]{1,120})¿", r"«\1»", text)
    text = re.sub(r"\x11([^\x11\n]{1,120})\x11", r"«\1»", text)
    text = re.sub(r"\x16", "—", text)
    text = re.sub(r"(?<=\s)\x15(?=\s)", "–", text)
    out = []
    for ch in text:
        if ch in PUA_SYMBOL_MAP:
            out.append(PUA_SYMBOL_MAP[ch])
        elif ch in MATH_LETTER_MAP:
            out.append(MATH_LETTER_MAP[ch])
        elif ch in SUPERSCRIPT_MAP:
            out.append("^{" + SUPERSCRIPT_MAP[ch] + "}")
        elif ch in SUBSCRIPT_MAP:
            out.append("_{" + SUBSCRIPT_MAP[ch] + "}")
        elif ch in LIGATURE_MAP:
            out.append(LIGATURE_MAP[ch])
        elif ch == "\u2212":  # математический минус -> дефис
            out.append("-")
        else:
            out.append(ch)
    text = "".join(out)
    # тире между математическими токенами -> минус
    text = DASH_IN_MATH_RE.sub("-", text)
    # мусорные символы
    text = PRIVATE_USE_RE.sub("", text)
    text = CONTROL_RE.sub("", text)
    # схлопнуть пробелы
    text = MULTI_SPACE_RE.sub(" ", text)
    # пробел перед переносом строки
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text


# =====================================================================
# ЭТАП 2. PDF-мусор
# =====================================================================

PDF_GARBAGE_PATTERNS = [
    # «© МФТИ, 2024.» — только сам копирайт, без остальной строки
    (re.compile(r"©\s*(?:МФТИ|Физтех)\s*,?\s*\d{4}\s*\.?"), "копирайт МФТИ/Физтех с годом"),
    (re.compile(r"©\s*(?:МФТИ|Физтех)\s*\.?"), "копирайт МФТИ/Физтех"),
    (re.compile(r"Физтех[–—‒-]\s?\d{4}\.?\s*Билеты[^\n]{0,40}"), "колонтитул «Физтех-ГОД. Билеты N–M»"),
    (re.compile(r"^\s*(?:Ответы и решения|ОТВЕТЫ И РЕШЕНИЯ|Ответы и решения\.)\s*$", re.M),
     "заголовок «Ответы и решения»"),
    (re.compile(r"^\s*(?:Условия задач|УСЛОВИЯ ЗАДАЧ|Условия\.)\s*$", re.M),
     "заголовок «Условия задач»"),
    (re.compile(r"^\s*(?:Решения задач|РЕШЕНИЯ ЗАДАЧ|Решения\.)\s*$", re.M),
     "заголовок «Решения задач»"),
    (re.compile(r"^\s*(?:Задачи|ЗАДАЧИ)\s+для\s+\d+\s+класса\s*$", re.M),
     "заголовок «Задачи для N класса»"),
    (re.compile(r"\A\s*[-–—‒]?\s*\d{1,2}\s*[-–—‒]?\s*\n|\n\s*[-–—‒]?\s*\d{1,2}\s*[-–—‒]?\s*\Z"),
     "одинокий номер страницы"),
    (re.compile(r"^\s*(?:Страница|стр\.)\s*\d+\s*(?:из\s*\d+)?\s*$", re.M),
     "колонтитул «Страница N»"),
    (re.compile(r"^\s*\d+\s*\|\s*[^\n]*Олимпиада[^\n]*$", re.M),
     "колонтитул с номером страницы и названием олимпиады"),
    (re.compile(r"\s*\[\s*(?:до\s+)?\d+\s*балл(?:а|ов|б\.?)?\s*\]\s*$"),
     "разбалловка [N баллов] в конце"),
]


def remove_repeated_lines(text: str, min_count: int = 3, min_len: int = 8) -> tuple[str, list[str]]:
    """Удаляет строки-колонтитулы, повторяющиеся >= min_count раз."""
    lines = text.split("\n")
    if not lines:
        return text, []
    counts: dict[str, int] = {}

    def _is_candidate(key: str) -> bool:
        if len(key) < min_len or len(key) > 80:
            return False
        if "\\" in key or "$" in key or "=" in key:
            return False
        if key.endswith((".", "!", "?", ":", ";", ",")):
            return False
        return True

    for ln in lines:
        key = ln.strip()
        if _is_candidate(key):
            counts[key] = counts.get(key, 0) + 1
    repeated = {k for k, v in counts.items() if v >= min_count}
    if not repeated:
        return text, []
    kept = [ln for ln in lines if ln.strip() not in repeated]
    return "\n".join(kept), sorted(repeated)


# =====================================================================
# ЭТАП 3. Markdown-мусор
# =====================================================================

MD_BOLD_SOLUTION = re.compile(r"\*\*\s*(?:Решение|РЕШЕНИЕ)\s*\.?\s*\*\*")
MD_BOLD_ANSWER = re.compile(r"\*\*\s*(?:Ответ|ОТВЕТ)\s*:?\s*\*\*")
OFFICIAL_SOLUTION_LINE = re.compile(
    r"(?:^|\n)[^\n]*\[Официальное решение\][^\n]*", re.I
)
MD_LINK = re.compile(r"\[([^\]]*)\]\(\s*(https?://[^)\s]+)\s*\)")
LEADING_TRAILING_MD = re.compile(r"^\s*\*\*|\*\*\s*$")
MD_HEADER = re.compile(r"^#{1,6}\s*", re.M)


# =====================================================================
# ЭТАП 4. LaTeX-разделители
# =====================================================================

DOLLAR_BLOCK_RE = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$", re.S)
DOLLAR_INLINE_RE = re.compile(r"(?<!\\)\$([^$\n]+?)(?<!\\)\$", re.S)
DOLLAR_MULTILINE_RE = re.compile(r"(?<!\\)\$(?!\$)((?:[^$\n]|\n(?!\n)){1,300}?)(?<!\\)\$(?!\$)")
TAG_DOLLAR_RE = re.compile(r"\\tag\{\$([^$]+)\$\}")
LPAREN_RE = re.compile(r"\\\(")
RPAREN_RE = re.compile(r"\\\)")
LBRACKET_RE = re.compile(r"\\\]")
RBRACKET_RE = re.compile(r"\\\[")


def split_math_segments(text: str) -> list[tuple[bool, str]]:
    """Разбивает текст на сегменты (защищённая_математика, обычный_текст)."""
    segments: list[tuple[bool, str]] = []
    pattern = re.compile(r"(\\\((?:[^\\]|\\(?!\\))*?\\\)|\\\[[\s\S]*?\\\])")
    pos = 0
    for m in pattern.finditer(text):
        if m.start() > pos:
            segments.append((False, text[pos:m.start()]))
        segments.append((True, m.group(0)))
        pos = m.end()
    if pos < len(text):
        segments.append((False, text[pos:]))
    return segments


def convert_dollar_delims(text: str) -> str:
    """$...$ -> \\( ... \\), $$...$$ -> \\[ ... \\] вне существующей математики."""
    if "$" not in text:
        return text
    out = []
    for protected, seg in split_math_segments(text):
        if protected:
            out.append(TAG_DOLLAR_RE.sub(r"\\tag{\1}", seg))
            continue
        seg = DOLLAR_BLOCK_RE.sub(lambda m: "\\[" + m.group(1).strip() + "\\]", seg)
        seg = DOLLAR_INLINE_RE.sub(lambda m: "\\(" + m.group(1).strip() + "\\)", seg)
        if "$" in seg:
            seg = DOLLAR_MULTILINE_RE.sub(lambda m: "\\(" + m.group(1).strip() + "\\)", seg)
        out.append(seg)
    return "".join(out)


def delimiters_balanced(text: str) -> tuple[bool, str]:
    """Проверка баланса \\(/\\) и \\[/\\]. Возвращает (ok, описание проблемы)."""
    problems = []
    if len(LPAREN_RE.findall(text)) != len(RPAREN_RE.findall(text)):
        problems.append("нечётное число \\( / \\)")
    if len(LBRACKET_RE.findall(text)) != len(RBRACKET_RE.findall(text)):
        problems.append("нечётное число \\[ / \\]")
    # незакрытое окружение
    for env in ("enumerate", "itemize", "align", "cases", "array", "matrix", "tabular"):
        begins = len(re.findall(r"\\begin\{" + env + r"\}", text))
        ends = len(re.findall(r"\\end\{" + env + r"\}", text))
        if begins != ends:
            problems.append(f"незакрытое окружение {env} ({begins} vs {ends})")
    return (not problems, "; ".join(problems))


# =====================================================================
# ЭТАП 6. Порезанные формулы (эвристики обнаружения)
# =====================================================================

BROKEN_FORMULA_HINTS = [
    re.compile(r"\\\)\s*[+=]\s*\\\("),                                      # \(a\) + \(b\)
    re.compile(r"\\\)\s*\d+\s*\\\("),                                       # \(x\) 24 \(y\)
    re.compile(r"(?<![а-яА-ЯёЁa-zA-Z])[a-z]{1,3}\s+\\\([a-z\^]"),           # co \(s^..., si \(n...
    re.compile(r"\\\)\s*[a-z]\s+\\\("),                                     # \(x\) f \(y\)
    re.compile(r"\d\s+\\?\(?[a-zA-Z]+\^\d+\)?\s*[+\-=]\s*\\?\(?[a-zA-Z0-9]"),  # 2 x^2+1 без разметки
    re.compile(r"\\\)\s*\+\s*\d"),                                          # \(x^2\)+1
    re.compile(r"\\\([^)]{1,80}\\\)[a-zA-Z]|[a-zA-Z]\\\([^)]{1,80}\\\)"),   # латиница вплотную к \(...\)
]


# =====================================================================
# ЭТАП 7. Формулы без LaTeX (эвристики обнаружения)
# =====================================================================

RAW_MATH_SYMBOLS_RE = re.compile(r"[√∛⇔∠≅⊆∈∉∀∃≤≥≠≈∞±⋅×÷∂∫∑∏]|\bx\s*\d\b|\ba\s*\+\s*b\b")
GREEK_KEEP = set("αβγδεζηθικλμνξπρστυφχψω")


# =====================================================================
# ЭТАП 8. Решение/критерии/ответ внутри условия
# =====================================================================

RE_SOLUTION_MARK = re.compile(
    r"(?:^|\n|[.?!)]\s+)\s*\**(?:Решени[ея]|РЕШЕНИЕ|Решение\s+задачи|Доказательств[оа]|"
    r"Разбор|Комментари[ий]|Схема\s+решения)\**\s*[.:]\s*",
    re.I,
)
RE_ANSWER_MARK = re.compile(
    r"(?:^|\n|[.?!)]\s+)\s*\**(?:Ответы?|ОТВЕТ|Правильный\s+ответ)\**\s*[:.]\s*",
    re.I,
)
RE_CRITERIA_LINE = re.compile(
    r"(?:(?:^|\n|[.?!]\s+)\s*\**(?:Критерии(?:\s+оценивания)?|Схема\s+оценивания|"
    r"Разбалловка)\**\s*[.:][^\n]*|\[\s*(?:до\s+)?\d+\s*балл(?:а|ов)?\s*\])",
    re.I,
)


# =====================================================================
# ЭТАП 9. Дубль условия в начале решения
# =====================================================================

def norm_for_compare(text: str) -> str:
    """Нормализация для сравнения текстов (префиксы, дубли)."""
    t = text.lower()
    t = re.sub(r"\\[()\[\]]", " ", t)
    t = re.sub(r"[^0-9a-zа-яё]", "", t)
    return t


def norm_for_dedupe(text: str) -> str:
    """Нормализация для точной дедупликации: СОХРАНЯЕТ математические операторы,
    чтобы «x+1» и «x-1» не склеились. Сравнение — по полному тексту."""
    t = normalize_unicode_math(text or "").lower()
    t = re.sub(r"\\[()\[\]]|\$\$?", " ", t)
    t = re.sub(r"\[\s*(?:до\s+)?\d+\s*балл(?:а|ов|б\.?)?\s*\]", " ", t)
    # Склейка PDF-переносов внутри русских слов («соче- тание» -> «сочетание»)
    # и удаление текстовых тире с пробелами между русскими словами
    t = re.sub(r"(?<=[а-яё])-\s+(?=[а-яё])", "", t)
    t = re.sub(r"(?<=[а-яё])\s+-\s+(?=[а-яё])", " ", t)
    t = (t.replace(r"\times", "*").replace("×", "*")
          .replace(r"\cdot", "*").replace("⋅", "*")
          .replace(r"\le", "<=").replace(r"\leq", "<=").replace("≤", "<=")
          .replace(r"\ge", ">=").replace(r"\geq", ">=").replace("≥", ">=")
          .replace(r"\ne", "!=").replace(r"\neq", "!=").replace("≠", "!="))
    # Текстовую пунктуацию сразу после кириллических букв убираем,
    # десятичные точки/запятые и математические знаки полностью сохраняем
    t = re.sub(r"(?<=[а-яё])[.,:;!?]+", " ", t)
    t = re.sub(r"[\s\u00a0]+", "", t)
    # Оставляем буквы, цифры и математические знаки
    t = re.sub(r"[^0-9a-zа-яё+\-*/=<>^_().,:%|√∑∫!]", "", t)
    return t


# =====================================================================
# ЭТАП 10. Мусорные ответы
# =====================================================================

ANSWER_GARBAGE_VALUES = {
    "", "-", "--", "—", "— -", "-—", "**", "***", "(︀", "√", "√ ", "нет",
    "ответ", "н/д", "n/a", "нет ответа", "см. решение", "см. решение.",
}
ANSWER_ONLY_PUNCT_RE = re.compile(r"^[\s\-–—‒_*#=+.,:;()|/\[\]]+$")
MAX_ANSWER_LEN = 250


def is_answer_garbage(answer: str) -> bool:
    if not answer or answer.strip().lower() in ANSWER_GARBAGE_VALUES:
        return True
    if ANSWER_ONLY_PUNCT_RE.match(answer.strip()):
        return True
    return False


# =====================================================================
# ЭТАП 12. Решения-заглушки
# =====================================================================

PLACEHOLDER_PATTERNS = [
    (re.compile(r"(?:^|\n)\s*(?:См\.?\s*(?:официальное\s*)?решение|Смотрите\s*решение)[^\n]*", re.I),
     "отсылка «см. решение»"),
    (re.compile(r"(?:^|\n)\s*(?:Уточните условие|Условие не\s*найдено|Нет данных|Недостаточно данных)[^\n]*", re.I),
     "«уточните условие»"),
    (re.compile(r"(?:^|\n)\s*Найдено официальное решение на сайте[^\n]*", re.I),
     "«найдено официальное решение на сайте»"),
    (re.compile(r"param\s*\d", re.I), "шаблонная таблица param"),
    (re.compile(r"(?:^|\n)\s*(?:решение\s*)?(?:отсутствует|не\s*найдено|не\s*приводится)\s*[.]?", re.I),
     "«решение отсутствует»"),
]

# «См. задачу 6 для 9 класса» / «См. решение задачи 6 (9 класс)»
SEE_TASK_RE = re.compile(
    r"(?:задач[ауые]\s*(?:№\s*)?|№\s*)(\d+)[^\n]{0,40}?(\d{1,2})\s*класс", re.I
)


# =====================================================================
# ЭТАП 15. Рисунки
# =====================================================================

FIGURE_MENTION_RE = re.compile(
    r"(?:см\.?\s*рис|смотрите\s*рис|на\s*рисунке|рисунок\s*№?\s*\d|на\s*рис\.)", re.I
)


# =====================================================================
# ЭТАП 16-17. Дубликаты и названия этапов
# =====================================================================

# Приоритет статусов: чем меньше индекс, тем ценнее запись
STATUS_PRIORITY = [
    "official_found", "official", "official_variant", "AI_verified",
    "gemini_solved", "AI_generated_with_hints", "AI_generated",
    "unresolved", "broken_text", "figure_only",
]


def status_rank(status: str) -> int:
    try:
        return STATUS_PRIORITY.index(status)
    except ValueError:
        return len(STATUS_PRIORITY)


def record_quality(rec: dict) -> tuple:
    """Качество записи для выбора лучшего дубликата: (статус, есть source, длина solution)."""
    return (
        -status_rank(rec.get("status", "")),
        1 if rec.get("source") else 0,
        len(rec.get("solution") or ""),
        len(rec.get("answer") or ""),
    )


# Канонические ключи этапов
ROUND_CANON = {
    "final": "Заключительный этап",
    "qual": "Отборочный этап",
    "regional": "Региональный этап",
}

# Таблица соответствий названий этапов (этап 17). Показывается пользователю.
ROUND_ALIAS_TABLE = {
    "kurchatov": {
        "2 тур": "final", "второй тур": "final", "1 тур": "qual", "первый тур": "qual",
        "отборочный этап": "qual", "заключительный этап": "final", "финал": "final",
    },
    "lomonosov": {
        "1 тур": "qual", "первый тур": "qual", "2 тур": "final", "второй тур": "final",
        "отборочный этап": "qual", "заключительный этап": "final",
    },
    "vysshaya-proba": {
        "1 тур": "qual", "2 тур": "final", "отборочный этап": "qual",
        "заключительный этап": "final", "региональный этап": "regional",
    },
    "turgor": {
        "отборочный тур": "qual", "основной тур": "final",
        "отборочный этап": "qual", "заключительный этап": "final",
    },
}
# Значения по умолчанию для олимпиад без явной таблицы: по ключевым словам.
ROUND_KEYWORD_MAP = [
    (re.compile(r"закл|финал|final", re.I), "final"),
    (re.compile(r"отбор|qualif|otbor", re.I), "qual"),
    (re.compile(r"регион|region", re.I), "regional"),
    (re.compile(r"2\s*тур|второй", re.I), "final"),
    (re.compile(r"1\s*тур|первый", re.I), "qual"),
]

# Подсказки по URL
URL_ROUND_HINTS = [
    (re.compile(r"final|zakl|2tur|tur2|2[\-_]?stage|stage[\-_]?2|ochn|закл|финал|очн|2[\-_]?тур|второй", re.I), "final"),
    (re.compile(r"region|регион|reg[\-_]", re.I), "regional"),
    (re.compile(r"otbor|qualif|zaoch|1tur|tur1|1[\-_]?stage|stage[\-_]?1|отбор|заочн|1[\-_]?тур|первый", re.I), "qual"),
]


def canon_round_key(round_name: str, slug: str = "") -> str | None:
    """Приводит название этапа к каноническому ключу ('final'/'qual'/'regional')."""
    if not round_name:
        return None
    name = round_name.strip().lower()
    table = ROUND_ALIAS_TABLE.get(slug)
    if table:
        for alias, key in table.items():
            if name == alias or name == alias.lower():
                return key
    for rx, key in ROUND_KEYWORD_MAP:
        if rx.search(name):
            return key
    return None


def url_round_key(url: str) -> str | None:
    if not url:
        return None
    for rx, key in URL_ROUND_HINTS:
        if rx.search(url):
            return key
    return None


# =====================================================================
# Официальные домены
# =====================================================================

OFFICIAL_DOMAINS = {
    "olymp.mipt.ru", "phystech.mipt.ru", "olymp-online.mipt.ru", "mipt.ru", "abitu.net",
    "tasks.olimpiada.ru", "rsr-olymp.ru", "olympiads.mccme.ru", "mccme.ru", "problems.ru",
    "turgor.ru", "vos.olimpiada.ru", "siriusolymp.ru", "всош.цпм.рф",
    "xn--b1a5a9a.xn--p1ag3a.xn--p1ai", "mosolymp.ru", "math.mosolymp.ru",
    "olymp.msu.ru", "msu.ru", "olymp.hse.ru", "hse.ru",
    "kurchatov-olymp.ru", "olimpiadakurchatov.ru", "old.olimpiadakurchatov.ru",
    "formulo.org", "matol.ru", "euler.mccme.ru", "euler.ru", "matol.kz",
    "mmo.mccme.ru", "matprazdnik.mccme.ru", "olimpiada.spbu.ru", "olympiada.spbu.ru",
    "spbu.ru", "pvg.mk.ru", "olimpiada.ru", "mathus.ru",
}


def is_official_url(url: str) -> bool:
    """Проверка, что URL ведёт на официальный домен олимпиады."""
    if not url:
        return False
    m = re.match(r"https?://([^/?#\s]+)", url.strip())
    if not m:
        return False
    host = m.group(1).lower()
    host = host[4:] if host.startswith("www.") else host
    for d in OFFICIAL_DOMAINS:
        if host == d or host.endswith("." + d):
            return True
    return False


# =====================================================================
# Детекторы проблем для отчёта «было/стало»
# (типы совпадают с колонкой issue в olymp_catalog_quality_issues.csv)
# =====================================================================

def _has_mixed_delims(rec: dict) -> bool:
    t = (rec.get("text") or "") + (rec.get("solution") or "")
    return ("$" in t) and ("\\(" in t or "\\[" in t)


def _truncated_text(rec: dict) -> bool:
    t = (rec.get("text") or "").strip()
    if len(t) < 40:
        return True
    if t and t[-1] not in ".?!:;»\"'":
        return True
    return False


DETECTORS = {
    "source_empty": lambda r: not (r.get("source") or "").strip(),
    "latex_mixed_delims": _has_mixed_delims,
    "latex_env_in_solution": lambda r: "\\begin{" in (r.get("solution") or ""),
    "pdf_math_alphanumerics": lambda r: any(
        0x1D400 <= ord(c) <= 0x1D7FF for c in (r.get("text") or "") + (r.get("solution") or "")),
    "pdf_private_use_chars": lambda r: any(
        0xE000 <= ord(c) <= 0xF8FF or ord(c) in (0xFFFD, 0xFFFF)
        for c in (r.get("text") or "") + (r.get("solution") or "")),
    "unicode_math_no_latex": lambda r: bool(
        RAW_MATH_SYMBOLS_RE.search(r.get("text") or "")) and "\\(" not in (r.get("text") or ""),
    "answer_markdown_bold": lambda r: "**" in (r.get("answer") or ""),
    "solution_has_links": lambda r: "http" in (r.get("solution") or ""),
    "answer_garbage": lambda r: is_answer_garbage(r.get("answer") or ""),
    "answer_too_long": lambda r: len(r.get("answer") or "") > MAX_ANSWER_LEN,
    "answer_in_text": lambda r: bool(RE_ANSWER_MARK.search(r.get("text") or "")),
    "sol_in_text": lambda r: bool(RE_SOLUTION_MARK.search(r.get("text") or "")),
    "solution_markdown": lambda r: "**" in (r.get("solution") or "") or "~~" in (r.get("solution") or ""),
    "solution_placeholder": lambda r: any(rx.search(r.get("solution") or "") for rx, _ in PLACEHOLDER_PATTERNS),
    "param_template": lambda r: "param1" in (r.get("solution") or "").lower(),
    "solution_too_short": lambda r: 0 < len((r.get("solution") or "").strip()) < 60,
    "solution_huge": lambda r: len(r.get("solution") or "") >= 7990,
    "text_huge": lambda r: len(r.get("text") or "") > 20000,
    "text_too_short": lambda r: 0 < len((r.get("text") or "").strip()) < 40,
    "text_no_terminal_punct": _truncated_text,
    "figure_mentioned_missing": lambda r: bool(
        FIGURE_MENTION_RE.search(r.get("text") or "")) and not (
        r.get("fig_statement") or r.get("fig_solution")),
    "latex_fragment_wrap": lambda r: any(rx.search(r.get("text") or "") for rx in BROKEN_FORMULA_HINTS),
    "latex_broken_func": lambda r: bool(re.search(r"\bco\s+\\\(|\bs\s+\\\(", r.get("text") or "")),
    "latex_unbalanced_display": lambda r: not delimiters_balanced(r.get("text") or "")[0],
    "text_dup_in_solution": lambda r: False,  # вычисляется отдельно (нужен префикс)
    "duplicate_same_variant": lambda r: False,  # вычисляется отдельно (каталог)
    "duplicate_cross_round": lambda r: False,  # вычисляется отдельно (каталог)
    "source_round_mismatch": lambda r: False,  # вычисляется отдельно (URL)
    "solution_notes_wrong_answer": lambda r: False,  # сверка моделью
    "status:unresolved": lambda r: r.get("status") == "unresolved",
    "status:broken_text": lambda r: r.get("status") == "broken_text",
    "status:figure_only": lambda r: r.get("status") == "figure_only",
    "status:official_variant": lambda r: r.get("status") == "official_variant",
    "status:AI_generated": lambda r: r.get("status") == "AI_generated",
    "status:AI_generated_with_hints": lambda r: r.get("status") == "AI_generated_with_hints",
}


def detect_issues(catalog: dict) -> dict:
    """Считает проблемы по каталогу {slug: [records]}.

    Возвращает {(issue, slug): count} + дубликаты и расхождения round/source.
    """
    counts: dict = {}
    for slug, records in catalog.items():
        for rec in records:
            for issue, fn in DETECTORS.items():
                try:
                    if fn(rec):
                        counts[(issue, slug)] = counts.get((issue, slug), 0) + 1
                except Exception:
                    continue
        # дубли внутри варианта
        seen: dict = {}
        for rec in records:
            key = (rec.get("year"), canon_round_key(rec.get("round") or "", slug), rec.get("grade"),
                   norm_for_compare(rec.get("text") or "")[:200])
            if key in seen:
                counts[("duplicate_same_variant", slug)] = counts.get(("duplicate_same_variant", slug), 0) + 1
            seen[key] = rec.get("uid")
        # дубли между этапами (одинаковый текст в разных round)
        by_text: dict = {}
        for rec in records:
            t = norm_for_compare(rec.get("text") or "")[:200]
            by_text.setdefault(t, []).append(rec)
        for t, recs in by_text.items():
            rounds = {canon_round_key(r.get("round") or "", slug) for r in recs}
            if len(recs) > 1 and len(rounds) > 1:
                counts[("duplicate_cross_round", slug)] = counts.get(("duplicate_cross_round", slug), 0) + 1
        # расхождение round и source
        for rec in records:
            ukey = url_round_key(rec.get("source") or "")
            rkey = canon_round_key(rec.get("round") or "", slug)
            if ukey and rkey and ukey != rkey:
                counts[("source_round_mismatch", slug)] = counts.get(("source_round_mismatch", slug), 0) + 1
    return counts
