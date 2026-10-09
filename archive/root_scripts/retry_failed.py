# -*- coding: utf-8 -*-
"""Добор непостроенных чертежей — три волны с нарастающим нажимом.

Волна 1: обычная модель, ужесточённый договор, две попытки.
Волна 2: требование упростить конфигурацию до минимума, две попытки.
Волна 3: сильная модель deepseek-v4-pro, две попытки.

Нечертёжные задачи (стереометрия, комбинаторика, алгебра) не трогаются:
модель их уже честно отклонила.

Запуск:
    $env:DEEPSEEK_API_KEY="ключ"
    python retry_failed.py geometry_missing_figures_with_solutions.json --workers 8

В конце собирает все чертежи в одну папку out\\figures_all.
"""
import argparse
import importlib.util
import json
import pathlib
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).parent
_sp = importlib.util.spec_from_file_location("ff", HERE / "formyla_figures.py")
ff = importlib.util.module_from_spec(_sp)
_sp.loader.exec_module(ff)

BASE_EXTRA = """
ВАЖНО, прошлый раз сломалось именно на этом:
- Каждое имя из draw, marks, draw_aux обязано быть объявлено в given или aux.
  Перед отправкой пройди свой ответ построчно и проверь это сам.
- Не используй имена из одной цифры и имена с апострофом. Вместо A' пиши A1.
- Не объявляй две точки, которые по построению совпадут: они сольются.
- Не выноси точку далеко за пределы фигуры: чертёж масштабируется по всем точкам,
  и одна далёкая точка сожмёт остальное в кашу. Если без неё смысл не теряется — не объявляй.
- Чем меньше точек, тем лучше.
"""

SIMPLIFY = """
Предыдущие попытки не построились. Теперь задача другая: сделай МИНИМАЛЬНЫЙ чертёж.
- Объяви только те точки, без которых условие непонятно. Всё остальное выбрось.
- Никаких точек пересечения вспомогательных прямых, никаких вторых окружностей,
  никаких симметричных образов, если они не названы прямо в вопросе задачи.
- Если в условии есть произвольная или бегущая точка — поставь её в одном
  удобном положении и не строй от неё длинных цепочек.
- Блок aux оставь пустым.
Лучше бедный, но правильный чертёж, чем богатый и несобираемый.
"""

CONTRACT0 = ff.CONTRACT


def collect(journal):
    last = {}
    if journal.exists():
        for line in journal.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            last[r["uid"]] = r["status"]
    return last


