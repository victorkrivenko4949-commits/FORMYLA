import json, os, sys
from collections import Counter
p = sys.argv[1] if len(sys.argv)>1 else r"C:\Users\Victor\Downloads\formyla_master_5345_fixed_after_manual_audit (1).json"
print("FILE:", p, "exists=", os.path.exists(p))
with open(p, "r", encoding="utf-8") as f:
    data = json.load(f)
print("TYPE:", type(data).__name__)
items = data if isinstance(data, list) else data.get("items") or data.get("tasks") or data.get("problems") or []
print("LEN:", len(items))
if items:
    first = items[0]
    print("FIRST KEYS:", sorted(first.keys()) if isinstance(first, dict) else first)
    print("FIRST SAMPLE:")
    print(json.dumps{