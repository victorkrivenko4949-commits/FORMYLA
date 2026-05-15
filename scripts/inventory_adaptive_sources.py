import glob, json, os
from collections import Counter
K={"class_level","difficulty_level","task_text","topic","solution"}
def ok(r): return isinstance(r,dict) and bool(K & r.keys())
def it(p):
    try:
        if p.lower().endswith(".jsonl"):
            for l in open(p,encoding="utf-8"):
                l=l.strip()
                if l:
                    try: yield json.loads(l)
                    except: pass
            return
        d=json.load(open(p,encoding="utf-8"))
        if isinstance(d,list):
            for x in d: yield x
        elif isinstance(d,dict):
            for k in ("tasks","problems","items","data","records","results"):
                v=d.get(k)
                if isinstance(v,list):
                    for x in v: yield x
                    return
    except Exception as e:
        print("[skip]",p,"->",e)
def main():
    pats=["adaptive_data/**/*.json","adaptive_data/**/*.jsonl",
          "_TRASH_2026/**/*.json","_TRASH_2026/**/*.jsonl"]
    files=sorted({f for pat in pats for f in glob.glob(pat,recursive=True)})
    skip=("venv","site-packages","__pycache__","_TRASH_20260429")
    files=[f for f in files if not any(s in f for s in skip)]
    print("files:",len(files))
    per=[]; merged={}; raw=0
    for f in files:
        n=0
        for r in it(f):
            if not ok(r): continue
            n+=1; raw+=1
            t=(r.get("task_text") or "").strip()
            if not t: continue
            if t not in merged: merged[t]=r
        if n: per.append((n,f))
    per.sort(reverse=True)
    print("\n== TOP 30 files by adaptive records ==")
    for n,f in per[:30]: print(f"{n:6d}  {f}")
    print(f"\nRAW total: {raw}")
    print(f"UNIQUE by task_text: {len(merged)}")
    cl=Counter(int(r.get("class_level") or 0) for r in merged.values())
    print("\nUnique by class_level:")
    for k in sorted(cl): print(f"  class {k}: {cl[k]}")
    ct=Counter((int(r.get("class_level") or 0), (r.get("topic") or "")[:60]) for r in merged.values())
    print("\nUnique by (class, topic) — top 40:")
    for (c,t),n in ct.most_common(40): print(f"  {n:5d}  c{c}  {t}")
    print("\nLowest filled (class, topic) — bottom 30:")
    for (c,t),n in sorted(ct.items(), key=lambda x:x[1])[:30]: print(f"  {n:5d}  c{c}  {t}")
    out="adaptive_data/_merged_inventory.json"
    json.dump(list(merged.values()), open(out,"w",encoding="utf-8"), ensure_ascii=False)
    print(f"\nWrote merged: {out}  ({len(merged)} records)")
    rep="adaptive_data/_inventory_report.txt"
    with open(rep,"w",encoding="utf-8") as fp:
        fp.write(f"RAW total records: {raw}\n")
        fp.write(f"UNIQUE by task_text: {len(merged)}\n\n")
        fp.write("== Unique by class_level ==\n")
        for k in sorted(cl): fp.write(f"  class {k}: {cl[k]}\n")
        fp.write("\n== Unique by (class, topic), sorted by class then count desc ==\n")
        by_class={}
        for (c,t),n in ct.items(): by_class.setdefault(c,[]).append((n,t))
        for c in sorted(by_class):
            fp.write(f"\n--- class {c} (total {cl[c]}) ---\n")
            for n,t in sorted(by_class[c], reverse=True):
                fp.write(f"  {n:5d}  {t}\n")
        fp.write("\n== TOP 30 source files ==\n")
        for n,f in per[:30]: fp.write(f"  {n:6d}  {f}\n")
    print(f"Wrote report: {rep}")
if __name__=="__main__": main()
