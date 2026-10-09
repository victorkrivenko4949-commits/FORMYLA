import os, json, time

l1l3 = 'l1_l3_generation'
dirs = [d for d in os.listdir(l1l3) if d.startswith('max_fill_') and os.path.isdir(os.path.join(l1l3, d))]
dirs.sort()
print(f'Output dirs: {dirs}', flush=True)

if dirs:
    latest = os.path.join(l1l3, dirs[-1])
    files = os.listdir(latest)
    print(f'Latest dir: {dirs[-1]}')
    print(f'Files: {files}', flush=True)
    
    manifest_path = os.path.join(latest, 'l1_l3_run_manifest.json')
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding='utf-8') as f:
            m = json.load(f)
        print(f'Coverage: {m.get("coverage", {})}', flush=True)
        print(f'Cell counts: {m.get("cell_counts", {})}', flush=True)
        print(f'Cost: {m.get("api_stats", {}).get("total_cost_usd", 0)}', flush=True)
    
    report_path = os.path.join(latest, 'L1_L3_MAX_FILL_FINAL_REPORT.md')
    if os.path.exists(report_path):
        with open(report_path, encoding='utf-8') as f:
            print(f'\n--- Report Excerpt ---', flush=True)
            lines = f.readlines()
            print(''.join(lines[-20:]), flush=True)
