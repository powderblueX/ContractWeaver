param([ValidateSet('all', 'backend', 'frontend')][string]$Component = 'all')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

# Initialize only absent configuration; never overwrite a developer's secrets.
if (-not (Test-Path -LiteralPath "$projectRoot/backend/.env")) {
    Copy-Item -LiteralPath "$projectRoot/backend/.env.example" -Destination "$projectRoot/backend/.env"
    Write-Host 'Created backend/.env. Edit LAW_LLM_API_KEY before using model features.'
}
if ($Component -in @('all', 'backend')) {
    Get-Command python -ErrorAction Stop | Out-Null
    & python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required. Install it and add it to PATH.' }
    $backendPython = "$projectRoot/backend/.venv/Scripts/python.exe"
    if (-not (Test-Path -LiteralPath $backendPython)) {
        & python -m venv "$projectRoot/backend/.venv"
        if ($LASTEXITCODE -ne 0) { throw 'Could not create backend virtual environment.' }
    }
    & $backendPython -m pip install --no-cache-dir -r "$projectRoot/backend/requirements.txt"
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed; check network and Python.' }
}
if ($Component -in @('all', 'frontend')) {
    Get-Command node -ErrorAction Stop | Out-Null
    & node -e 'if(Number(process.versions.node.split(/\./)[0])<20) process.exit(1)'
    if ($LASTEXITCODE -ne 0) { throw 'Node.js 20+ is required.' }
    Push-Location "$projectRoot/frontend"
    try {
        & npm.cmd ci --cache "$projectRoot/frontend/.npm-cache"
        if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed; check network and Node.js.' }
    } finally { Pop-Location }
}
Write-Host 'Setup complete. Configure backend/.env, then run start-backend.bat and start-frontend.bat in separate terminals.'
