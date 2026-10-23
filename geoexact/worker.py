"""A disposable subprocess isolates numerical work from HTTP request threads."""
import json
import os
import sys
import traceback
from dataclasses import asdict


def main():
    # Enforce a wall-clock limit even if Gunicorn dies and this child is orphaned.
    import signal
    signal.signal(signal.SIGALRM, lambda *_: os._exit(124))
    # Just after the pipeline's own limit; jobs.py then serves the keyword sketch.
    signal.alarm(int(min(290, float(os.getenv("GEOEXACT_TIME_LIMIT", "170")) + 25)))
    from .jobs import failure
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print(json.dumps(failure("NOT_CONFIGURED", "Сервис ещё не настроен.")))
        return
    from .core.pipeline import generate
    from .core.llm import Budget
    data = json.load(sys.stdin)
    if data.get("solution"):
        # «Полное решение»: тот же диалог с экспертом + оформление LaTeX.
        from .core.solution import generate_solution
        payload = generate_solution(data["problem"], data.get("history") or None)
        print(json.dumps(payload, ensure_ascii=False))
        return
    try:
        result = generate(data["problem"], data["with_aux"],
                          budget=Budget(cap=.10), use_cache=False,
                          aux_history=data.get("history") or None)
    except Exception as exc:  # noqa: BLE001 - показать место падения, а не «не удалось»
        # Раньше любое исключение конвейера давало безликое WORKER_ERROR по коду
        # возврата, и найти причину можно было только в логах сервера. Теперь
        # traceback уходит в stderr (журнал), а пользователь видит класс ошибки
        # и модуль: по ним понятно, что сломалось, без утечки внутренних путей.
        traceback.print_exc(file=sys.stderr)
        tb = traceback.extract_tb(exc.__traceback__)
        where = ""
        for frame in reversed(tb):
            if "geoexact" in frame.filename.replace("\\", "/"):
                where = f" ({os.path.basename(frame.filename)}:{frame.lineno}, {frame.name})"
                break
        print(json.dumps(failure(
            "PIPELINE_CRASH",
            f"Внутренняя ошибка построения: {type(exc).__name__}{where}. "
            "Повторите запрос; если повторяется — это ошибка кода, а не условия."),
            ensure_ascii=False))
        return
    payload = asdict(result)
    # No model plans, token logs, internal API errors, costs or traces in the client.
    for field in ("plan", "usage", "cost", "seconds", "retries", "cls"):
        payload.pop(field, None)
    if not result.ok:
        detail = (result.detail if result.reason == "INVALID_CONDITION" else
                  "Не удалось построить проверенный чертёж. Проверьте полноту и "
                  "непротиворечивость условия. Некоторые конфигурации пока не поддерживаются.")
        payload = failure(result.reason, detail)
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
