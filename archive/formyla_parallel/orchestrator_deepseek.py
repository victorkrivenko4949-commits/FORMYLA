
import argparse, json, os, subprocess, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_worker(worker_id, queue_dir, out_dir, model, limit):
    cmd=[sys.executable, str(Path(__file__).with_name('deepseek_worker.py')), '--worker', str(worker_id), '--queue', queue_dir, '--out', out_dir, '--model', model]
    if limit:
        cmd += ['--limit', str(limit)]
    p=subprocess.run(cmd, capture_output=True, text=True)
    return {'worker':worker_id,'returncode':p.returncode,'stdout':p.stdout[-3000:],'stderr':p.stderr[-3000:]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=20)
    ap.add_argument('--queue-dir', default='output')
    ap.add_argument('--out-dir', default='output/formyla_parallel/results')
    ap.add_argument('--model', default=os.getenv('DEEPSEEK_MODEL','deepseek-chat'))
    ap.add_argument('--limit-per-worker', type=int, default=0)
    args=ap.parse_args()
    if not os.getenv('DEEPSEEK_API_KEY'):
        raise SystemExit('Set DEEPSEEK_API_KEY env var first.')
    Path(args.out_dir).mkdir(parents=True, exist_ok=True)
    results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs=[ex.submit(run_worker,w,args.queue_dir,args.out_dir,args.model,args.limit_per_worker) for w in range(1,args.workers+1)]
        for fut in as_completed(futs):
            r=fut.result(); results.append(r); print(json.dumps(r,ensure_ascii=False), flush=True)
    Path(args.out_dir,'deepseek_orchestrator_report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__ == '__main__':
    main()
