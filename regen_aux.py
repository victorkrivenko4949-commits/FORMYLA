# -*- coding: utf-8 -*-
"""Регенерация чертежей: только с дополнительным построением.

Берёт задачи, у которых есть базовый .svg, но нет _aux.svg,
и прогоняет их заново с требованием найти в решении
дополнительное построение и показать его.

Если в решении нет доп. построения — задача пропускается честно.

Запуск:
    $env:DEEPSEEK_API_KEY="ключ"
    python regen_aux.py geometry_missing_figures_with_solutions.json --workers 6

В конце собирает все чертежи в out\\figures_all.
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

CONTRACT_AUX = """Ты — геометр. Твоя задача — построить чертёж к олимпиадной задаче
с ОБЯЗАТЕЛЬНЫМ дополнительным построением, которое помогает решить задачу.

Прочитай решение. Найди в нём дополнительное построение:
проведённую линию, построенную точку, достроение до фигуры,
симметрию, окружность, которая не дана в условии, но появляется в решении.

Это построение и есть главное на чертеже. Без него чертёж бесполезен.

Формат ответа — JSON:
{
  "given": [
    {"type": "triangle", "id": "ABC", "kind": "acute"},
    {"type": "midpoint", "id": "M", "of": "AB"},
    ...
  ],
  "aux": [
    {"type": "foot", "id": "D", "from": "A", "line": "BC"},
    ...
  ],
  "draw": [
    {"polygon": "ABC"},
    {"segment": "AM", "style": "soft"}
  ],
  "draw_aux": [
    {"segment": "AD", "style": "accent"},
    {"segment": "DM", "style": "accent"}
  ],
  "marks": [
    {"equal": ["MD", "ME"]},
    {"right": "ADB"}
  ]
}

given — точки и фигуры из условия задачи.
aux — точки и фигуры из дополнительного построения, которого нет в условии,
      но которое появляется в решении и делает задачу решаемой.
draw — что рисовать на базовом чертеже (только из условия).
draw_aux — что добавлять к чертежу из дополнительного построения.
marks — метки: равенство отрезков, прямые углы, равные углы.
        равные отрезки: {"equal": ["AB", "CD"]}
        прямой угол: {"right": "ADB"} (три точки, средняя — вершина)
        равные углы: {"angle": ["ABC", "DEF"]}

Типы построений:
triangle: {"type":"triangle","id":"ABC","kind":"acute|right|obtuse|isosceles|equilateral"}
quad: {"type":"quad","id":"ABCD","kind":"parallelogram|trapezoid|kite|cyclic|general"}
midpoint: {"type":"midpoint","id":"M","of":"AB"}
point_on_segment: {"type":"point_on_segment","id":"P","on":"AB","ratio":0.3}
foot: {"type":"foot","id":"D","from":"A","line":"BC"}
intersection: {"type":"intersection","id":"P","of":["AB","CD"]}
circumcenter: {"type":"circumcenter","id":"O","of":"ABC"}
incenter: {"type":"incenter","id":"I","of":"ABC"}
centroid: {"type":"centroid","id":"M","of":"ABC"}
orthocenter: {"type":"orthocenter","id":"H","of":"ABC"}
reflect_point: {"type":"reflect_point","id":"A'","of":"A","over":"BC"}
reflect_line: {"type":"reflect_line","id":"l'","of":"l","over":"BC"}
circle: {"type":"circle","id":"w","center":"O","radius":50}
circumcircle: {"type":"circumcircle","id":"w","of":"ABC"}
incircle: {"type":"incircle","id":"w","of":"ABC"}
point_on_circle: {"type":"point_on_circle","id":"P","on":"w","angle":45}
line_circle: {"type":"line_circle","id":"P","line":"AB","circle":"w","pick":0}
circle_circle: {"type":"circle_circle","id":"P","c1":"w1","c2":"w2","pick":0}
tangent_point: {"type":"tangent_point","id":"T","from":"P","to":"w"}

Стили линий:
  accent — ярко-синий, главное
  soft — серо-голубой, вспомогательное
  (по умолчанию) — светло-голубой

Правила:
1. Каждое имя объявляется один раз, ссылаться можно только на объявленное ранее.
2. Обозначения бери из условия. Не переименовывай. Вместо A' пиши A1.
3. Блок aux ОБЯЗАТЕЛЕН. Если в решении нет доп. построения —
   верни {"skip":"в решении нет дополнительного построения"}.
