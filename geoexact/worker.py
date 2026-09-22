"""A disposable subprocess isolates numerical work from HTTP request threads."""
import json
import os
import sys
from dataclasses import asdict


def main():
    # Enforce a wall-clock limit even if Gunicorn dies and this child is orphaned.
    import signal
    signal.signal(signal.SIGALRM, lambda *_: os._exit(124))
    signal.alarm(590)
    from .jobs import failure
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print(json.dumps(failure("NOT_CONFIGURED", "Сервис ещё не настроен.")))
        return
    from .core.pipeline import generate
    from .core.llm import Budget
    data = json.load(sys.stdin)
    result = generate(data["problem"], data["with_aux"],
                      budget=Budget(cap=.10), use_cache=False)
    payload = asdict(result)
    # No model plans, token logs, internal API errors, costs or traces in the client.
    for field in ("plan", "usage", "cost", "seconds", "retries", "cls"):
        payload.pop(field, None)
    if not result.ok:
        payload = failure(result.reason,
            "Не удалось построить проверенный чертёж. Проверьте полноту и "
            "непротиворечивость условия. Некоторые конфигурации пока не поддерживаются.")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
