<#
.SYNOPSIS
Start Vite from the project frontend dependency tree.
#>
param([string]$BindAddress = '127.0.0.1', [ValidateRange(1, 65535)][int]$Port = 5173)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath "$projectRoot/frontend/node_modules/.bin/vite.cmd")) { throw 'Run scripts/setup.bat first.' }
Push-Location "$projectRoot/frontend"
try {
    Write-Host "Frontend: http://${BindAddress}:${Port} | Ctrl+C to stop. Start the backend separately."
    & node "$projectRoot/frontend/node_modules/vite/bin/vite.js" --host $BindAddress --port $Port --strictPort
    if ($LASTEXITCODE -ne 0) { throw 'Frontend exited with an error; inspect the message above.' }
} finally { Pop-Location }