4. Не используй имена из одной цифры и имена с апострофом.
5. Не объявляй точки, которые совпадут по построению.
6. Чем меньше точек, тем лучше. Объявляй только важное.
7. Проверь свой ответ построчно: каждое имя из draw, draw_aux, marks
   обязано быть в given или aux.
"""

EXTRA = """
ВАЖНО:
- Блок aux обязателен. Это главное.
- Если в решении провели высоту, биссектрису, медиану, среднюю линию,
  симметрию, окружность, параллель, достроение — это твой aux.
- Если решение чисто вычислительное и нет никакого построения —
  верни {"skip":"в решении нет дополнительного построения"}.
- Не выдумывай построение, которого нет в решении.
"""


def collect_done(outdir):
    """возвращает uid задач, у которых есть _aux.svg"""
    has_aux = set()
    has_base = set()
    for p in outdir.glob("*.svg"):
        name = p.stem
        if name.endswith("_aux"):
            has_aux.add(name[:-4])
        else:
            has_base.add(name)
    return has_base, has_aux


def attempt(task, outdir, notes, seeds):
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
    # нужен aux
    if not (isinstance(spec.get("aux"), list) and spec["aux"]):
        return "fail", "нет блока aux", 0
    svg, tries, errs = ff.draw(spec, 1, seeds)
    if svg is None:
        return "fail", "; ".join(errs)[:300], 0
    # базовый
    (outdir / f"{uid}.svg").write_text(svg, encoding="utf-8")
    (outdir / f"{uid}.json").write_text(
        json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
    # с доп. построением
    merged = dict(spec)
    merged["given"] = spec["given"] + spec["aux"]
    merged["draw"] = spec["draw"] + spec.get("draw_aux", [])
    s2, _, e2 = ff.draw(merged, 1, seeds)
    if s2:
        (outdir / f"{uid}_aux.svg").write_text(s2, encoding="utf-8")
        return "ok", f"семян: {tries}", tries
    return "fail", f"aux не построился: {e2}"[:200], 0


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
            print(f"  [ok] {uid[:8]} — доп. построение найдено, {note}", flush=True)
            return True
        if st == "skip":
            with ff.lock:
                ff.stat["skip"] += 1
            ff.write_log(logf, uid, "skip", i + 1, note, time.time() - t0)
            print(f"  [skip] {uid[:8]} — {note}", flush=True)
            return True
        notes = note
    print(f"  --- {uid[:8]} {tag} не сдался: {notes[:70]}", flush=True)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--out", default="out")
    ap.add_argument("--seeds", type=int, default=200)
    ap.add_argument("--tries", type=int, default=3)
    a = ap.parse_args()

    if not ff.API_KEY:
        print("нет ключа: задай DEEPSEEK_API_KEY")
        sys.exit(1)

    outdir = pathlib.Path(a.out) / "figures"
    outdir.mkdir(parents=True, exist_ok=True)
    journal = pathlib.Path(a.out) / "figures_batch.jsonl"

    has_base, has_aux = collect_done(outdir)
    todo_uids = has_base - has_aux  # есть базовый, но нет aux

    data = json.loads(pathlib.Path(a.tasks).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("tasks") or data.get("items") or []
    tasks = [t for t in data if t.get("task_uid") in todo_uids]

    print(f"к регенерации: {len(tasks)} | потоков: {a.workers}")
    print(f"(у {len(has_aux)} задач aux уже есть, {len(has_base)} всего с базовым)")

    ff.CONTRACT = CONTRACT_AUX + EXTRA
    t0 = time.time()
    left = []
    if tasks:
        with open(journal, "a", encoding="utf-8") as logf:
            with ThreadPoolExecutor(max_workers=a.workers) as ex:
                futs = {ex.submit(worker, t, outdir, logf, a.tries, a.seeds,
                                   "регенерация"): t for t in tasks}
                for f, t in futs.items():
                    try:
                        ok = f.result()
                    except Exception as e:
                        print(f"  !!! сбой потока: {e}", flush=True)
                        ok = False
                    if not ok:
                        left.append(t)

    cost = ff.stat["in"] / 1e6 * 0.14 + ff.stat["out"] / 1e6 * 0.28
    print(f"\nитого: готово {ff.stat['ok']}, пропущено {ff.stat['skip']}, "
          f"не вышло {len(left)}")
    print(f"токенов вход {ff.stat['in']}, выход {ff.stat['out']}")
    print(f"стоимость: ${cost:.3f} | время: {(time.time()-t0)/60:.1f} мин")
    if left:
        print("\nнепостроенные:")
        for t in left:
            print("   ", t["task_uid"][:12], t["text"][:80].replace("\n", " "))

    # собрать всё в одну папку
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
