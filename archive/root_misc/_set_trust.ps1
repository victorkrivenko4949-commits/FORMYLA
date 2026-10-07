$settings = 'C:\Users\Redmi\AppData\Roaming\Code\User\settings.json'
$json = if (Test-Path $settings) { Get-Content $settings -Raw | ConvertFrom-Json } else { [PSCustomObject]@{} }
$json | Add-Member -MemberType NoteProperty -Name 'security.workspace.trust.enabled' -Value $false -Force
$json | ConvertTo-Json -Depth 10 | Set-Content $settings -Encoding UTF8
Write-Output 'settings updated:'
Get-Content $settings -Raw
