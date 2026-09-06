$ErrorActionPreference = "Stop"
$p = 'C:\H2\victor_bridge_release\payload\VICTOR_BRIDGE_WHEELHOUSE_v1_r2\scripts\install_victor_bridge.ps1'
$c = Get-Content -LiteralPath $p -Raw

# Fix 1: $existing = Get-BridgeProcesses -> wrap in @()
$c = $c.Replace('$existing = Get-BridgeProcesses', '$existing = @(Get-BridgeProcesses)')
# Fix 2: $after = Get-BridgeProcesses -> wrap
$c = $c.Replace('$after = Get-BridgeProcesses', '$after = @(Get-BridgeProcesses)')
# Fix 3: (Get-BridgeProcesses).Count -gt 0 -> @(...).Count
$c = $c.Replace('(Get-BridgeProcesses).Count -gt 0', '@(Get-BridgeProcesses).Count -gt 0')
# Fix 4: (Get-BridgeProcesses).Count -eq 0 -> @(...).Count
$c = $c.Replace('(Get-BridgeProcesses).Count -eq 0', '@(Get-BridgeProcesses).Count -eq 0')

[IO.File]::WriteAllText($p, $c, (New-Object Text.UTF8Encoding($false)))
Write-Output 'install script patched for @() array wrapping.'
