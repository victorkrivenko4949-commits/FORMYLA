# Restarts the python script until all objects are processed.
# Relies on the script's own checkpoint: each run resumes where it stopped.
#
# RUN:
#   powershell -ExecutionPolicy Bypass -File .\run_until_done.ps1
#
# Stop manually with Ctrl+C
# ASCII only on purpose: Windows PowerShell 5.1 reads .ps1 as ANSI without BOM.

$ErrorActionPreference = "Continue"

$WorkDir    = "C:\Users\Redmi\Desktop\" + [char]0x041D + [char]0x043E + [char]0x0432 + [char]0x0430 + [char]0x044F + " " + [char]0x043F + [char]0x0430 + [char]0x043F + [char]0x043A + [char]0x0430 + " (2)"
$Script     = "fix_latex_deepseek.py"
$OutFile    = "6767_latex_fixed"
$Target     = 69
$MaxRuns    = 100
$StallLimit = 4
$PauseSec   = 5
$LogFile    = "latex_run.log"

Set-Location $WorkDir

function Get-Done {
    $candidates = @($OutFile, "$OutFile.jsonl", "$OutFile.json", "$OutFile.txt")
    foreach ($f in $candidates) {
        if (Test-Path $f) {
            $n = (Get-Content $f -Encoding UTF8 | Where-Object { $_.Trim() -ne "" }).Count
            return @{ file = $f; count = $n }
        }
    }
    return @{ file = "none"; count = 0 }
}

$run = 0
$stall = 0
$prev = (Get-Done).count

Write-Host "Start. Already done: $prev of $Target" -ForegroundColor Cyan
Add-Content $LogFile "`n===== SESSION $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====="

while ($run -lt $MaxRuns) {
    $run++
    $stamp = Get-Date -Format "HH:mm:ss"
    Write-Host "[$stamp] Run #$run ..." -ForegroundColor Yellow

    Add-Content $LogFile "`n--- run #$run at $stamp ---"
    & python -u $Script *>> $LogFile
    $code = $LASTEXITCODE

    $state = Get-Done
    $now = $state.count
    $gain = $now - $prev

    Write-Host ("  exit={0}  done={1}/{2}  gain={3}" -f $code, $now, $Target, $gain)
    Add-Content $LogFile "--- exit $code | done $now/$Target | gain $gain ---"

    if ($now -ge $Target) {
        Write-Host "" 
        Write-Host "COMPLETE: $now of $Target after $run runs." -ForegroundColor Green
        break
    }

    if ($gain -le 0) {
        $stall++
        Write-Host "  no progress ($stall of $StallLimit)" -ForegroundColor Red
        if ($stall -ge $StallLimit) {
            Write-Host ""
            Write-Host "STOPPED: $StallLimit runs in a row with no progress." -ForegroundColor Red
            Write-Host "Log tail:" -ForegroundColor Red
            Get-Content $LogFile -Tail 25 -Encoding UTF8
            break
        }
        Start-Sleep ($PauseSec * $stall)
    } else {
        $stall = 0
        Start-Sleep $PauseSec
    }

    $prev = $now
}

if ($run -ge $MaxRuns) {
    Write-Host "Reached the limit of $MaxRuns runs." -ForegroundColor Red
}

$final = Get-Done
Write-Host ""
Write-Host "Result: $($final.count) of $Target in file $($final.file)"
Write-Host "Full log: $LogFile"
