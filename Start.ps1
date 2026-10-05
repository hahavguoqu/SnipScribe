$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot 'runtime'
$localUv = Join-Path $PSScriptRoot 'tools\uv.exe'
if (Test-Path $localUv) { & $localUv run --frozen --no-sync python launch.py }
else { uv run --frozen --no-sync python launch.py }
