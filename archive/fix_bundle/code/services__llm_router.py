# -*- coding: utf-8 -*-
"""services/llm_router.py — провайдер-специфичный резолвер моделей.

Решает проблему «логическое имя модели отправляется в Novita без маппинга»:
Novita требует префиксные ID (deepseek/deepseek-v4-pro), прямой DeepSeek — без
префикса (deepseek-v4-pro).  Здесь логическая модель резолвится в
provider-native ID, а цепочка провайдеров строится ДО запроса.

Без numpy, без внешних зависимостей (requests импортируется лениво).
Никогда не логирует api_key / Authorization.
"""
from __future__ import annotations

import os
import time
from typing import Dict, List, Optional, Tuple

# ──────────────────────────────────────────────────────────────────────────
# Маппинг логического имени -> provider-native ID
# ──────────────────────────────────────────────────────────────────────────
PROVIDER_MODEL_MAP = {
    "novita": {
        "deepseek-v4-pro": "deepseek/deepseek-v4-pro",
        "deepseek-v4-flash": "deepseek/deepseek-v4-flash",
    },
    "deepseek": {
        "deepseek-v4-pro": "deepseek-v4-pro",
        "deepseek-v4-flash": "deepseek-v4-flash",
    },
    # CH-aux: прямой api.deepseek.com без префикса (для роли solver).
    "deepseek_direct": {
        "deepseek-v4-pro": "deepseek-v4-pro",
        "deepseek-v4-flash": "deepseek-v4-flash",
    },
    # REC-5: OdiRouter (OpenAI-compatible), модели без префикса.
    # BATCH FIX: добавлен Claude Sonnet для base/aux/audit планировщиков.
    "odirouter": {
        "gemini-3.7-flash": "gemini-3.7-flash",
        "claude-sonnet-4-6": "claude-sonnet-4-6",
        "claude-sonnet-4-5": "claude-sonnet-4-5",
        # GPT-модели через OdiRouter (OpenAI-compatible).  gpt-5.6-sol и gpt-5.5
        # дают 504 Gateway Timeout на nginx OdiRouter при длинном промпте.
        # gpt-5.4 отвечает быстро (~24s) и строит полные доп. построения.
        "gpt-5.6-sol": "gpt-5.6-sol",
        "gpt-5.5": "gpt-5.5",
        "gpt-5.4": "gpt-5.4",
        # CH-fidelity: DeepSeek тоже доступен на OdiRouter и отвечает стабильно,
        # тогда как прямой api.deepseek.com падает с SSLError/ChunkedEncodingError,
        # а Novita отдаёт 401 (невалидный ключ).  Без этого маппинга solver-роль
        # не могла пройти OdiRouter и падала с solver_failed (aux не строился).
        "deepseek-v4-pro": "deepseek-v4-pro",
        "deepseek-v4-flash": "deepseek-v4-flash",
    },
}

def _odirouter_base_url() -> str:
    """REC-5: OdiRouter — OpenAI-compatible endpoint (полный URL до /chat/completions).

    .env хранит только хост (GEMINI_API_BASE / GEMINI_BASE_URL), поэтому
    дополняем путь.  Ключ — GEMINI_API_KEY, имя модели без префикса.
    """
    base = (
        os.environ.get("GEMINI_API_BASE")
        or os.environ.get("GEMINI_BASE_URL")
        or "https://api.odirouter.ai/v1"
    ).strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


PROVIDER_BASE_URLS = {
    "novita": "https://api.novita.ai/v3/openai/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "deepseek_direct": "https://api.deepseek.com/v1/chat/completions",
    "odirouter": _odirouter_base_url(),
}

# Логические роли -> дефолтная логическая модель.
ROLE_DEFAULT_MODEL = {
    # REC-5: структурный JSON и извлечение — Gemini (flash) через OdiRouter.
    "base": "gemini-3.7-flash",
    "aux": "gemini-3.7-flash",
    "audit": "gemini-3.7-flash",
    "repair": "deepseek-v4-pro",
    "legacy_reasoner": "deepseek-v4-pro",
    # CH-aux: решатель.  gpt-5.4 через OdiRouter отклонялся провайдером с
    # permission_error (LLM_AUTH_ERROR), из-за чего aux не строился вовсе.
    # Переключаемся на deepseek-v4-pro через прямой DeepSeek API — провайдер
    # уже проверен в проекте (роль repair) и доступен.
    "solver": "deepseek-v4-pro",
    # REC-5 Part 6: shadow-прогон solver'а на Gemini (сравнение качества).
    "solver_shadow": "gemini-3.7-flash",
    # Банк неточностей: deep-разбор на deepseek-v4-pro (прямой DeepSeek API).
    "insight_deep": "deepseek-v4-pro",
}

