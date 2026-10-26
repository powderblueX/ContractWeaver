<#
.SYNOPSIS
Start the local API with its project virtual environment.
#>
param([string]$BindAddress = '127.0.0.1', [ValidateRange(1, 65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONDONTWRITEBYTECODE = '1'
$backendPython = "$projectRoot/backend/.venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $backendPython)) { throw 'Run scripts/setup.bat first.' }
if (-not (Test-Path -LiteralPath "$projectRoot/backend/.env")) { throw 'Create backend/.env from .env.example first.' }
Push-Location "$projectRoot/backend"
try {
    Write-Host "Backend: http://${BindAddress}:${Port} | Ctrl+C to stop."
    & $backendPython -m uvicorn app.main:app --host $BindAddress --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Backend exited with an error; inspect the message above.' }
} finally { Pop-Location }
