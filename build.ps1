# Builds dist/KaiDrop.exe: one file, no console window.
# -Out: the folder for the .exe (a test build: -Out dist-test).
param([string]$Out = "dist")
$ErrorActionPreference = "Stop"
$python = if (Test-Path .venv/Scripts/python.exe) { ".venv/Scripts/python.exe" } else { "python" }
& $python -m PyInstaller --onefile --windowed --name KaiDrop --icon assets/kaidrop.ico --collect-all tkinterdnd2 `
    --collect-data pypinyin --collect-data anyascii --add-data "kaidrop/data/readings-ja.xz;kaidrop/data" `
    --distpath $Out --clean kaidrop/__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host "Built $Out/KaiDrop.exe"
