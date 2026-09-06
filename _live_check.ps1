$ErrorActionPreference = "Stop"
$Call = "C:\H2\victor_bridge_release\payload\VICTOR_BRIDGE_WHEELHOUSE_v1_r2\scripts\invoke_owui_function.ps1"
$Evidence = "C:\ProgramData\H2\evidence"
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null

$ops = @(
    @{ name = "route_attest";   json = '{"operation":"route_attest","node":"victor"}' },
    @{ name = "health";         json = '{"operation":"health","node":"victor"}' },
    @{ name = "list_instances"; json = '{"operation":"list_instances","node":"victor"}' }
)

foreach ($op in $ops) {
    Write-Host "=== $($op.name) ==="
    $outFile = Join-Path $Evidence ("{0}.json" -f $op.name)
    try {
        $r = & $Call -PayloadJson $op.json -OutFile $outFile 2>&1
        Write-Host $r
    } catch {
        Write-Host ("ERROR: " + $_.Exception.Message)
    }
}
