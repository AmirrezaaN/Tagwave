# Builds dist\Tagwave-Setup-<version>.exe from scratch.
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1 [-SkipTests]
param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"

if (-not $SkipTests) {
    Write-Host "== Running tests" -ForegroundColor Cyan
    & $py -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw "Tests failed - not building." }
}

Write-Host "== Building the interface" -ForegroundColor Cyan
Push-Location ui
$env:NODE_TLS_REJECT_UNAUTHORIZED = "1"
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "UI build failed." }
Pop-Location

Write-Host "== Icons" -ForegroundColor Cyan
& $py packaging\make_icon.py

Write-Host "== Packaging the app (PyInstaller)" -ForegroundColor Cyan
& $py -m PyInstaller packaging\tagwave.spec --noconfirm --distpath build\dist --workpath build\work --log-level WARN
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }

Write-Host "== Creating the installer (Inno Setup)" -ForegroundColor Cyan
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found. Install it from https://jrsoftware.org/isdl.php" }
& $iscc /Q packaging\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

Get-ChildItem dist\*.exe | ForEach-Object { Write-Host ("Done: {0}  ({1:N1} MB)" -f $_.FullName, ($_.Length / 1MB)) -ForegroundColor Green }