# Env-переменные, переопределяющие дефолт для роли (в порядке приоритета).
ROLE_ENV_OVERRIDE = {
    "base": ["FIGURE_BASE_MODEL"],
    "aux": ["FIGURE_AUX_MODEL"],
    "repair": ["FIGURE_REPAIR_MODEL"],
    "audit": ["FIGURE_AUDIT_MODEL"],
    "legacy_reasoner": ["FIGURE_MODEL", "DEEPSEEK_MODEL"],
    "solver": ["FIGURE_SOLVER_MODEL"],
    "solver_shadow": ["FIGURE_SOLVER_SHADOW_MODEL"],
}

# CH20: max_tokens по роли (env имеет приоритет над дефолтами).
ROLE_DEFAULT_MAX_TOKENS = {
    "base": 3000,
    "aux": 3500,
    "audit": 800,
    "repair": 6000,
    "legacy_reasoner": 4096,
    # solver-промпт требует полное решение + steps + aux_constructions; у
    # reasoning-модели deepseek-v4-pro длинный вывод легко упирается в 3000
    # (finish_reason=length → невалидный JSON).  Даём запас.
    "solver": 8000,
    "solver_shadow": 3500,
    "insight_deep": 6000,
}

ROLE_MAX_TOKENS_ENV = {
    "base": "FIGURE_BASE_MAX_TOKENS",
    "aux": "FIGURE_AUX_MAX_TOKENS",
    "audit": "FIGURE_AUDIT_MAX_TOKENS",
    "repair": "FIGURE_REPAIR_MAX_TOKENS",
    "legacy_reasoner": None,
    "solver": "FIGURE_SOLVER_MAX_TOKENS",
}

# CH20: thinking-политика по роли.  Планировщики (base/aux/audit) должны
# отдавать JSON сразу, без CoT; repair/legacy_reasoner — reasoning-модели,
# у которых thinking оставляем включённым.
ROLE_DEFAULT_THINKING = {
    "base": "enabled",
    "aux": "enabled",
    "audit": "enabled",
    "repair": "enabled",
    "legacy_reasoner": "enabled",
    # solver = gpt-5.6-sol через OdiRouter.  reasoning-канал (thinking=enabled)
    # вызывает 504 Gateway Timeout на nginx OdiRouter при длинном промпте,
    # поэтому для solver рассуждение отключено — GPT отвечает быстро.
    "solver": "disabled",
    "solver_shadow": "disabled",
    # Банк неточностей: deep-разбор с включённым reasoning-каналом.
    "insight_deep": "enabled",
}

ROLE_THINKING_ENV = {
    "base": "FIGURE_BASE_THINKING",
    "aux": "FIGURE_AUX_THINKING",
    "audit": "FIGURE_AUDIT_THINKING",
    "repair": "FIGURE_REPAIR_THINKING",
    "legacy_reasoner": None,
    "solver": "FIGURE_SOLVER_THINKING",
    "solver_shadow": None,
}

PROVIDER_API_KEY_ENV = {
    "novita": "NOVITA_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "deepseek_direct": "DEEPSEEK_API_KEY",
    "odirouter": "GEMINI_API_KEY",
}

# Порядок цепочки провайдеров (по умолчанию для ролей base/aux/audit/repair).
PROVIDER_ORDER = ("novita", "deepseek")

# Порядок цепочки для роли solver: прямой DeepSeek первым.
SOLVER_PROVIDER_ORDER = ("deepseek_direct", "novita", "deepseek")

# REC-5: раскладка провайдеров по ролям (env override для провайдера).
ROLE_PROVIDER_ENV = {
    "base": "FIGURE_BASE_PROVIDER",
    "aux": "FIGURE_AUX_PROVIDER",
    "audit": "FIGURE_AUDIT_PROVIDER",
    "repair": "FIGURE_REPAIR_PROVIDER",
    "solver": "FIGURE_SOLVER_PROVIDER",
    "solver_shadow": "FIGURE_SOLVER_SHADOW_PROVIDER",
    # Банк неточностей: глубокий разбор идёт ТОЛЬКО напрямую в DeepSeek API.
    "insight_deep": "INSIGHT_DEEP_PROVIDER",
}

# REC-5: цепочки fallback по ролям.
ROLE_PROVIDER_ORDER = {
    "base": ("odirouter", "deepseek_direct", "novita"),
    "aux": ("odirouter", "deepseek_direct"),
    "audit": ("odirouter", "deepseek_direct"),
    # solver — GPT-5.6-SOL через OdiRouter первым, fallback на Gemini и DeepSeek.
    "solver": ("odirouter", "deepseek_direct", "novita"),
    "repair": ("deepseek_direct", "novita"),
    # Shadow-сравнение solver'а — только Gemini через OdiRouter.
    "solver_shadow": ("odirouter",),
    # Банк неточностей: deep-разбор — строго прямой DeepSeek API
    # (api.deepseek.com), без Novita/OdiRouter.
    "insight_deep": ("deepseek_direct",),
}

