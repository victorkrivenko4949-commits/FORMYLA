#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DeepSeek Reasoner API smoke test for L1-L3 generation pipeline.

Tests:
  1. DNS resolution for api.deepseek.com
  2. TCP connectivity (port 443)
  3. TLS handshake
  4. API authentication (models endpoint)
  5. Model availability (deepseek-reasoner)
  6. JSON response parsing (lightweight chat completion)

Output:
  - l1_l3_generation/smoke_test_deepseek.json       — full test results
  - l1_l3_generation/smoke_test_deepseek_audit.json  — audit verdict
"""

import os
import sys
import json
import socket
import ssl
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SMOKE_PATH = os.path.join(BASE_DIR, "smoke_test_deepseek.json")
AUDIT_PATH = os.path.join(BASE_DIR, "smoke_test_deepseek_audit.json")

API_HOST = "api.deepseek.com"
API_PORT = 443
API_BASE = f"https://{API_HOST}"
MODEL_NAME = "deepseek-reasoner"

# Lightweight test prompt — minimal tokens, validates JSON contract
TEST_MESSAGES = [
    {"role": "user", "content": "Respond with {\"answer\": 42} only."}
]

# ============================================================================
# Helper
# ============================================================================

def _load_api_key() -> str:
    """Load DEEPSEEK_API_KEY from .env or environment."""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    # Try .env
    env_path = os.path.join(os.path.dirname(BASE_DIR), ".env")
    if not os.path.exists(env_path):
        env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, "r", encoding="utf-8").readlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY") and "=" in line:
                key = line.split("=", 1)[1].strip().strip("\"'").strip()
                break
    return key


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_result(name: str, passed: bool, detail: str, duration_ms: float = None) -> dict:
    return {
        "test_name": name,
        "passed": passed,
        "detail": detail,
        "duration_ms": round(duration_ms, 1) if duration_ms is not None else None,
        "timestamp": _timestamp(),
    }


# ============================================================================
# Smoke tests
# ============================================================================

def test_dns() -> dict:
    """SMOKE 1: DNS resolution."""
    import time
    t0 = time.time()
    try:
        addrs = socket.getaddrinfo(API_HOST, API_PORT)
        ip = addrs[0][4][0]
        elapsed = (time.time() - t0) * 1000
        return _make_result("dns_resolution", True, f"Resolved {API_HOST} -> {ip}", elapsed)
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        return _make_result("dns_resolution", False, f"DNS failure: {e}", elapsed)


def test_tcp_connect() -> dict:
    """SMOKE 2: TCP connectivity."""
    import time
    t0 = time.time()
    try:
        sock = socket.create_connection((API_HOST, API_PORT), timeout=10)
        sock.close()
        elapsed = (time.time() - t0) * 1000
        return _make_result("tcp_connectivity", True, f"TCP handshake to {API_HOST}:{API_PORT} succeeded", elapsed)
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        return _make_result("tcp_connectivity", False, f"TCP failure: {e}", elapsed)


def test_tls_handshake() -> dict:
    """SMOKE 3: TLS handshake."""
    import time
    t0 = time.time()
    try:
        ctx = ssl.create_default_context()
        sock = socket.create_connection((API_HOST, API_PORT), timeout=15)
        ssock = ctx.wrap_socket(sock, server_hostname=API_HOST)
        cipher = ssock.cipher()[0]
        version = ssock.version()
        ssock.close()
        elapsed = (time.time() - t0) * 1000
        return _make_result("tls_handshake", True, f"TLS {version}, cipher={cipher}", elapsed)
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        return _make_result("tls_handshake", False, f"TLS failure: {e}", elapsed)


def test_models_endpoint(api_key: str) -> dict:
    """SMOKE 4: API authentication via models list endpoint."""
    import time
    t0 = time.time()
    try:
        req = urllib.request.Request(
            f"{API_BASE}/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        resp = urllib.request.urlopen(req, timeout=15)
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        elapsed = (time.time() - t0) * 1000

        models = data.get("data", [])
        model_ids = [m.get("id", "") for m in models] if isinstance(models, list) else []

        detail = f"HTTP {resp.status}, {len(model_ids)} models returned"
        return _make_result("models_endpoint", True, detail, elapsed)
    except urllib.error.HTTPError as e:
        elapsed = (time.time() - t0) * 1000
        body = e.read().decode("utf-8", errors="replace")
        return _make_result("models_endpoint", False, f"HTTP {e.code}: {body[:200]}", elapsed)
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        return _make_result("models_endpoint", False, f"Request failure: {e}", elapsed)


def test_model_availability(api_key: str) -> dict:
    """
    SMOKE 5: Check that deepseek-reasoner is available.
    
    Some API providers alias model names (deepseek-reasoner may resolve to
    deepseek-v4-pro internally). We check:
      1. Is the model name in the listing?
      2. If not, does a lightweight chat-completion call succeed?
    """
    import time
    import json as json_mod
    t0 = time.time()
    try:
        req = urllib.request.Request(
            f"{API_BASE}/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        resp = urllib.request.urlopen(req, timeout=15)
        body = resp.read().decode("utf-8")
        data = json.loads(body)
        elapsed = (time.time() - t0) * 1000

        models = data.get("data", [])
        model_ids = [m.get("id", "") for m in models] if isinstance(models, list) else []

        if MODEL_NAME in model_ids:
            return _make_result("model_availability", True, f"{MODEL_NAME} found in model list", elapsed)

        # Model not in listing — try a lightweight validation call
        t1 = time.time()
        payload = json_mod.dumps({
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": "Respond with 1"}],
            "max_tokens": 5,
        }).encode("utf-8")

        val_req = urllib.request.Request(
            f"{API_BASE}/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        val_resp = urllib.request.urlopen(val_req, timeout=30)
        val_elapsed = (time.time() - t1) * 1000
        total_elapsed = (time.time() - t0) * 1000

        if val_resp.status == 200:
            return _make_result(
                "model_availability", True,
                f"{MODEL_NAME} not in listing (listed: {model_ids[:4]}) "
                f"but API call succeeded ({val_elapsed:.0f}ms) — alias confirmed",
                total_elapsed,
            )
        else:
            return _make_result(
                "model_availability", False,
                f"{MODEL_NAME} not in listing and API call returned HTTP {val_resp.status}",
                total_elapsed,
            )
    except urllib.error.HTTPError as e:
        elapsed = (time.time() - t0) * 1000
        return _make_result("model_availability", False, f"HTTP {e.code}", elapsed)
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        return _make_result("model_availability", False, f"Failure: {e}", elapsed)


def test_chat_completion(api_key: str) -> dict:
    """
    SMOKE 6: Lightweight chat completion call to deepseek-reasoner.
    Verifies JSON response parsing.
    """
    import time
    import json as json_mod
    t0 = time.time()
    payload = json_mod.dumps({
        "model": MODEL_NAME,
        "messages": TEST_MESSAGES,
        "max_tokens": 50,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"{API_BASE}/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=60)
        body = resp.read().decode("utf-8")
        data = json_mod.loads(body)
        elapsed = (time.time() - t0) * 1000

        # Validate response structure
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        finish_reason = choice.get("finish_reason", "")
        usage = data.get("usage", {})

        valid = bool(content) and finish_reason in ("stop", "length")

        detail_parts = [
            f"HTTP {resp.status}",
            f"finish_reason={finish_reason}",
            f"content_len={len(content)}",
        ]
        if usage:
            detail_parts.append(f"prompt_tokens={usage.get('prompt_tokens', '?')}")
            detail_parts.append(f"completion_tokens={usage.get('completion_tokens', '?')}")
            # Check for reasoning_tokens (deepseek-reasoner specific)
            if "completion_tokens_details" in usage:
                det = usage["completion_tokens_details"]
                detail_parts.append(f"reasoning_tokens={det.get('reasoning_tokens', '?')}")

        return _make_result(
            "chat_completion", valid,
            "; ".join(detail_parts), elapsed
        )
    except urllib.error.HTTPError as e:
        elapsed = (time.time() - t0) * 1000
        body = e.read().decode("utf-8", errors="replace")[:300]
        return _make_result("chat_completion", False, f"HTTP {e.code}: {body}", elapsed)
    except json_mod.JSONDecodeError as e:
        elapsed = (time.time() - t0) * 1000
        return _make_result("chat_completion", False, f"JSON parse failure: {e}", elapsed)
    except Exception as e:
        elapsed = (time.time() - t0) * 1000
        return _make_result("chat_completion", False, f"Request failure: {e}", elapsed)


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 60)
    print("DeepSeek Reasoner API — Smoke Test")
    print(f"Target: {API_HOST}, Model: {MODEL_NAME}")
    print(f"Started: {_timestamp()}")
    print("=" * 60)

    # Load API key
    api_key = _load_api_key()
    key_masked = api_key[:8] + "..." + api_key[-4:] if api_key else "(none)"
    print(f"\nAPI Key: {key_masked}")
    if not api_key:
        print("ERROR: No API key found. Aborting.")
        sys.exit(1)

    # Run tests sequentially (network tests first, then API)
    tests = [
        test_dns(),
        test_tcp_connect(),
        test_tls_handshake(),
    ]

    # Only proceed to API tests if network stack is OK
    network_ok = all(t["passed"] for t in tests)
    if network_ok:
        tests.append(test_models_endpoint(api_key))
        tests.append(test_model_availability(api_key))
        # Only attempt chat completion if models endpoint succeeded
        if tests[-2]["passed"]:
            tests.append(test_chat_completion(api_key))
        else:
            tests.append(_make_result("chat_completion", False, "Skipped — models endpoint failed", None))
    else:
        tests.append(_make_result("models_endpoint", False, "Skipped — network layer failed", None))
        tests.append(_make_result("model_availability", False, "Skipped — network layer failed", None))
        tests.append(_make_result("chat_completion", False, "Skipped — network layer failed", None))

    # Compute overall verdict
    all_pass = all(t["passed"] for t in tests)
    verdict = "PASS" if all_pass else "FAIL"

    # Print results
    print(f"\n{'':-^60}")
    for t in tests:
        status = "PASS" if t["passed"] else "FAIL"
        dur = f" ({t['duration_ms']}ms)" if t["duration_ms"] is not None else ""
        print(f"  [{status}] {t['test_name']}{dur}")
        print(f"         {t['detail']}")
    print(f"{'':-^60}")
    print(f"\n  OVERALL VERDICT: {verdict}")
    print()

    # Build smoke_test_deepseek.json
    smoke_data = {
        "meta": {
            "pipeline_step": "smoke_test",
            "target": f"https://{API_HOST}",
            "model": MODEL_NAME,
            "api_key_masked": key_masked,
            "timestamp": _timestamp(),
            "duration_ms": sum(t["duration_ms"] for t in tests if t["duration_ms"] is not None),
        },
        "tests": tests,
        "verdict": verdict,
    }

    # Build audit
    audit = {
        "meta": {
            "pipeline_step": "smoke_test_audit",
            "source": "smoke_test_deepseek.json",
            "timestamp": _timestamp(),
        },
        "verdict": verdict,
        "all_tests_passed": all_pass,
        "tests_summary": [
            {"name": t["test_name"], "passed": t["passed"]}
            for t in tests
        ],
        "passed_count": sum(1 for t in tests if t["passed"]),
        "total_count": len(tests),
        "invariants": {
            "dns_resolution_ok": tests[0]["passed"],
            "tcp_connectivity_ok": tests[1]["passed"],
            "tls_handshake_ok": tests[2]["passed"],
            "api_authentication_ok": tests[3]["passed"] if len(tests) > 3 else False,
            "model_available": tests[4]["passed"] if len(tests) > 4 else False,
            "chat_completion_ok": tests[5]["passed"] if len(tests) > 5 else False,
        },
        "status": "SMOKE_OK" if all_pass else "SMOKE_FAIL",
    }

    # Write files
    os.makedirs(BASE_DIR, exist_ok=True)

    with open(SMOKE_PATH, "w", encoding="utf-8") as f:
        json.dump(smoke_data, f, indent=2, ensure_ascii=False)
    print(f"Wrote: {SMOKE_PATH}")

    with open(AUDIT_PATH, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)
    print(f"Wrote: {AUDIT_PATH}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
