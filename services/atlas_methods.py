# -*- coding: utf-8 -*-
"""Server-side access to the "Методы — визуальный атлас" data.

The atlas is a large self-contained HTML file (static/methods/index.html) that
embeds two JSON documents:

  - <script type="application/json" id="methods-data">  -> list of method objects
  - <script type="application/json" id="visuals-data">  -> { "visual_id:stage": "<svg…>" }

The AI tutor backend must NEVER trust method content sent by the client.
Instead it loads the canonical copy once, caches it, and exposes a small,
explicit allow-list of fields that may be forwarded to the model.  This keeps
the model context bounded and prevents prompt-injection through client-supplied
"method data".

Security notes:
  * All fields returned here are truncated to fixed limits.
  * LaTeX is preserved; markdown is flattened to plain text (no HTML).
  * SVG is never forwarded whole — only extracted text labels / aria-labels.
"""

from __future__ import annotations

import html as _html
import json
import logging
import os
import re
import threading

logger = logging.getLogger(__name__)

_ATLAS_HTML_PATH = os.path.join("static", "methods", "index.html")

# Fallback paths if the canonical file is missing (CI / alternate checkouts).
_ATLAS_HTML_FALLBACKS = [
    os.path.join("static", "methods", "atlas.html"),
    os.path.join("templates", "olympiad", "method.html"),
]

_cache = None
_cache_lock = threading.Lock()

# Maximum sizes for every string field forwarded to the model. These are
# generous for a single method but keep the total prompt under control.
MAX_FIELD = 4000
MAX_SELECTION = 2000
MAX_NEIGHBOR = 3000
MAX_SECTION_TITLE = 200
MAX_STAGE_NOTE = 1500
MAX_SVG_LABELS = 60
MAX_SVG_LABEL_LEN = 200

# Allow-listed method fields that may reach the model.
METHOD_FIELDS = [
    "definition_md",
    "main_theorems_md",
    "typical_techniques_md",
    "triggers_md",
    "why_it_works_md",
    "pitfalls_md",
]

# Allow-listed example fields.
EXAMPLE_FIELDS = [
    "title",
    "display_title",
    "index_title",
    "body",
    "visual_id",
    "visual_type",
    "visual_spec",
    "stage_notes",
]


def _load_atlas():
    """Load and cache methods + visuals from the static atlas HTML."""
    global _cache
    with _cache_lock:
        if _cache is not None:
            return _cache

        methods: list = []
        visuals: dict = {}
        html = ""

        candidates = [_ATLAS_HTML_PATH] + _ATLAS_HTML_FALLBACKS
        for path in candidates:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    html = f.read()
                if html:
                    break
            except Exception:
                continue

        if html:
            m = re.search(
                r'<script[^>]*type=["\']application/json["\'][^>]*id=["\']methods-data["\'][^>]*>(.*?)</script>',
                html,
                re.S,
            )
            if m:
                try:
                    methods = json.loads(m.group(1))
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning("[atlas_methods] methods-data parse failed: %s", e)
                    methods = []

            v = re.search(
                r'<script[^>]*type=["\']application/json["\'][^>]*id=["\']visuals-data["\'][^>]*>(.*?)</script>',
                html,
                re.S,
            )
            if v:
                try:
                    visuals = json.loads(v.group(1))
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning("[atlas_methods] visuals-data parse failed: %s", e)
                    visuals = {}

        by_code = {}
        by_code_lower = {}
        for item in methods:
            if isinstance(item, dict) and item.get("method_code"):
                code = item["method_code"]
                by_code[code] = item
                by_code_lower.setdefault(code.lower(), item)

        _cache = {
            "methods": methods,
            "visuals": visuals,
            "by_code": by_code,
            "by_code_lower": by_code_lower,
        }
        logger.info(
            "[atlas_methods] loaded %d methods, %d visual keys",
            len(methods),
            len(visuals),
        )
        return _cache


def reload_atlas() -> None:
    """Drop the cache (used by tests to force a fresh read)."""
    global _cache
    with _cache_lock:
        _cache = None


