"""Пользовательские предупреждения — без внутренних кодов и жаргона.

Каждое предупреждение конвейера исторически начинается с кода
(«TARGET_DROPPED: …», «UNDERDETERMINED: …»). Код нужен разработчику в
журнале, а не школьнику на странице чертежа: пользователь видит
техническую абракадабру и внутренние диагностики решателя.

Обёртка pipeline.generate приводит warnings к пользовательскому виду:
- внутренние диагностики/подтверждения (решатель, ремонт плана, рендер)
  убираются совсем;
- контрактные предупреждения (что не удалось и почему это важно для
  ответа) остаются — но нормальным языком, без кодов и английских
  терминов.

Контракт сохраняется: неверный/неполный чертёж никогда не выглядит
«проверенным» — причина всегда объяснена, только по-человечески.
Суффикс версии не поднимается: меняется только текст предупреждений,
кэш валиден (полировка применяется и к результатам из кэша).
"""
from __future__ import annotations

import functools
import os
import re

GEOEXACT_WARNPOLISH = os.environ.get("GEOEXACT_WARNPOLISH", "1")
ENABLED = GEOEXACT_WARNPOLISH != "0"

_CODE_RE = re.compile(r"^([A-Z][A-Z0-9_]{2,}):\s*(.*)$", re.S)
_NESTED_RE = re.compile(r"(?:^|\s)[A-Z][A-Z0-9_]{2,}:\s*")

# Внутреннее: пользователю не нужно (диагностика решателя, журнал ремонта
# плана, подтверждения statement-проверок, внутренности рендера).
_DROP = frozenset({
    "UNDERDETERMINED", "OVERDETERMINED",
    "CONVEXITY", "CONVEXITY_INJECTED",
    "STATEMENT_MARK", "STATEMENT_DRAW", "DRAW_COMPLETED", "MARK_SUPPORT",
    "GIVEN_ORDER_FIXED", "EQUIDISTANT_FIXED", "DRAW_SANITIZED",
    "LINE_CIRCLE_ANCHOR", "FALLBACK_FROM", "DETAIL_VIEW",
    "GATE_SCORE", "GATE_WARN", "GATE_FAIL",
    "SKIPPED_ANGLE", "SKIPPED_ARC", "SKIPPED_CIRCLE", "SKIPPED_EQUAL_MARK",
    "SKIPPED_SEGMENT", "DUPLICATE_ANGLE_TEXT",
    "LABEL_COLLISION", "MARK_COLLISION",
    "POINT_ON_SEGMENT", "UNDECLARED_INCIDENCE", "ORPHAN_POINT",
    "CURVE_APPROXIMATION", "PROJECTED_OVERLAP",
})

# Контрактное: остаётся пользователю, но нормальным языком.
# {text} — исходный текст после кода (очищенный от вложенных кодов).
_REWRITE = {
    "TARGET_DROPPED": "Автоматически измерить искомую величину не удалось: "
                      "чертёж построен по условию, ответ — в полном решении.",
    "SKETCH": "Показан схематичный чертёж по ключевым словам условия: пропорции "
              "условные, сверьте чертёж с текстом задачи.",
    "SIMPLIFIED": "Чертёж построен по упрощённой схеме: часть условий могла быть "
                  "не учтена.",
    "AUX_FALLBACK": "Чертёж с дополнительными построениями построить не удалось — "
                    "показан основной чертёж.",
    "INTERNAL": "Внутренняя ошибка построения — попробуйте ещё раз.",
    "TIME_LIMIT": "Не хватило времени на построение — попробуйте ещё раз.",
    "APPROXIMATE": "Автопроверка подтвердила не всё условие: {text}",
    "INVALID_CONDITION": "Условие задачи противоречиво, точный чертёж невозможен: {text}",
    "STATEMENT_MISSING": "На чертеже не хватает части названных в условии объектов: {text}",
}


def _polish_aux_claim(text: str) -> str:
    """AUX_CLAIM: без «Луны» и служебного хвоста, с текстом утверждения."""
    claim = (text.replace("Луна пишет, что ", "")
                 .split(", но на чертеже")[0]
                 .replace(". Линии построены точно; проверьте утверждение сами", "")
                 .strip().rstrip("."))
    return (f"Дополнительное построение построено точно, но утверждение «{claim}» "
            "на чертеже не выполняется — проверьте его сами.")


def _strip_nested(text: str) -> str:
    return _NESTED_RE.sub(" ", text).strip()


def _polish_one(w: str) -> str | None:
    """Одно предупреждение -> пользовательский текст или None (убрать)."""
    w = str(w).strip()
    if not w:
        return None
    m = _CODE_RE.match(w)
    if not m:
        return _strip_nested(w) or None      # уже без кода — только чистка
    code, text = m.group(1), _strip_nested(m.group(2))
    if code in _DROP:
        return None
    if code == "AUX_CLAIM":
        return _polish_aux_claim(text)
    if code == "APPROXIMATE":
        # источник уже начинает текст с «не подтверждено автоматически:» —
        # не дублируем
        text = text.replace("не подтверждено автоматически: ", "").strip()
    if code in _REWRITE:
        out = _REWRITE[code]
        return out.format(text=text) if "{text}" in out else out
    return text or None                      # прочее — текст без кода


def polish_warnings(warnings) -> list[str]:
    """Список предупреждений к пользовательскому виду (без дубликатов)."""
    out: list[str] = []
    for w in warnings or []:
        p = _polish_one(w)
        if p and p not in out:
            out.append(p)
    return out


def _wrap_generate(orig):
    @functools.wraps(orig)
    def generate(problem, with_aux=False, **kwargs):
        res = orig(problem, with_aux, **kwargs)
        try:
            polished = polish_warnings(getattr(res, "warnings", None))
            if polished != list(getattr(res, "warnings", None) or []):
                res.warnings = polished
        except Exception:  # noqa: BLE001 - полировка не должна ломать выдачу
            pass
        return res

    generate._warn_polish = True
    generate._original = orig
    return generate


def install(pipeline_module) -> bool:
    """Обернуть pipeline.generate (снаружи остальных обёрток). Повторный
    вызов — no-op. Выключается GEOEXACT_WARNPOLISH=0."""
    if not ENABLED:
        return False
    ok = False
    fn = getattr(pipeline_module, "generate", None)
    if fn is not None and not getattr(fn, "_warn_polish", False):
        pipeline_module.generate = _wrap_generate(fn)
        ok = True
    return ok
