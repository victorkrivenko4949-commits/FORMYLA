$ErrorActionPreference = "Continue"

Set-Location "C:\Users\Victor\Desktop\Новая папка (2)\formyla_parallel_complete"

$env:PYTHONUTF8="1"
$env:PYTHONIOENCODING="utf-8"

powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
powercfg /change monitor-timeout-ac 0

New-Item -ItemType Directory -Force .\logs | Out-Null
New-Item -ItemType Directory -Force .\interrupted_backup | Out-Null

$masterStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = ".\logs\auto_7h_master_$masterStamp.log"
$end = (Get-Date).AddHours(7)
$workersList = @(8,6,4,3)
$workerIndex = 0
$round = 0

function Move-LatestPartial {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $latest = Get-ChildItem .\auto_run -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "results_retry_*" -or $_.Name -like "results_audit_fix_*" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($latest) {
        $suffix = $latest.Name -replace "^results_",""
        foreach ($name in @("queue_$suffix","results_$suffix")) {
            $p = ".\auto_run\$name"
            if (Test-Path $p) {
                Move-Item $p ".\interrupted_backup\${name}_partial_$stamp" -ErrorAction SilentlyContinue
                "MOVED_PARTIAL $name" | Tee-Object -FilePath $log -Append
            }
        }
    }
}

"START_7H $(Get-Date)" | Tee-Object -FilePath $log -Append

while ((Get-Date) -lt $end) {
    $round++
    $workers = $workersList[$workerIndex]

    "===== ROUND=$round WORKERS=$workers TIME=$(Get-Date) =====" | Tee-Object -FilePath $log -Append

    python .\make_safe_auto.py $workers 2>&1 | Tee-Object -FilePath $log -Append

    $out = python .\auto_formyla_until_clean_safe.py 2>&1 | Tee-Object -FilePath $log -Append
    $code = $LASTEXITCODE

    "EXIT_CODE=$code TIME=$(Get-Date)" | Tee-Object -FilePath $log -Append

    if (($out -match "AUTO_STATUS=CLEAN") -or ($out -match "VALIDATOR_BAD=0")) {
        "DONE_CLEAN $(Get-Date)" | Tee-Object -FilePath $log -Append
        break
    }

    if (($code -ne 0) -or ($out -match "WinError 1455") -or ($out -match "COMMAND FAILED")) {
        "CRASH_OR_FAIL_DETECTED" | Tee-Object -FilePath $log -Append
        Move-LatestPartial

        if ($workerIndex -lt ($workersList.Count - 1)) {
            $workerIndex++
            "LOWER_WORKERS_TO=$($workersList[$workerIndex])" | Tee-Object -FilePath $log -Append
        }

        Start-Sleep -Seconds 90
        continue
    }

    Start-Sleep -Seconds 120
}

"TIME_LIMIT_OR_DONE $(Get-Date)" | Tee-Object -FilePath $log -Append

python -c "import glob,json,os; dirs=sorted(glob.glob('auto_run/results*')); print('RESULT_DIRS',len(dirs)); [print(d,'files',len(glob.glob(os.path.join(d,'worker_*_results.jsonl')))) for d in dirs[-10:]]" 2>&1 | Tee-Object -FilePath $log -Append

"LOG=$log" | Tee-Object -FilePath $log -Append
