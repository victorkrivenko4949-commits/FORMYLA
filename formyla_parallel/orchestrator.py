
import argparse, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

def run_worker(worker_id, queue_dir, out_dir, model):
    cmd=[sys.executable, str(Path(__file__).with_name('worker.py')), '--worker', str(worker_id), '--queue', queue_dir, '--out', out_dir, '--model', model]
    p=subprocess.run(cmd, capture_output=True, text=True)
    return {'worker':worker_id,'returncode':p.returncode,'stdout':p.stdout[-4000:],'stderr':p.stderr[-4000:]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=20)
    ap.add_argument('--queue-dir', default='output')
    ap.add_argument('--out-dir', default='output/formyla_parallel/results')
    ap.add_argument('--model', default=os.getenv('FORMYLA_MODEL','gpt-5.5-thinking'))
    args=ap.parse_args()
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs=[ex.submit(run_worker,w,args.queue_dir,args.out_dir,args.model) for w in range(1,args.workers+1)]
        for fut in as_completed(futs):
            r=fut.result(); results.append(r); print(json.dumps(r,ensure_ascii=False))
    Path(args.out_dir,'orchestrator_report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__': main()