def get_method(method_code: str):
    """Return the canonical method dict or None.

    Method codes are case-sensitive (e.g. "A2b" vs "A2B"), so we first try an
    exact match, then a case-insensitive fallback. The caller must still treat
    the result as untrusted *content* (it is only ever forwarded through the
    allow-listed field accessors below).
    """
    code = (method_code or "").strip()
    if not code:
        return None
    cache = _load_atlas()
    if code in cache["by_code"]:
        return cache["by_code"][code]
    return cache["by_code_lower"].get(code.lower())


def get_example(method_code: str, example_index):
    """Return the example dict for a valid example index, or None."""
    method = get_method(method_code)
    if not method:
        return None
    examples = method.get("examples") or []
    if not isinstance(examples, list) or not examples:
        return None
    if example_index is None:
        return None
    try:
        idx = int(example_index)
    except (TypeError, ValueError):
        return None
    if idx < 0 or idx >= len(examples):
        return None
    return examples[idx]


def list_examples(method_code: str):
    """Return (count, list_of_short_titles) for the task selector."""
    method = get_method(method_code)
    if not method:
        return 0, []
    examples = method.get("examples") or []
    titles = []
    for ex in examples:
        if not isinstance(ex, dict):
            continue
        titles.append(_short_title(ex))
    return len(examples), titles


# --------------------------------------------------------------------------
# Plain-text / LaTeX-preserving helpers
# --------------------------------------------------------------------------

def markdown_to_plain(text) -> str:
    """Flatten markdown to plain text but KEEP LaTeX ($…$, \\(…\\), \\[…\\]).

    Removes bold/italic markers, headings, list bullets, code ticks, links,
    and collapses whitespace. No HTML is produced.
    """
    if text is None:
        return ""
    if isinstance(text, (list, tuple)):
        return " · ".join(markdown_to_plain(x) for x in text if x)
    if isinstance(text, dict):
        return " · ".join(markdown_to_plain(v) for v in text.values() if v is not None)

    s = str(text)
    # Protect LaTeX blocks so their internal markup is untouched.
    latex_stash: list[str] = []

    def _stash(m):
        latex_stash.append(m.group(0))
        return "\u0000L%d\u0000" % (len(latex_stash) - 1)

    s = re.sub(r"\$\$[\s\S]+?\$\$", _stash, s)
    s = re.sub(r"\\\[[\s\S]+?\\\]", _stash, s)
    s = re.sub(r"\\\([\s\S]+?\\\)", _stash, s)
    s = re.sub(r"\$[^$\n]+?\$", _stash, s)

    s = s.replace("**", "").replace("__", "")
    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.M)
    s = re.sub(r"^\s*[-*+]\s+", "", s, flags=re.M)
    s = re.sub(r"^\s*\d+[.)]\s+", "", s, flags=re.M)
    s = s.replace("`", "")
    s = re.sub(r"\[([^\]]+)\]\([^)\s]+\)", r"\1", s)
    s = s.replace(">", "")
    s = re.sub(r"\s+", " ", s).strip()

    # Restore LaTeX.
    def _unstash(m):
        idx = int(m.group(1))
        return latex_stash[idx] if idx < len(latex_stash) else ""

    s = re.sub(r"\u0000L(\d+)\u0000", _unstash, s)
    return s


def _short_title(ex: dict) -> str:
    t = markdown_to_plain(ex.get("display_title") or ex.get("index_title") or ex.get("title") or "")
    t = re.sub(r"^(Задача|Пример)\s*\d+\s*[.:]?\s*", "", t, flags=re.I)
    if not t:
        t = "Разбор"
    if len(t) > 74:
        t = t[:74].rsplit(" ", 1)[0] + "…"
    return t


def _truncate(text, limit: int) -> str:
    s = markdown_to_plain(text)
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + "…"
    return s


# --------------------------------------------------------------------------
# Context builders (the ONLY way method data reaches the model)
# --------------------------------------------------------------------------