# TTL кэша недоступных пар (provider, model_id) после 404 MODEL_NOT_FOUND.
MODEL_NOT_FOUND_TTL_SECONDS = 15 * 60

# CH20: после N подряд транспортных ошибок провайдер помечается недоступным.
PROVIDER_UNREACHABLE_TTL_SECONDS = 10 * 60
# CH21 FIX 5: порог настраивается env FIGURE_PROVIDER_FAIL_THRESHOLD (default 2).
PROVIDER_UNREACHABLE_THRESHOLD = int(
    os.environ.get("FIGURE_PROVIDER_FAIL_THRESHOLD", "2") or "2"
)
# CH21 FIX 5: явное отключение провайдера.
FIGURE_DISABLE_NOVITA = (
    os.environ.get("FIGURE_DISABLE_NOVITA", "").strip().lower()
    in ("1", "true", "yes", "on")
)

# ──────────────────────────────────────────────────────────────────────────
# Кэш процесса: (provider, model_id) -> время, до которого пара недоступна
# ──────────────────────────────────────────────────────────────────────────
_unavailable_until: Dict[Tuple[str, str], float] = {}

# CH20: недоступность провайдера целиком (все его модели) на время TTL.
_provider_unreachable_until: Dict[str, float] = {}

# CH-aux: недоступность пары provider::model (ключ блокировки).  Ошибка одной
# модели не должна отключать весь провайдер (pro != flash).
_provider_model_unreachable_until: Dict[str, float] = {}

# Счётчик подряд идущих транспортных ошибок по провайдеру (CH20).
_transport_errors: Dict[str, int] = {}

# Кэш: (provider, model_id) — у провайдера нет поддержки параметра "thinking".
_thinking_unsupported: set = set()


def _now() -> float:
    return time.monotonic()


def mark_model_unavailable(provider: str, model_id: str, ttl: Optional[float] = None) -> None:
    """Запомнить, что пара provider+model недоступна на TTL секунд."""
    ttl = ttl if ttl is not None else MODEL_NOT_FOUND_TTL_SECONDS
    _unavailable_until[(provider, model_id)] = _now() + ttl


def is_model_unavailable(provider: str, model_id: str) -> bool:
    """True, если пара недоступна (и TTL ещё не истёк)."""
    exp = _unavailable_until.get((provider, model_id))
    if exp is None:
        return False
    if _now() >= exp:
        _unavailable_until.pop((provider, model_id), None)
        return False
    return True


def clear_model_cache() -> None:
    """Сбросить кэш недоступных пар (для тестов)."""
    _unavailable_until.clear()
    _provider_unreachable_until.clear()
    _provider_model_unreachable_until.clear()
    _transport_errors.clear()
    _thinking_unsupported.clear()


def mark_provider_unreachable(provider: str) -> None:
    """Пометить провайдера недоступным на 10 минут (все его модели)."""
    _provider_unreachable_until[provider] = _now() + PROVIDER_UNREACHABLE_TTL_SECONDS


def is_provider_unreachable(provider: str) -> bool:
    exp = _provider_unreachable_until.get(provider)
    if exp is None:
        return False
    if _now() >= exp:
        _provider_unreachable_until.pop(provider, None)
        return False
    return True


def _pm_key(provider: str, model_id: str) -> str:
    return f"{provider}::{model_id}"


def mark_provider_model_unreachable(provider: str, model_id: str,
                                    ttl_sec: int = 600) -> None:
    """CH-aux: заблокировать конкретную пару provider::model на TTL секунд."""
    _provider_model_unreachable_until[_pm_key(provider, model_id)] = _now() + ttl_sec


def is_provider_model_unreachable(provider: str, model_id: str) -> bool:
    exp = _provider_model_unreachable_until.get(_pm_key(provider, model_id))
    if exp is None:
        return False
    if _now() >= exp:
        _provider_model_unreachable_until.pop(_pm_key(provider, model_id), None)
        return False
    return True


def record_transport_error(provider: str, model_id: str = "") -> bool:
    """REC-6: зафиксировать транспортную ошибку пары provider::model.

    При достижении порога помечает ТОЛЬКО пару provider::model недоступной
    (не весь провайдер): падение v4-pro не должно отключать v4-flash.
    """
    key = _pm_key(provider, model_id)
    _transport_errors[key] = _transport_errors.get(key, 0) + 1
    if _transport_errors[key] >= PROVIDER_UNREACHABLE_THRESHOLD:
        _transport_errors[key] = 0
        mark_provider_model_unreachable(provider, model_id,
                                        PROVIDER_UNREACHABLE_TTL_SECONDS)
        return True
    return False


