# Cleanup script: move all junk from root to _TRASH_2026/
# Whitelist of files & directories that MUST stay in root.
# Everything else (only files at top level) is moved.

$ErrorActionPreference = "Stop"
$root = (Get-Location).Path
$trash = Join-Path $root "_TRASH_2026"

if (-not (Test-Path $trash)) {
    New-Item -ItemType Directory -Path $trash | Out-Null
}

# Files that MUST stay at root level
$keepFiles = @(
    # Core app
    "app.py", "wsgi.py", "models.py",
    # Data modules used by app/routes
    "olympiads.py", "problems.py", "problem_images.py",
    "simple_prefetch.py",
    # Configs
    ".env", ".env.example", ".env.migration",
    ".gitignore",
    "requirements.txt", "requirements_new.txt", "runtime.txt",
    "render.yaml", "Procfile",
    "formyle.code-workspace",
    # Databases
    "formyla.db", "tasks.db",
    # This script & its inventory
    "_cleanup_root.ps1"
)

# Lowercase set for case-insensitive compare
$keepSet = @{}
foreach ($f in $keepFiles) { $keepSet[$f.ToLower()] = $true }

# Collect inventory
$movedLog = Join-Path $trash "_MOVED_FILES.txt"
"# Files moved to _TRASH_2026 on $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $movedLog -Encoding utf8

$movedCount = 0
$skippedCount = 0

# Only process FILES at root (not directories - all dirs stay)
Get-ChildItem -Path $root -File -Force | ForEach-Object {
    $name = $_.Name
    $nameLower = $name.ToLower()

    if ($keepSet.ContainsKey($nameLower)) {
        $skippedCount++
        return
    }

    # Move to trash
    $dest = Join-Path $trash $name
    # Handle name collisions (shouldn't happen but be safe)
    if (Test-Path $dest) {
        $dest = Join-Path $trash ("{0}_{1}" -f (Get-Random), $name)
    }
    try {
        Move-Item -LiteralPath $_.FullName -Destination $dest -Force
        Add-Content -Path $movedLog -Value $name
        $movedCount++
    } catch {
        Write-Host "FAILED: $name - $_" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== CLEANUP COMPLETE ===" -ForegroundColor Green
Write-Host "Kept in root:   $skippedCount files" -ForegroundColor Cyan
Write-Host "Moved to trash: $movedCount files" -ForegroundColor Yellow
Write-Host "Trash location: $trash" -ForegroundColor Yellow
Write-Host ""
Write-Host "To restore everything:" -ForegroundColor Gray
Write-Host "  Move-Item _TRASH_2026/* . -Force" -ForegroundColor Gray
Write-Host "To permanently delete trash:" -ForegroundColor Gray
Write-Host "  Remove-Item _TRASH_2026 -Recurse -Force" -ForegroundColor Gray
