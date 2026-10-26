<#
.SYNOPSIS
Runs local backend and frontend verification without installing dependencies.
#>
[CmdletBinding()]
param(
    [string]$BackendPython = (Join-Path $PSScriptRoot '../backend/.venv/Scripts/python.exe'),
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonCommand = Get-Command $BackendPython -ErrorAction Stop
$pythonExecutable = $pythonCommand.Source

Push-Location (Join-Path $projectRoot 'backend')
try {
    & $pythonExecutable -m app.cli.check_comments
    if ($LASTEXITCODE -ne 0) { throw 'Backend comment coverage failed.' }
    & $pythonExecutable -m ruff check app tests
    if ($LASTEXITCODE -ne 0) { throw 'Backend lint failed.' }
    & $pythonExecutable -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
} finally {
    Pop-Location
}

if (-not $SkipFrontend) {
    $npmExecutable = (Get-Command npm.cmd -ErrorAction SilentlyContinue)
    if (-not $npmExecutable) { $npmExecutable = Get-Command npm -ErrorAction Stop }
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        & $npmExecutable.Source test
        if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed. Run npm ci first.' }
        & $npmExecutable.Source run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally {
        Pop-Location
    }
}