def attempt(task, outdir, notes, seeds):
    """одна попытка. возвращает ('ok'|'skip'|'fail', заметка, семян)"""
    uid = task["task_uid"]
    try:
        spec, usage = ff.ask_model(task, notes)
    except RuntimeError:
        time.sleep(20)
        return "fail", "429", 0
    except Exception as e:
        return "fail", f"{type(e).__name__}: {e}"[:200], 0
    with ff.lock:
        ff.stat["in"] += usage.get("prompt_tokens", 0)
        ff.stat["out"] += usage.get("completion_tokens", 0)
    try:
        spec = ff.normalize(spec)
    except Exception as e:
        return "fail", f"кривой ответ: {e}"[:200], 0
    if "skip" in spec:
        return "skip", spec["skip"], 0
    bad = ff.validate_spec(spec)
    if bad:
        return "fail", "; ".join(bad)[:300], 0
    svg, tries, errs = ff.draw(spec, 1, seeds)
    if svg is None:
        return "fail", "; ".join(errs)[:300], 0
    (outdir / f"{uid}.svg").write_text(svg, encoding="utf-8")
    (outdir / f"{uid}.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    if isinstance(spec.get("aux"), list) and spec["aux"]:
        merged = dict(spec)
        merged["given"] = spec["given"] + spec["aux"]
        merged["draw"] = spec["draw"] + spec.get("draw_aux", [])
        s2, _, _ = ff.draw(merged, 1, seeds)
        if s2:
            (outdir / f"{uid}_aux.svg").write_text(s2, encoding="utf-8")
    return "ok", f"семян: {tries}", tries


def worker(task, outdir, logf, tries_n, seeds, tag):
    uid = task["task_uid"]
    t0 = time.time()
    notes = None
    for i in range(tries_n):
        st, note, _ = attempt(task, outdir, notes, seeds)
        if st == "ok":
            with ff.lock:
                ff.stat["ok"] += 1
            ff.write_log(logf, uid, "ok", i + 1, f"{tag}, {note}", time.time() - t0)
            return True
        if st == "skip":
            with ff.lock:
                ff.stat["skip"] += 1
            ff.write_log(logf, uid, "skip", i + 1, note, time.time() - t0)
            return True
        notes = note
    print(f"  --- {uid[:8]} {tag} не дал результата: {notes[:70]}", flush=True)
    return False


def wave(tasks, outdir, logf, workers, contract, tries_n, seeds, model, tag):
    if not tasks:
        return []
    ff.CONTRACT = contract
    ff.MODEL = model
    print(f"\n=== {tag}: задач {len(tasks)}, модель {model}, "
          f"попыток {tries_n}, семян {seeds} ===", flush=True)
    left = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(worker, t, outdir, logf, tries_n, seeds, tag): t for t in tasks}
        for f, t in futs.items():
            try:
                ok = f.result()
            except Exception as e:
                print(f"  !!! сбой потока: {e}", flush=True)
                ok = False
            if not ok:
                left.append(t)
    print(f"=== {tag}: осталось {len(left)} ===", flush=True)
    return left


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default="out")
    ap.add_argument("--pro-model", default="deepseek-v4-pro")
    ap.add_argument("--no-pro", action="store_true", help="без третьей волны")
    a = ap.parse_args()

    if not ff.API_KEY:
        print("нет ключа: задай DEEPSEEK_API_KEY")
        sys.exit(1)

    outdir = pathlib.Path(a.out) / "figures"
    outdir.mkdir(parents=True, exist_ok=True)
    journal = pathlib.Path(a.out) / "figures_batch.jsonl"

    last = collect(journal)
    todo = {u for u, st in last.items() if st == "fail"}
    todo -= {u for u, st in last.items() if st in ("ok", "skip")}
    todo -= {p.stem for p in outdir.glob("*.svg")}

    data = json.loads(pathlib.Path(a.tasks).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("tasks") or data.get("items") or []
    tasks = [t for t in data if t.get("task_uid") in todo]

    print(f"к добору: {len(tasks)} | потоков: {a.workers}")
    t0 = time.time()
    if tasks:
        with open(journal, "a", encoding="utf-8") as logf:
            left = wave(tasks, outdir, logf, a.workers,
                        CONTRACT0 + BASE_EXTRA, 2, 200, ff.MODEL, "волна 1")
            left = wave(left, outdir, logf, a.workers,
                        CONTRACT0 + BASE_EXTRA + SIMPLIFY, 2, 300,
                        ff.MODEL, "волна 2, упрощение")
            if not a.no_pro:
                left = wave(left, outdir, logf, max(2, a.workers // 2),
                            CONTRACT0 + BASE_EXTRA + SIMPLIFY, 2, 300,
                            a.pro_model, "волна 3, сильная модель")
        print(f"\nнепостроено окончательно: {len(left)}")
        for t in left:
            print("   ", t["task_uid"][:12], t["text"][:80].replace("\n", " "))
        cost = ff.stat["in"] / 1e6 * 0.14 + ff.stat["out"] / 1e6 * 0.28
        print(f"\nтокенов вход {ff.stat['in']}, выход {ff.stat['out']}")
        print(f"стоимость по тарифу Flash: ${cost:.3f} | время: {(time.time()-t0)/60:.1f} мин")
        print("волна 3 считается по тарифу Pro, он в три раза дороже")

    allx = pathlib.Path(a.out) / "figures_all"
    allx.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in outdir.glob("*.svg"):
        dst = allx / f.name
        if not dst.exists() or dst.stat().st_mtime < f.stat().st_mtime:
            shutil.copy2(f, dst)
            n += 1
    aux = len(list(allx.glob("*_aux.svg")))
    base = len(list(allx.glob("*.svg"))) - aux
    print(f"\nпапка {allx}: скопировано {n}")
    print(f"  чертежей: {base}, из них с доп. построением ещё {aux}")


if __name__ == "__main__":
    main()
