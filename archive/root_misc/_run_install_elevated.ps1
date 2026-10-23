$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Not admin: requesting elevation via UAC..."
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","`"$PSCommandPath`"" `
        -Verb RunAs -Wait
    exit $LASTEXITCODE
}

$env:NODE_NO_WARNINGS = "1"
$env:NODE_OPTIONS = "--no-deprecation"
$PSNativeCommandUseErrorActionPreference = $false

$Log = "C:\ProgramData\H2\install_log_v1r2.txt"
New-Item -ItemType Directory -Force -Path "C:\ProgramData\H2" | Out-Null
Start-Transcript -Path $Log -Force

try {
    $Root = "C:\H2\victor_bridge_release"
    $SrcZip = "C:\Users\Redmi\_bundle_v1r2.zip"
    $Zip = "$Root\VICTOR_BRIDGE_WHEELHOUSE_v1_r2.zip"
    $Extract = "$Root\payload"

    New-Item -ItemType Directory -Path $Root -Force | Out-Null
    Copy-Item -LiteralPath $SrcZip -Destination $Zip -Force

    if ((Get-Item -LiteralPath $Zip).Length -ne 10766068) {
        Write-Host "BLOCK_BUNDLE_SIZE_MISMATCH"; Stop-Transcript; exit 1
    }
    $Sha = (Get-FileHash -LiteralPath $Zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Sha -ne "f54f025db2ec1548629a589bbe9d1dd56f70e48dde0227205e74149f19791419") {
        Write-Host "BLOCK_BUNDLE_SHA256_MISMATCH actual=$Sha"; Stop-Transcript; exit 1
    }
    Write-Host "PASS_BUNDLE_SIZE_SHA"

    if (Test-Path -LiteralPath $Extract) {
        Remove-Item -LiteralPath $Extract -Recurse -Force
    }
    Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force
    $Bundle = "$Extract\VICTOR_BRIDGE_WHEELHOUSE_v1_r2"

    # Local compat fix: wrap Get-BridgeProcesses calls in @() so
    # $null result (no bridge process yet) doesn't break .Count under StrictMode.
    $installScript = "$Bundle\scripts\install_victor_bridge.ps1"
    $c = Get-Content -LiteralPath $installScript -Raw
    $c = $c.Replace('$existing = Get-BridgeProcesses', '$existing = @(Get-BridgeProcesses)')
    $c = $c.Replace('$after = Get-BridgeProcesses', '$after = @(Get-BridgeProcesses)')
    $c = $c.Replace('(Get-BridgeProcesses).Count -gt 0', '@(Get-BridgeProcesses).Count -gt 0')
    $c = $c.Replace('(Get-BridgeProcesses).Count -eq 0', '@(Get-BridgeProcesses).Count -eq 0')
    [IO.File]::WriteAllText($installScript, $c, (New-Object Text.UTF8Encoding($false)))
    Write-Host "LOCAL_COMPAT_FIX_APPLIED"

    Set-ExecutionPolicy -Scope Process Bypass -Force
    Write-Host "==== INSTALL SCRIPT ===="
    & "$Bundle\scripts\install_victor_bridge.ps1"
    $rc1 = $LASTEXITCODE
    Write-Host "INSTALL_EXIT=$rc1"
    if ($rc1 -ne 0) {
        Write-Host "BLOCK_INSTALL_SCRIPT_FAILED"; Stop-Transcript; exit 2
    }
    Write-Host "==== VERIFY SCRIPT ===="
    & "$Bundle\scripts\verify_victor_bridge.ps1"
    $rc2 = $LASTEXITCODE
    Write-Host "VERIFY_EXIT=$rc2"
    if ($rc2 -ne 0) {
        Write-Host "BLOCK_LOCAL_VERIFY_FAILED"; Stop-Transcript; exit 3
    }

    Write-Host "VERDICT=INSTALL_APPLIED_PENDING_LIVE_E2E"
    Stop-Transcript
    exit 0
} catch {
    Write-Host "FATAL_EXCEPTION=$($_.Exception.Message)"
    Stop-Transcript
    exit 99
}
