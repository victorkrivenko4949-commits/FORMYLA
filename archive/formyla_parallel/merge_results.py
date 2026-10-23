
import argparse, json
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--results-dir', required=True)
    ap.add_argument('--out', required=True)
    args=ap.parse_args()
    base=json.loads(Path(args.base).read_text(encoding='utf-8'))
    byid={t['id']:t for t in base}
    additions=[]; replacements=0
    for p in Path(args.results_dir).glob('worker_*_results.jsonl'):
        for line in p.read_text(encoding='utf-8').splitlines():
            rec=json.loads(line)
            t=rec.get('task')
            if not t: continue
            if t['id'] in byid: byid[t['id']]=t; replacements+=1
            else: additions.append(t)
    final=list(byid.values())+additions
    Path(args.out).write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'base':len(base),'final':len(final),'replacements':replacements,'additions':len(additions)},ensure_ascii=False))
if __name__=='__main__': main()
