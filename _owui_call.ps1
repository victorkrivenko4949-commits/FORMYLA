[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$PayloadJson,
    [string]$OutFile = ""
)

$ErrorActionPreference = "Stop"
$key = [Environment]::GetEnvironmentVariable("H2_API_KEY", "Machine")
if ([string]::IsNullOrWhiteSpace($key)) {
    $key = [Environment]::GetEnvironmentVariable("H2_API_KEY", "User")
}
if ([string]::IsNullOrWhiteSpace($key)) {
    $key = $env:H2_API_KEY
}
if ([string]::IsNullOrWhiteSpace($key)) {
    throw "BLOCK_H2_API_KEY_MISSING"
}

$parsed = $PayloadJson | ConvertFrom-Json
if ($parsed.node -and ([string]$parsed.node -cne "victor")) {
    throw "BLOCK_NON_VICTOR_NODE"
}

$content = "``````json`n$PayloadJson`n``````"
$bodyHashtable = @{}
$bodyHashtable["model"] = "h2_roo_function"
$bodyHashtable["stream"] = $false
$messages = @()
$msg = @{}
$msg["role"] = "user"
$msg["content"] = $content
$messages += $msg
$bodyHashtable["messages"] = $messages

$body = $bodyHashtable | ConvertTo-Json -Depth 12 -Compress

$headers = @{ Authorization = "Bearer $key" }
$response = Invoke-WebRequest -UseBasicParsing `
    -Uri "https://chat.h2platform.ru/api/chat/completions" `
    -Method Post `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body `
    -TimeoutSec 930

if ($response.StatusCode -ne 200) {
    throw "BLOCK_OWUI_FUNCTION_HTTP_$($response.StatusCode)"
}
if ($OutFile) {
    [IO.File]::WriteAllText($OutFile, $response.Content, (New-Object Text.UTF8Encoding($false)))
}
Write-Output $response.Content
