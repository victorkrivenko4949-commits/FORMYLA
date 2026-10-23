$ErrorActionPreference = "Continue"
Set-Location "C:\Users\Victor\Desktop\Новая папка (2)\formyla_parallel_complete"

$end = (Get-Date).AddHours(7)
$round = 0
$log = ".\logs\AUTO_7H_$((Get-Date).ToString('yyyyMMdd_HHmmss')).log"

"START $(Get-Date)" | Tee-Object -FilePath $log -Append

while ((Get-Date) -lt $end) {
    $round++
    "===== ROUND $round $(Get-Date) =====" | Tee-Object -FilePath $log -Append

    $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like "*auto_formyla_until_clean.py*" -or
        $_.CommandLine -like "*auto_formyla_until_clean_7h.py*" -or
        $_.CommandLine -like "*orchestrator_deepseek.py*" -or
        $_.CommandLine -like "*deepseek_worker.py*"
    }

    if ($procs) {
        "FOUND RUNNING PROCESS, WAIT 300 SEC" | Tee-Object -FilePath $log -Append
        $procs | Select-Object ProcessId, CommandLine | Out-String | Tee-Object -FilePath $log -Append
        Start-Sleep -Seconds 300
        continue
    }

    python .\auto_formyla_until_clean_7h.py 2>&1 | Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE
    "EXIT_CODE=$code $(Get-Date)" | Tee-Object -FilePath $log -Append

    python - <<'PY' 2>&1 | Tee-Object -FilePath $log -Append
import glob, json, os
dirs = sorted(glob.glob("auto_run/results*"))
print("RESULT_DIRS", len(dirs))
for d in dirs[-8:]:
    files = glob.glob(os.path.join(d, "worker_*_results.jsonl"))
    lines = failed = 0
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as x:
            for line in x:
                if not line.strip():
                    continue
                lines += 1
                try:
                    if json.loads(line).get("status") != "ok":
                        failed += 1
                except Exception:
                    failed += 1
    print(d, "files", len(files), "lines", lines, "failed", failed)
PY

    Start-Sleep -Seconds 120
}

"TIME LIMIT DONE $(Get-Date)" | Tee-Object -FilePath $log -Append

$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*orchestrator_deepseek.py*" -or
    $_.CommandLine -like "*deepseek_worker.py*"
}
if ($procs) {
    "LEAVE WORKERS RUNNING, NOT KILLING" | Tee-Object -FilePath $log -Append
    $procs | Select-Object ProcessId, CommandLine | Out-String | Tee-Object -FilePath $log -Append
}

"LOG=$log" | Tee-Object -FilePath $log -Append
