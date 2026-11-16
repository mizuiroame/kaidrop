# Builds dist/KaiDrop.exe: one file, no console window.
$ErrorActionPreference = "Stop"
$python = if (Test-Path .venv/Scripts/python.exe) { ".venv/Scripts/python.exe" } else { "python" }
& $python -m PyInstaller --onefile --windowed --name KaiDrop --icon assets/kaidrop.ico --clean kaidrop/__main__.py
Write-Host "Built dist/KaiDrop.exe"
