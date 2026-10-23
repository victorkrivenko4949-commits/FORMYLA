# -*- coding: utf-8 -*-
import io, sys, json, csv, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

recs = {}
for line in open("output/ch19/pilot_100.jsonl", encoding="utf-8"):
    d = json.loads(line)
    recs[d["task_uid"]] = d

rows = list(csv.DictReader(open("output/ch22/results.csv", encoding="utf-8")))
done = [r for r in rows if r["status"] == "done"]
done.sort(key=lambda r: len(recs.get(r["task_uid"], {}).get("solution", "") or ""), reverse=True)

top = done[:5]
for r in top:
    uid = r["task_uid"]
    d = recs.get(uid, {})
    print(uid, "| sol_len", len(d.get("solution", "") or ""),
          "| aux", r["has_aux"], "| grade", d.get("grade"))
    # копируем svg в manual_review/top5
    os.makedirs("output/ch22/manual_review/top5", exist_ok=True)
    for suf in ("_base.svg", "_aux.svg"):
        src = os.path.join("output/ch22/svg", uid + suf)
        if os.path.exists(src):
            import shutil
            shutil.copy(src, os.path.join("output/ch22/manual_review/top5", uid + suf))