def reset_transport_errors(provider: str, model_id: str = "") -> None:
    """Сбросить счётчик транспортных ошибок после успешного вызова."""
    _transport_errors.pop(_pm_key(provider, model_id), None)


def mark_thinking_unsupported(provider: str, model_id: str) -> None:
    _thinking_unsupported.add((provider, model_id))


def is_thinking_unsupported(provider: str, model_id: str) -> bool:
    return (provider, model_id) in _thinking_unsupported


# ──────────────────────────────────────────────────────────────────────────
# Резолвер логической роли/модели
# ──────────────────────────────────────────────────────────────────────────

def logical_model_for_role(role: str) -> str:
    """Логическая модель для роли с учётом env-переопределений."""
    default = ROLE_DEFAULT_MODEL.get(role, "deepseek-v4-pro")
    for env_name in ROLE_ENV_OVERRIDE.get(role, []):
        val = (os.environ.get(env_name) or "").strip()
        if val:
            return val
    return default


def max_tokens_for_role(role: str) -> int:
    """max_tokens для роли: env override > дефолт.  Значение из env
    разбирается как int (невалидное — дефолт)."""
    default = ROLE_DEFAULT_MAX_TOKENS.get(role, 4096)
    env_name = ROLE_MAX_TOKENS_ENV.get(role)
    if env_name:
        raw = (os.environ.get(env_name) or "").strip()
        if raw:
            try:
                return int(raw)
            except ValueError:
                return default
    return default


def thinking_mode_for_role(role: str) -> str:
    """Thinking-политика для роли: 'disabled' | 'enabled'.  env override."""
    default = ROLE_DEFAULT_THINKING.get(role, "enabled")
    env_name = ROLE_THINKING_ENV.get(role)
    if env_name:
        raw = (os.environ.get(env_name) or "").strip().lower()
        if raw in ("disabled", "enabled", "0", "1", "false", "true", "off", "on"):
            return "disabled" if raw in ("disabled", "0", "false", "off") else "enabled"
    return default


def resolve_provider_model(logical_model: str, provider: str) -> Optional[str]:
    """Резолв логической модели в provider-native ID.

    Если модель уже содержит '/', считаем её provider-native и возвращаем
    как есть (без повторного преобразования).  Если маппинга нет — None
    (провайдер не должен вызываться с этой моделью).
    """
    logical_model = (logical_model or "").strip()
    if not logical_model:
        return None
    if "/" in logical_model:
        return logical_model
    return PROVIDER_MODEL_MAP.get(provider, {}).get(logical_model)


def provider_api_key(provider: str) -> str:
    return (os.environ.get(PROVIDER_API_KEY_ENV.get(provider, "")) or "").strip()


def build_provider_chain(
    logical_model: str,
    providers: Tuple[str, ...] = PROVIDER_ORDER,
) -> List[dict]:
    """Построить цепочку провайдеров ДО запроса.

    Провайдер попадает в цепочку, только если:
      - есть api_key;
      - есть валидный provider_model_id (резолв не None);
      - пара provider+model_id не закэширована как недоступная.

    Возвращает список dict с provider / model_id / base_url / api_key.
    """
    chain = []
    for provider in providers:
        # CH21 FIX 5: явное отключение novita.
        if provider == "novita" and FIGURE_DISABLE_NOVITA:
            continue
        if is_provider_unreachable(provider):
            continue
        model_id = resolve_provider_model(logical_model, provider)
        if model_id is None:
            continue
        if is_model_unavailable(provider, model_id):
            continue
        # CH-aux: ключ блокировки provider::model.
        if is_provider_model_unreachable(provider, model_id):
            continue
        api_key = provider_api_key(provider)
        if not api_key:
            continue
        chain.append({
            "provider": provider,
            "model_id": model_id,
            "base_url": PROVIDER_BASE_URLS.get(provider),
            "api_key": api_key,
        })
    return chain


# ──────────────────────────────────────────────────────────────────────────
# Ошибки и классификация
# ──────────────────────────────────────────────────────────────────────────

