#!/usr/bin/env python3
"""Compact validator for all gen_678 tasks."""
import json, os, re, sys
from datetime import datetime
from collections import defaultdict, Counter

GEN = os.path.join(os.path.dirname(__file__), "gen_678")
DIRS = ["L6", "L7", "L8", "reserve", "blacklist"]
REQ = {"id":(int,),"task_text":(str,),"solution":(str,),"correct_answer":(str,),
       "class_level":(int,),"topic":(str,),"difficulty_level":(int,),"real_level":(int,),
       "key_method":(str,),"idea_count":(int,),"is_clone":(bool,),"lang_ok":(bool,),
       "_status":(str,),"fix_rounds":(int,),"quality_score":(int,float),
       "source":(str,),"was_improved":(bool,),"generated_at":(str,)}
VALID_ST = {"active","clone_exhausted","blacklisted"}
VALID_TP = {"Алгебра","Геометрия","Теория чисел","Комбинаторика","Логика","Неравенства"}

def validate(fp, subdir):
    r = {"f":os.path.basename(fp),"sd":subdir,"ok":True,"err":[],"warn":[],"id":None,"lvl":None,"st":None}
    try:
        with open(fp,"r",encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        return {**r,"ok":False,"err":[f"JSON: {e}"]}
    r["id"] = d.get("id"); r["lvl"] = d.get("difficulty_level"); r["st"] = d.get("_status")
    for fld, types in REQ.items():
        if fld not in d: r["err"].append(f"missing {fld}"); r["ok"]=False
        elif d[fld] is None: r["err"].append(f"{fld}=None"); r["ok"]=False
        elif not isinstance(d[fld], types): r["err"].append(f"{fld} type {type(d[fld]).__name__}"); r["ok"]=False
    if not r["ok"]: return r
    if d["id"]<=0: r["err"].append(f"bad id {d['id']}")
    if d["class_level"] not in range(5,12): r["err"].append(f"class_level {d['class_level']}")
    for lf in ("difficulty_level","real_level"):
        if d[lf] not in (6,7,8): r["err"].append(f"{lf} {d[lf]}")
    if d["difficulty_level"]!=d["real_level"]: r["warn"].append(f"lvl mismatch {d['difficulty_level']}!={d['real_level']}")
    if getattr(validate,"lvl_dir",{}).get(subdir) and d["difficulty_level"]!=validate.lvl_dir[subdir]:
        r["warn"].append(f"dir {subdir}!={d['difficulty_level']}")
    if d["_status"] not in VALID_ST: r["err"].append(f"status {d['_status']}")
    if d["source"]!="gen_678": r["warn"].append(f"source {d['source']}")
    if d["idea_count"]<1: r["warn"].append(f"idea_count {d['idea_count']}")
    if not (0<=d["quality_score"]<=1): r["err"].append(f"qs {d['quality_score']}")
    if d["fix_rounds"]<0: r["err"].append(f"fix_rounds {d['fix_rounds']}")
    try: datetime.fromisoformat(d["generated_at"])
    except: r["warn"].append(f"bad date {d.get('generated_at','')}")
    t = d.get("topic","")
    if not t: r["warn"].append("no topic")
    elif t not in VALID_TP: r["warn"].append(f"topic '{t}'")
    if len(d.get("task_text",""))<30: r["warn"].append(f"short text {len(d['task_text'])}")
    if len(d.get("solution",""))<50: r["warn"].append(f"short sol {len(d['solution'])}")
    if re.search(r'TODO|PLACEHOLDER|FIXME', d.get("task_text",""), re.I): r["warn"].append("placeholder in text")
    if d.get("is_clone") and "clone_similarity" not in d: r["warn"].append("clone no similarity")
    if d.get("is_clone") and d.get("_status")=="active": r["warn"].append("clone active")
    return r

validate.lvl_dir = {"L6":6,"L7":7,"L8":8}

def main():
    print("="*70)
    print("  gen_678 VALIDATION REPORT")
    print(f"  {datetime.now().isoformat()}")
    print("="*70)
    total=0; errors=[]; warnings=[]; stats=Counter(); topics=Counter(); levels=Counter()
    for sd in DIRS:
        p=os.path.join(GEN,sd)
        if not os.path.isdir(p): continue
        files=sorted(f for f in os.listdir(p) if f.endswith(".json"))
        print(f"\n  [{sd}] {len(files)} files")
        for fn in files:
            total+=1
            r=validate(os.path.join(p,fn),sd)
            if not r["ok"]:
                errors.append(r)
                print(f"    ERR {r['f']}: {'; '.join(r['err'][:3])}")
            else:
                if r["warn"]: warnings.append(r)
                stats[r["st"]]+=1
                topics[r.get("topic","?")]+=1
                levels[r["lvl"]]+=1
    print("\n"+"="*70)
    print("  SUMMARY")
    print("="*70)
    print(f"  Total files scanned: {total}")
    print(f"  Errors (structural): {len(errors)}")
    print(f"  Warnings (quality): {len(warnings)}")
    print(f"  Statuses: {dict(stats)}")
    print(f"  Topics: {dict(topics)}")
    print(f"  Levels: {dict(levels)}")
    if errors:
        print(f"\n  --- ERRORS ({len(errors)}) ---")
        for e in errors[:10]:
            print(f"  [{e['sd']}] {e['f']}: {'; '.join(e['err'][:3])}")
        if len(errors)>10: print(f"  ... and {len(errors)-10} more")
    if warnings:
        print(f"\n  --- WARNINGS (sample, {len(warnings)} total) ---")
        for w in warnings[:5]:
            print(f"  [{w['sd']}] {w['f']}: {'; '.join(w['warn'][:3])}")
        if len(warnings)>5: print(f"  ... and {len(warnings)-5} more")
    print("\n"+"="*70)
    print("  DONE")
    print("="*70)

if __name__=="__main__":
    main()