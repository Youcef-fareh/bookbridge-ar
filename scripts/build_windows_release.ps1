Param(
    [string]$Python = "python",
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "[1/4] Installing packaging dependencies..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt
& $Python -m pip install pyinstaller==6.10.0

Write-Host "[2/4] Building BookBridge EXE..."
New-Item -ItemType Directory -Force -Path "$Root\dist\app" | Out-Null
if (Test-Path "$Root\icon.ico") {
    & pyinstaller --noconfirm --clean --onefile --windowed --name BookBridge `
      --icon "$Root\icon.ico" `
            --manifest "$Root\installer\BookBridge.manifest" `
      --add-data "README.md;." `
      --add-data "sample_data;sample_data" `
      --distpath "$Root\dist\app" `
      "$Root\bookbridge\app.py"
} else {
    & pyinstaller --noconfirm --clean --onefile --windowed --name BookBridge `
            --manifest "$Root\installer\BookBridge.manifest" `
      --add-data "README.md;." `
      --add-data "sample_data;sample_data" `
      --distpath "$Root\dist\app" `
      "$Root\bookbridge\app.py"
}

Write-Host "[3/4] Building installer..."
if (-not (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue)) {
    throw "Inno Setup is not installed. Install it first or run the GitHub Action workflow on a Windows runner."
}

New-Item -ItemType Directory -Force -Path "$Root\dist\installer" | Out-Null
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "$Root\installer\BookBridge.iss"

Write-Host "[4/4] Finished. Installer is in $Root\dist\installer\BookBridge-Setup.exe"
