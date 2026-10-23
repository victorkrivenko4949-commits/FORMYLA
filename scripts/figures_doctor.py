# -*- coding: utf-8 -*-
"""scripts/figures_doctor.py — дешёвая проверка резолва ролей.

По умолчанию только печатает резолв (без запросов).  С флагом --live делает
один ping-запрос на роль (max_tokens=16), чтобы убедиться, что провайдер
и provider-native модель работают.  Не создаёт job, не списывает кредиты,
не пишет в БД.  Не печатает значения секретных ключей.
"""
import argparse
import os
import sys


def _load_dotenv(path=".env"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip(); v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except FileNotFoundError:
        pass


def main():
    ap = argparse.ArgumentParser(description="FIGURES LLM router doctor")
    ap.add_argument("--live", action="store_true",
                    help="сделать один дешёвый ping-запрос на роль")
    ap.add_argument("--role", default="base",
                    choices=["base", "aux", "repair", "audit", "legacy_reasoner"],
                    help="роль для live-проверки")
    args = ap.parse_args()

    _load_dotenv()
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.insert(0, _root)

    from services.llm_router import (
        describe_roles, logical_model_for_role, build_provider_chain,
        call_llm,
    )

    print("ROLE RESOLVE (без реальных запросов):")
    for row in describe_roles():
        print(f"  {row['role']:<16} logical={row['logical_model']:<18} "
              f"providers={row['providers']} mapped={row['mapped']}")

    if not args.live:
        print("\n(для live-проверки добавьте --live)")
        return

    logical = logical_model_for_role(args.role)
    chain = build_provider_chain(logical)
    print(f"\nLIVE ping для роли {args.role!r} (logical={logical}):")
    if not chain:
        print("  нет доступных провайдеров")
        return
    try:
        result = call_llm(logical, [{"role": "user", "content": "ping"}],
                          max_tokens=16)
        print("  OK provider=", result["provider"], "model_id=",
              result["model_id"], "latency_ms=", round(result["latency_ms"]),
              "content[:80]=", repr(result["content"][:80]))
    except Exception as e:
        print("  FAIL:", type(e).__name__, str(e)[:300])


if __name__ == "__main__":
    main()
