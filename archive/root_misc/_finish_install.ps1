$ErrorActionPreference = "Stop"

# Self-elevate
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","`"$PSCommandPath`"" `
        -Verb RunAs -Wait
    exit 0
}

$env:NODE_NO_WARNINGS = "1"
$PSNativeCommandUseErrorActionPreference = $false

$Log = "C:\ProgramData\H2\install_log_finish.txt"
New-Item -ItemType Directory -Force -Path "C:\ProgramData\H2" | Out-Null
Start-Transcript -Path $Log -Force

function Get-BridgeProcesses {
    $items = @()
    try {
        $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue
        foreach ($p in $procs) {
            if ($p.CommandLine -and $p.CommandLine -match 'owui_roo_bridge|bridge_compat_runner[.]py') {
                $items += $p
            }
        }
    } catch {}
    return ,$items
}

$BundleRoot = "C:\H2\victor_bridge_release\payload\VICTOR_BRIDGE_WHEELHOUSE_v1_r2"
$PythonExe = "C:\ProgramData\H2\bridge_venv\Scripts\python.exe"
$ConfigDir = "C:\ProgramData\H2\config"
$StateDir = "C:\ProgramData\H2\state"
$LogDir = "C:\ProgramData\H2\logs"
$ScriptDir = "C:\ProgramData\H2\scripts"
$NodePath = Join-Path $ConfigDir "node.json"
$InstalledRunner = Join-Path $ScriptDir "run_victor_bridge.ps1"
$TaskName = "H2_VICTOR_BRIDGE"
$NodeId = "victor"
$ExpectedHostname = "DESKTOP-OLJ4LRK"
$NatsUrl = "nats://192.168.99.11:4222"
$OwnershipBucket = "owui_roo_bridge_victor_ownership"
$RooStorage = "C:\Users\Redmi\AppData\Roaming\Code\User\globalStorage\rooveterinaryinc.roo-cline"
$RooTasks = "$RooStorage\tasks"
$InstancesRegistry = "C:\Users\Redmi\.roo-bridge\instances.json"

foreach ($dir in @($ConfigDir, $StateDir, $LogDir, $ScriptDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

# 1. DeepSeek credential (metadata-only check)
$CredentialCheck = @'
import keyring
import os
value = keyring.get_password("H2_DEEPSEEK_API_KEY", "default")
if not value:
    value = (os.environ.get("H2_DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if value:
        keyring.set_password("H2_DEEPSEEK_API_KEY", "default", value)
print("DEEPSEEK_CREDENTIAL=" + ("PRESENT" if keyring.get_password("H2_DEEPSEEK_API_KEY", "default") else "OPTIONAL_ABSENT_STRICT_JSON_ONLY"))
'@
$CredentialCheck | & $PythonExe -

# 2. node.json (BOM-free)
$Node = [ordered]@{
    schema_version = 1
    node_id = $NodeId
    hostname = $ExpectedHostname
    wheel_version = "0.5.10"
    workspaces_root = "C:/H2"
    log_dir = "C:/ProgramData/H2/logs"
    workspaces = @("C:/H2/victor_bridge_canary")
    roo = [ordered]@{
        tasks_root = $RooTasks.Replace('\','/')
        instances_registry = $InstancesRegistry.Replace('\','/')
        storage_root = $RooStorage.Replace('\','/')
    }
    nats = [ordered]@{
        url = $NatsUrl
        ownership_kv = $OwnershipBucket
    }
}
$Json = $Node | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText($NodePath, $Json, (New-Object Text.UTF8Encoding($false)))
Get-Content -LiteralPath $NodePath -Raw | ConvertFrom-Json | Out-Null
Write-Host "PASS_NODE_JSON"

# 3. Copy runner + compat runner
Copy-Item -LiteralPath (Join-Path $BundleRoot "scripts\run_victor_bridge.ps1") -Destination $InstalledRunner -Force
Copy-Item -LiteralPath (Join-Path $BundleRoot "scripts\bridge_compat_runner.py") -Destination (Join-Path $ScriptDir "bridge_compat_runner.py") -Force

# 4. Provision ownership KV
$env:NATS_URL = $NatsUrl
& $PythonExe (Join-Path $BundleRoot "scripts\provision_ownership_kv.py") --url $NatsUrl --bucket $OwnershipBucket --ttl-seconds 60
if ($LASTEXITCODE -ne 0) {
    Write-Host "BLOCK_OWNERSHIP_KV_NOT_PROVISIONED"
    Stop-Transcript; exit 1
}
Write-Host "PASS_OWNERSHIP_KV"

# 5. Scheduled task (idempotent)
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$taskAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$InstalledRunner`"" `
    -WorkingDirectory $ConfigDir
$taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$taskPrincipal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest
$taskSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

if ($existingTask) {
    Write-Host "TASK=KEEP"
} else {
    Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $taskTrigger -Principal $taskPrincipal -Settings $taskSettings -Description "H2 OWUI-Roo Bridge for node victor" | Out-Null
    Write-Host "TASK=APPLIED"
}

# 6. Start bridge if not running
$before = @(Get-BridgeProcesses)
if ($before.Count -eq 0) {
    Start-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 12
}
$after = @(Get-BridgeProcesses)
if ($after.Count -ne 1) {
    Write-Host "BLOCK_BRIDGE_PROCESS_CARDINALITY expected=1 actual=$($after.Count)"
    Stop-Transcript; exit 2
}
$taskState = (Get-ScheduledTask -TaskName $TaskName).State
Write-Host "PASS_BRIDGE_PROCESS_CARDINALITY=1"
Write-Host "TASK_STATE=$taskState"
Write-Host "VERDICT=INSTALL_APPLIED_PENDING_LIVE_E2E"
Stop-Transcript
exit 0