class LLMError(Exception):
    """Ошибка LLM-вызова с кодом и контекстом для осмысленного job.error."""

    def __init__(self, code: str, message: str, provider: str = "",
                 model_id: str = "", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.provider = provider
        self.model_id = model_id
        self.retryable = retryable

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def classify_status(status: int, body: Optional[dict]) -> str:
    """Классифицировать HTTP-статус в код ошибки."""
    if status in (401, 403):
        return "LLM_AUTH_ERROR"
    if status == 404:
        reason = ""
        if isinstance(body, dict):
            reason = str(body.get("reason") or body.get("message") or "")
        if "MODEL_NOT_FOUND" in reason or "model not found" in reason.lower():
            return "LLM_MODEL_NOT_FOUND"
        return "LLM_NOT_FOUND"
    if status == 429:
        return "LLM_RATE_LIMIT"
    if 500 <= status < 600:
        return "LLM_SERVER_ERROR"
    return "LLM_HTTP_ERROR"


def _safe_error_body(resp) -> str:
    """Безопасная выжимка тела ошибки: только code/reason/message или 300 символов."""
    try:
        body = resp.json()
    except Exception:
        text = (resp.text or "")[:300]
        return text
    if isinstance(body, dict):
        parts = []
        for key in ("code", "reason", "message"):
            if key in body:
                parts.append(f"{key}={body[key]}")
        if parts:
            return " ".join(parts)
    return str(body)[:300]


def extract_response_text(body: dict) -> Tuple[str, Dict[str, int]]:
    """Надёжное извлечение текста из chat-completions ответа.

    Порядок: content -> reasoning_content -> reasoning -> choices[0].text.
    Возвращает (text, lengths) где lengths — длины всех проверенных полей.
    """
    lengths: Dict[str, int] = {
        "content": 0, "reasoning_content": 0, "reasoning": 0, "text": 0,
    }
    choices = body.get("choices") or []
    if not choices:
        return "", lengths
    choice = choices[0] or {}
    msg = choice.get("message") or {}
    content = msg.get("content") or ""
    reasoning_content = msg.get("reasoning_content") or ""
    reasoning = msg.get("reasoning") or ""
    text = choice.get("text") or ""
    lengths["content"] = len(content or "")
    lengths["reasoning_content"] = len(reasoning_content or "")
    lengths["reasoning"] = len(reasoning or "")
    lengths["text"] = len(text or "")
    for candidate in (content, reasoning_content, reasoning, text):
        if candidate:
            return candidate, lengths
    return "", lengths


# CH21 FIX 6: прайс по провайдеру и модели (USD за 1M токенов).
_COST_PRICES = {
    # (provider, model_fragment) -> (prompt_usd, completion_usd)
    ("deepseek", "v4-pro"): (0.27, 1.10),
    ("deepseek", "v4-flash"): (0.27, 1.10),
    ("deepseek", "chat"): (0.27, 1.10),
    ("deepseek", "reasoner"): (0.55, 2.19),
    ("novita", "v4-pro"): (0.27, 1.10),
    ("novita", "v4-flash"): (0.27, 1.10),
}

# CH-aux: канонический прайс по модели (USD за 1M токенов), reasoning как output.
MODEL_PRICES_USD_PER_MTOK = {
    "deepseek-v4-pro":   {"in": 0.5693, "out": 1.139},
    "deepseek-v4-flash": {"in": 0.03,   "out": 0.10},
    "gemini-3.7-flash":  {"in": 0.75,   "out": 3.75},
}


def price_for_model(model_id: str) -> Optional[dict]:
    """Вернуть {"in":..,"out":..} для модели (None если неизвестна)."""
    mid = (model_id or "").strip()
    if "/" in mid:
        mid = mid.rsplit("/", 1)[-1]
    return MODEL_PRICES_USD_PER_MTOK.get(mid)


def compute_cost(provider: str, usage: dict, model_id: str = "") -> Optional[float]:
    """Стоимость по прайсу.  Приоритет: канонический MODEL_PRICES_USD_PER_MTOK
    (reasoning тарифицируется как output), затем legacy _COST_PRICES."""
    prompt_tokens = usage.get("prompt_tokens", 0) or 0
    completion_tokens = usage.get("completion_tokens", 0) or 0
    # reasoning-токены считаем как выходные.
    reasoning_tokens = int(usage.get("reasoning_tokens", 0) or 0)
    out_tokens = completion_tokens + reasoning_tokens

    # 1. Каноническая цена по модели.
    mid = (model_id or "").strip()
    if "/" in mid:
        mid = mid.rsplit("/", 1)[-1]
    if mid in MODEL_PRICES_USD_PER_MTOK:
        pp = MODEL_PRICES_USD_PER_MTOK[mid]["in"]
        cp = MODEL_PRICES_USD_PER_MTOK[mid]["out"]
        return (prompt_tokens * pp + out_tokens * cp) / 1_000_000

    # 2. Legacy прайс.
    for (prov, frag), (pp, cp) in _COST_PRICES.items():
        if prov == provider and (not frag or frag in (model_id or "")):
            return (prompt_tokens * pp + out_tokens * cp) / 1_000_000

    # Прайс неизвестен — не 0.0, а None (залогирует вызывающий).
    return None


# ──────────────────────────────────────────────────────────────────────────
# Вызов по цепочке провайдеров
# ──────────────────────────────────────────────────────────────────────────

def call_llm(
    logical_model: str,
    messages: List[dict],
    max_tokens: int = 4096,
    timeout: Tuple[float, float] = (15, 300),
    logger=None,
    role: str = "legacy_reasoner",
    thinking_mode: Optional[str] = None,
    response_format: Optional[dict] = None,
) -> dict:
    """Вызвать LLM по цепочке провайдеров для логической модели.

    CH20:
      * max_tokens берётся по роли (если не задан явно — default 4096);
      * thinking-политика по роли (disabled для base/aux/audit);
      * при reasoning_overflow/truncated выполняются внутренние retry
        (thinking disabled -> max_tokens*2);
      * 3 подряд транспортные ошибки -> провайдер недоступен 10 минут.

    Возвращает dict с content/cost_usd/model_id/provider/latency_ms/usage,
    а также think_mode / finish_reason / reasoning_tokens / prompt_tokens /
    completion_tokens для диагностики.
    """
    import requests  # noqa: F401

    if thinking_mode is None:
        thinking_mode = thinking_mode_for_role(role)

    # REC-5: цепочка провайдеров по роли (с env-override конкретного провайдера).
    providers = ROLE_PROVIDER_ORDER.get(role)
    if providers is None:
        providers = PROVIDER_ORDER
    # Env-override: конкретный провайдер для роли ставится первым.
    env_provider = (os.environ.get(ROLE_PROVIDER_ENV.get(role, "")) or "").strip()
    if env_provider:
        providers = tuple([env_provider] + [p for p in providers if p != env_provider])

    # BATCH FIX: Gemini (роли base/aux/audit) идёт ТОЛЬКО через OdiRouter.
    # Если OdiRouter лёг с 401 (FAILED_TO_AUTH), цепочка пустеет и задача падает.
    # Здесь подставляем fallback-цепочку DeepSeek для Gemini-ролей, чтобы
    # планировщик не умирал из-за сбоя одного провайдера.
    chain = build_provider_chain(logical_model, providers=providers)
    if not chain and logical_model in ("gemini-3.7-flash", "claude-sonnet-4-6", "claude-sonnet-4-5"):
        fallback_providers = tuple(p for p in ("deepseek_direct", "novita", "deepseek")
                                   if p not in providers)
        chain = build_provider_chain("deepseek-v4-pro", providers=fallback_providers)
        if chain and logger:
            logger.warning(
                "[llm_router] PLANNER_FALLBACK: logical=%s → deepseek-v4-pro "
                "(providers=%s)", logical_model, [c["provider"] for c in chain]
            )
    if not chain:
        raise LLMError(
            "LLM_NO_PROVIDER",
            f"нет доступного провайдера для модели '{logical_model}'",
            model_id=logical_model,
            retryable=False,
        )

    # Внутренние retry-стратегии (CH20):
    #   1) reasoning overflow -> retry с thinking disabled;
    #   2) thinking уже disabled + length -> retry с max_tokens*2 (один раз).
    for strategy in range(3):
        eff_thinking = thinking_mode
        eff_max_tokens = max_tokens
        if strategy == 1:
            eff_thinking = "disabled"
        elif strategy == 2:
            eff_max_tokens = max_tokens * 2

        last_error: Optional[LLMError] = None
        for cfg in chain:
            provider = cfg["provider"]
            model_id = cfg["model_id"]
            payload = {
                "model": model_id,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": eff_max_tokens,
            }
            # REC-8: принудительный JSON (OdiRouter/Gemini и DeepSeek понимают).
            if response_format:
                payload["response_format"] = response_format
            # thinking-параметр (disabled/enabled) — только если поддерживается.
            if eff_thinking == "disabled" and not is_thinking_unsupported(provider, model_id):
                payload["thinking"] = {"type": "disabled"}
            elif eff_thinking == "enabled" \
                    and provider in ("deepseek_direct", "odirouter") \
                    and not is_thinking_unsupported(provider, model_id):
                # Явное включение reasoning-канала: DeepSeek v4 (reasoner) и
                # Gemini (OdiRouter) получают «глубокое мышление».
                payload["thinking"] = {"type": "enabled"}

            start = time.perf_counter()
            try:
                resp = requests.post(
                    cfg["base_url"],
                    headers={"Authorization": f"Bearer {cfg['api_key']}",
                             "Content-Type": "application/json"},
                    json=payload,
                    timeout=timeout,
                )
            except requests.exceptions.Timeout as e:
                latency = (time.perf_counter() - start) * 1000
                if logger:
                    logger.warning("[llm_router] provider=%s model=%s timeout %s",
                                   provider, model_id, type(e).__name__)
                last_error = LLMError("LLM_TIMEOUT", str(e), provider, model_id,
                                      retryable=True)
                continue
            except requests.exceptions.RequestException as e:
                latency = (time.perf_counter() - start) * 1000
                # CH20: 3 подряд транспортные ошибки -> провайдер недоступен на 10 мин.
                if record_transport_error(provider, model_id):
                    if logger:
                        logger.warning("[llm_router] PROVIDER_MODEL_UNREACHABLE: provider=%s "
                                       "model=%s transport_errors>=%d", provider, model_id,
                                       PROVIDER_UNREACHABLE_THRESHOLD)
                if logger:
                    logger.warning("[llm_router] provider=%s model=%s transport %s",
                                   provider, model_id, type(e).__name__)
                last_error = LLMError("LLM_TRANSPORT", str(e), provider, model_id,
                                      retryable=True)
                continue

            reset_transport_errors(provider, model_id)
            latency = (time.perf_counter() - start) * 1000
            status = resp.status_code

            if status != 200:
                body = None
                try:
                    body = resp.json()
                except Exception:
                    body = None
                code = classify_status(status, body)
                # 400 из-за неизвестного параметра "thinking" — повторить без него.
                if status == 400 and eff_thinking == "disabled" and \
                        "thinking" in (resp.text or "").lower():
                    mark_thinking_unsupported(provider, model_id)
                    if logger:
                        logger.info("[llm_router] THINKING_PARAM_UNSUPPORTED provider=%s "
                                    "model=%s — retry without thinking param",
                                    provider, model_id)
                    # Повторяем этот же провайдер БЕЗ thinking (не fatal).
                    continue
                if code == "LLM_MODEL_NOT_FOUND":
                    mark_model_unavailable(provider, model_id)
                if logger:
                    logger.warning("[llm_router] provider=%s model=%s %s body=%s",
                                   provider, model_id, code, _safe_error_body(resp))
                retryable = code in ("LLM_RATE_LIMIT", "LLM_SERVER_ERROR",
                                     "LLM_HTTP_ERROR", "LLM_NOT_FOUND")
                last_error = LLMError(code, _safe_error_body(resp), provider,
                                      model_id, retryable=retryable)
                continue

            # 200 OK
            try:
                body = resp.json()
            except Exception as e:
                if logger:
                    logger.warning("[llm_router] provider=%s model=%s bad json %s",
                                   provider, model_id, e)
                last_error = LLMError("LLM_BAD_RESPONSE", str(e), provider,
                                      model_id, retryable=True)
                continue

            usage = body.get("usage", {}) or {}
            finish_reason = ""
            choices = body.get("choices") or []
            raw_content = ""
            if choices:
                finish_reason = (choices[0].get("finish_reason") or "")
                raw_content = (choices[0].get("message") or {}).get("content") or ""

            # reasoning-токены (поле может отличаться у провайдеров).
            det = usage.get("completion_tokens_details") or {}
            reasoning_tokens = (
                int(usage.get("reasoning_tokens", 0) or 0)
                or int(det.get("reasoning_tokens", 0) or 0)
            )

            content, lengths = extract_response_text(body)
            has_reasoning = lengths["reasoning_content"] > 0 or lengths["reasoning"] > 0
            # CH20: overflow/truncated судим по СЫРОМУ content, а не по
            # extract_response_text (который подставляет reasoning как fallback).
            raw_content_empty = not (raw_content or "").strip()

            # ── CH20: reasoning overflow / truncated ──
            if raw_content_empty and has_reasoning and finish_reason == "length":
                if logger:
                    logger.warning("[llm_router] LLM_REASONING_OVERFLOW provider=%s "
                                   "model=%s max_tokens=%s thinking=%s",
                                   provider, model_id, eff_max_tokens, eff_thinking)
                if strategy == 0:
                    # retry с thinking disabled.
                    last_error = LLMError("LLM_REASONING_OVERFLOW",
                                          "reasoning consumed budget",
                                          provider, model_id, retryable=True)
                    break  # -> следующий strategy
                # thinking уже disabled — не ретраим больше.
                last_error = LLMError("LLM_REASONING_OVERFLOW",
                                      "reasoning overflow", provider, model_id,
                                      retryable=False)
                break

            if raw_content_empty and finish_reason == "length" and eff_thinking == "disabled":
                if logger:
                    logger.warning("[llm_router] LLM_TRUNCATED provider=%s model=%s "
                                   "max_tokens=%s", provider, model_id, eff_max_tokens)
                if strategy < 2:
                    last_error = LLMError("LLM_TRUNCATED", "output truncated",
                                          provider, model_id, retryable=True)
                    break  # -> strategy 2 (max_tokens*2)
                last_error = LLMError("LLM_TRUNCATED", "output truncated",
                                      provider, model_id, retryable=False)
                break

            if not content:
                last_error = LLMError(
                    "LLM_EMPTY_CONTENT",
                    f"пустой ответ (lengths={lengths})",
                    provider, model_id, retryable=True,
                )
                continue

            cost_usd = compute_cost(provider, usage, model_id)
            if cost_usd is None:
                if logger:
                    logger.warning("[llm_router] COST_PRICE_UNKNOWN provider=%s model=%s",
                                   provider, model_id)
                cost_usd = 0.0
            if logger:
                logger.info(
                    "[llm_router] role=%s provider=%s model_id=%s thinking=%s "
                    "max_tokens=%s prompt_tokens=%s completion_tokens=%s "
                    "reasoning_tokens=%s finish_reason=%s http_status=%s latency_ms=%.0f",
                    role, provider, model_id, eff_thinking, eff_max_tokens,
                    usage.get("prompt_tokens", 0) or 0,
                    usage.get("completion_tokens", 0) or 0,
                    reasoning_tokens, finish_reason or "-", status, latency,
                )
            return {
                "content": content,
                "cost_usd": cost_usd,
                "model": model_id,
                "provider": provider,
                "model_id": model_id,
                "latency_ms": latency,
                "usage": usage,
                "thinking_mode": eff_thinking,
                "finish_reason": finish_reason,
                "reasoning_tokens": reasoning_tokens,
            }

        # Проверить, нужно ли переходить к следующему strategy.
        if last_error is not None and last_error.retryable:
            continue
        if last_error is not None:
            # BATCH FIX: Gemini/Claude роли (base/aux/audit) на OdiRouter при 401
            # (FAILED_TO_AUTH) не имеют следующего провайдера в цепочке —
            # однократно переключаемся на DeepSeek, чтобы задача не падала.
            if (logical_model in ("gemini-3.7-flash", "claude-sonnet-4-6", "claude-sonnet-4-5")
                    and getattr(last_error, "code", "") == "LLM_AUTH_ERROR"):
                fb_chain = build_provider_chain("deepseek-v4-pro",
                                                providers=("deepseek_direct", "novita", "deepseek"))
                for cfg in fb_chain:
                    try:
                        payload = {
                            "model": cfg["model_id"],
                            "messages": messages,
                            "temperature": 0.1,
                            "max_tokens": max_tokens,
                        }
                        if response_format:
                            payload["response_format"] = response_format
                        r = requests.post(
                            cfg["base_url"],
                            headers={"Authorization": f"Bearer {cfg['api_key']}",
                                     "Content-Type": "application/json"},
                            json=payload,
                            timeout=timeout,
                        )
                        if r.status_code == 200:
                            body = r.json()
                            content, _ = extract_response_text(body)
                            usage = body.get("usage", {}) or {}
                            if logger:
                                logger.warning(
                                    "[llm_router] GEMINI_401_FALLBACK_OK provider=%s model=%s",
                                    cfg["provider"], cfg["model_id"],
                                )
                            return {
                                "content": content,
                                "cost_usd": compute_cost(cfg["provider"], usage, cfg["model_id"]) or 0.0,
                                "model": cfg["model_id"],
                                "provider": cfg["provider"],
                                "model_id": cfg["model_id"],
                                "latency_ms": 0.0,
                                "usage": usage,
                                "thinking_mode": "disabled",
                                "finish_reason": "stop",
                                "reasoning_tokens": 0,
                            }
                    except Exception:
                        continue
            raise last_error

    # Все стратегии исчерпаны.
    if last_error is not None:
        raise last_error
    raise LLMError("LLM_UNKNOWN", "неизвестная ошибка LLM", retryable=False)


# ──────────────────────────────────────────────────────────────────────────
# Self-check (без реальных запросов)
# ──────────────────────────────────────────────────────────────────────────

def describe_roles() -> List[dict]:
    """Описание резолва по ролям (для startup self-check)."""
    rows = []
    for role in ROLE_DEFAULT_MODEL:
        logical = logical_model_for_role(role)
        chain = build_provider_chain(logical)
        rows.append({
            "role": role,
            "logical_model": logical,
            "providers": [{"provider": c["provider"], "model_id": c["model_id"]}
                          for c in chain],
            "mapped": {p: resolve_provider_model(logical, p)
                       for p in PROVIDER_ORDER},
        })
    return rows