def build_method_context(method_code: str) -> dict | None:
    """Return a bounded, allow-listed method context or None."""
    method = get_method(method_code)
    if not method:
        return None

    ctx: dict = {
        "code": method.get("method_code", ""),
        "name": method.get("method_name", ""),
        "section": method.get("section", ""),
        "grades": (method.get("grades") or [])[:12],
        "difficulty": method.get("difficulty_level"),
        "definition": _truncate(method.get("definition_md"), MAX_FIELD),
        "theorems": _truncate(method.get("main_theorems_md"), MAX_FIELD),
        "techniques": _truncate(method.get("typical_techniques_md"), MAX_FIELD),
        "triggers": _truncate(method.get("triggers_md"), MAX_FIELD),
        "whyItWorks": _truncate(method.get("why_it_works_md"), MAX_FIELD),
        "pitfalls": _truncate(method.get("pitfalls_md"), MAX_FIELD),
        "signalPhrases": [_truncate(x, 300) for x in (method.get("signal_phrases") or [])][:12],
        "firstMoves": [_truncate(x, 300) for x in (method.get("first_moves") or [])][:12],
        "relatedMethods": (method.get("related_methods") or [])[:12],
        "prerequisites": (method.get("prerequisites") or [])[:12],
        "leadsTo": (method.get("leads_to") or [])[:12],
    }
    return ctx


def build_example_context(method_code: str, example_index) -> dict | None:
    """Return a bounded example context (without full SVG), or None."""
    example = get_example(method_code, example_index)
    if not example:
        return None

    stage_notes = example.get("stage_notes") or {}
    if not isinstance(stage_notes, dict):
        stage_notes = {}

    ctx: dict = {
        "index": int(example_index),
        "title": _short_title(example),
        "body": _truncate(example.get("body"), MAX_FIELD),
        "visualType": _truncate(example.get("visual_type"), 120),
        "visualSpec": _truncate(example.get("visual_spec"), MAX_STAGE_NOTE),
        "stageNotes": {
            str(k): _truncate(v, MAX_STAGE_NOTE)
            for k, v in stage_notes.items()
            if v is not None
        },
    }
    return ctx


def build_visual_context(method_code: str, example_index, stage: str) -> dict | None:
    """Return text-only metadata for explaining one drawing stage.

    Never returns the SVG markup itself. Extracts textual labels and
    aria-labels so the model can talk about what is actually drawn.
    """
    example = get_example(method_code, example_index)
    if not example:
        return None

    visual_id = example.get("visual_id")
    if not visual_id:
        return {
            "available": False,
            "note": "У этого разбора нет чертежа (визуализация не добавляет смысла).",
        }

    stage = (stage or "").strip().lower()
    valid_stages = ("condition", "construction", "result")
    if stage not in valid_stages:
        stage = "condition"

    visuals = _load_atlas()["visuals"]
    svg = visuals.get(f"{visual_id}:{stage}") or ""
    labels = extract_svg_labels(svg)

    stage_notes = example.get("stage_notes") or {}
    if not isinstance(stage_notes, dict):
        stage_notes = {}
    note = stage_notes.get(stage) or ""

    stage_names = {
        "condition": "Условие",
        "construction": "Построение",
        "result": "Результат",
    }

    return {
        "available": True,
        "visualId": visual_id,
        "stage": stage,
        "stageName": stage_names.get(stage, stage),
        "visualType": _truncate(example.get("visual_type"), 120),
        "visualSpec": _truncate(example.get("visual_spec"), MAX_STAGE_NOTE),
        "stageNote": _truncate(note, MAX_STAGE_NOTE),
        "svgLabels": labels,
    }


_TAG_RE = re.compile(r"<(?:text|tspan)\b[^>]*>(.*?)</(?:text|tspan)>", re.S)
_ARIA_RE = re.compile(r"aria-label\s*=\s*[\"']([^\"']+)[\"']", re.S)


def extract_svg_labels(svg: str) -> list[str]:
    """Extract a bounded list of text labels / aria-labels from SVG markup."""
    if not svg:
        return []
    labels: list[str] = []

    for m in _TAG_RE.finditer(svg):
        txt = re.sub(r"<[^>]+>", "", m.group(1))
        txt = _html.unescape(txt).strip()
        if txt and txt not in labels:
            labels.append(txt)
        if len(labels) >= MAX_SVG_LABELS:
            break

    if len(labels) < MAX_SVG_LABELS:
        for m in _ARIA_RE.finditer(svg):
            txt = _html.unescape(m.group(1)).strip()
            if txt and txt not in labels:
                labels.append(txt)
            if len(labels) >= MAX_SVG_LABELS:
                break

    return [lbl[:MAX_SVG_LABEL_LEN] for lbl in labels[:MAX_SVG_LABELS]]
