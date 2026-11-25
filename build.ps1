# Builds dist/KaiDrop.exe: one file, no console window.
# -Out: the folder for the .exe (a test build: -Out dist-test).
# -Python: the Python to build with (default: .venv's), with requirements-build.txt installed:
#   pip install --require-hashes -r requirements-build.txt
# Signing (optional, see docs/developers.md): set KAIDROP_SIGN_THUMBPRINT to a code-signing
# certificate's thumbprint in the user's certificate store, with signtool.exe on PATH or in the
# Windows SDK. Without it, the .exe is left unsigned, as before.
param([string]$Out = "dist", [string]$Python = "")
$ErrorActionPreference = "Stop"
if (-not $Python) { $Python = if (Test-Path .venv/Scripts/python.exe) { ".venv/Scripts/python.exe" } else { "python" } }

# No UPX (--noupx): packed files look like malware to antivirus programs and gain little here.
# jieba: only its code; its own dictionary and models are left out (tools/hooks/hook-jieba.py),
# KaiDrop brings its shorter word list (kaidrop/data/words-zh.xz).
& $Python -m PyInstaller --onefile --windowed --noupx --name KaiDrop --icon assets/kaidrop.ico `
    --collect-all tkinterdnd2 --collect-data pypinyin --collect-data anyascii `
    --additional-hooks-dir tools/hooks --exclude-module jieba.analyse --exclude-module jieba.posseg `
    --exclude-module jieba.lac_small --exclude-module paddle `
    --add-data "kaidrop/data/readings-ja.xz;kaidrop/data" --add-data "kaidrop/data/words-zh.xz;kaidrop/data" `
    --distpath $Out --clean kaidrop/__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
$exe = Join-Path $Out "KaiDrop.exe"

if ($env:KAIDROP_SIGN_THUMBPRINT) {
    $signtool = Get-Command signtool.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    if (-not $signtool) {
        $signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
            Sort-Object FullName | Select-Object -Last 1 -ExpandProperty FullName
    }
    if (-not $signtool) { throw "KAIDROP_SIGN_THUMBPRINT is set but signtool.exe wasn't found (Windows SDK)" }
    $timestamp = if ($env:KAIDROP_SIGN_TIMESTAMP) { $env:KAIDROP_SIGN_TIMESTAMP } else { "http://timestamp.digicert.com" }
    & $signtool sign /sha1 $env:KAIDROP_SIGN_THUMBPRINT /fd sha256 /tr $timestamp /td sha256 /d KaiDrop $exe
    if ($LASTEXITCODE -ne 0) { throw "Signing failed" }
    & $signtool verify /pa $exe
    if ($LASTEXITCODE -ne 0) { throw "The signature doesn't verify" }
}

Write-Host "Built $exe"
Write-Host "SHA-256: $((Get-FileHash $exe -Algorithm SHA256).Hash)"
