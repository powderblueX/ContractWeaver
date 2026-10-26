<#
.SYNOPSIS
Stop only identified project processes and safely clean generated directories.
#>
param([switch]$RemoveEnvironment)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Use this script on Windows only.' }
$projectRoot = (Resolve-Path -LiteralPath (Split-Path -Parent $PSScriptRoot)).Path.TrimEnd('\')
. "$PSScriptRoot/windows-project-processes.ps1"

# Keep identities for orphan descendants; compare creation times to avoid PID reuse.
$observed = @{}
for ($attempt = 0; $attempt -lt 3; $attempt++) {
    foreach ($process in @(Get-ContractWeaverProcessSnapshot -ProjectRoot $projectRoot)) {
        $observed[[int]$process.ProcessId] = $process
    }
    foreach ($process in @($observed.Values | Sort-Object CreationDate -Descending)) {
        $current = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $($process.ProcessId)" -ErrorAction Stop
        if ($current -and $current.CreationDate -eq $process.CreationDate) {
            try { Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop }
            catch {
                if (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue) { throw }
            }
        }
    }
    Start-Sleep -Milliseconds 300
}
$remaining = @(Get-ContractWeaverProcessSnapshot -ProjectRoot $projectRoot)
foreach ($process in $observed.Values) {
    $current = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $($process.ProcessId)" -ErrorAction Stop
    if ($current -and $current.CreationDate -eq $process.CreationDate) { $remaining += $current }
}
if ($remaining.Count) { throw 'Some project processes are still running. No dependency cleanup performed; check permissions.' }

$generatedDirectories = @('frontend/node_modules/.vite', 'frontend/node_modules/.vite-temp', 'frontend/.npm-cache', 'backend/.pytest_cache', 'backend/.ruff_cache', '.pytest_cache', '.ruff_cache')
foreach ($sourceRoot in @('backend/app', 'backend/tests')) {
    $absoluteSource = Join-Path $projectRoot $sourceRoot
    if (Test-Path -LiteralPath $absoluteSource) {
        foreach ($cache in @(Get-ChildItem -LiteralPath $absoluteSource -Directory -Filter '__pycache__' -Recurse -Force)) {
            $generatedDirectories += $cache.FullName.Substring($projectRoot.Length + 1)
        }
    }
}
if ($RemoveEnvironment) { $generatedDirectories += @('backend/.venv', 'frontend/node_modules', 'frontend/dist') }
foreach ($relativePath in $generatedDirectories) {
    Remove-ContractWeaverGeneratedDirectory -ProjectRoot $projectRoot -RelativePath $relativePath
}
Write-Host 'Verified: no identified ContractWeaver server/launcher/descendant processes remain.'
Write-Host 'Source, backend/.env, user database and generated contracts are preserved.'
if ($RemoveEnvironment) { Write-Host 'Dependencies/build outputs removed. Run scripts/setup.bat before starting again.' }
