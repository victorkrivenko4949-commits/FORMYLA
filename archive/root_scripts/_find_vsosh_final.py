#!/usr/bin/env python3
"""Find vsosh 2020 regional in olympiads.py via AST."""
import ast, json

with open('olympiads.py','r',encoding='utf-8') as f:
    content = f.read()

tree = ast.parse(content)
for node in ast.iter_child_nodes(tree):
    if isinstance(node, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == 'OLYMPIADS_DB' for t in node.targets
    ):
        entries = node.value.elts
        print(f"Total: {len(entries)}", flush=True)
        vsosh = []
        for i, elt in enumerate(entries):
            if not isinstance(elt, ast.Dict):
                continue
            d = {}
            for k, v in zip(elt.keys, elt.values):
                if isinstance(k, ast.Constant):
                    d[k.value] = v
            o = d.get('olympiad')
            on = o.value if isinstance(o, ast.Constant) else ''
            if on != 'vsosh':
                continue
            yv = d.get('year', ast.Constant(value=0))
            yr = yv.value if isinstance(yv, ast.Constant) else 0
            rv = d.get('round', ast.Constant(value=''))
            rn = rv.value if isinstance(rv, ast.Constant) else ''
            gv = d.get('grade', ast.Constant(value=0))
            gr = gv.value if isinstance(gv, ast.Constant) else 0
            pv = d.get('problems', ast.List(elts=[]))
            pc = len(pv.elts) if isinstance(pv, ast.List) else 0
            pnums = []
            for p in (pv.elts if isinstance(pv, ast.List) else []):
                if isinstance(p, ast.Dict):
                    for pk, pv2 in zip(p.keys, p.values):
                        if isinstance(pk, ast.Constant) and pk.value == 'num' and isinstance(pv2, ast.Constant):
                            pnums.append(pv2.value)
            print(f"  [{i}] yr={yr} round={rn} grade={gr} probs={pc} nums={pnums}", flush=True)
            if yr == 2020 and rn == 'regional':
                vsosh.append((i, gr, pc, pnums))
        print(f"\nVsosh 2020 regional entries:")
        for idx, gr, pc, pnums in vsosh:
            print(f"  Index {idx}: grade={gr}, problems={pc}, nums={pnums}", flush=True)

        # Now extract full JSON for the vsosh 2020 regional entries
        print(f"\nExtracting full JSON...", flush=True)
        result_data = []
        for idx, gr, pc, pnums in vsosh:
            elt = entries[idx]
            d = {}
            for k, v in zip(elt.keys, elt.values):
                if isinstance(k, ast.Constant):
                    kname = k.value
                    if isinstance(v, ast.Constant):
                        d[kname] = v.value
                    elif isinstance(v, ast.List):
                        probs = []
                        for p in v.elts:
                            if isinstance(p, ast.Dict):
                                pd = {}
                                for pk, pv in zip(p.keys, p.values):
                                    if isinstance(pk, ast.Constant) and isinstance(pv, ast.Constant):
                                        pd[pk.value] = pv.value
                                probs.append(pd)
                        d[kname] = probs
                    else:
                        d[kname] = str(type(v).__name__)
            result_data.append(d)

        with open('_vsosh_2020_regional.json', 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
        print(f"Saved to _vsosh_2020_regional.json", flush=True)
        break
