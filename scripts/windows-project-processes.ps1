# Windows-only process discovery. Never match by port alone or kill every node/python.
function Get-ContractWeaverProcessSnapshot {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot)
    $processes = @(Get-CimInstance -ClassName Win32_Process -ErrorAction Stop)
    $normalizedRoot = $ProjectRoot.Replace('/', '\').TrimEnd('\').ToLowerInvariant()
    $launcherPattern = '(?i)(?:^|\s)-File\s+"?' + [regex]::Escape($normalizedRoot) + '\\scripts\\start-(?:backend|frontend)\.ps1"?(?:\s|$)'
    $batchPattern = '(?i)(?:^|\s)(?:/|\\)c\s+"{0,2}' + [regex]::Escape($normalizedRoot) + '\\scripts\\start-(?:backend|frontend)\.bat(?:"|\s|$)'
    $owned = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($process in $processes) {
        if ($process.ProcessId -eq $PID) { continue }
        $command = ([string]$process.CommandLine).Replace('/', '\').ToLowerInvariant()
        $executable = ([string]$process.ExecutablePath).Replace('/', '\').ToLowerInvariant()
        $isBackend = $process.Name -in @('python.exe', 'pythonw.exe') -and
            $executable.StartsWith($normalizedRoot + '\backend\.venv\') -and
            $command -match '-m\s+uvicorn\s+app\.main:app(?:\s|$)'
        $isFrontend = $process.Name -eq 'node.exe' -and
            $command.Contains($normalizedRoot + '\frontend\node_modules\vite\bin\vite.js')
        $isLauncher = $process.Name -in @('powershell.exe', 'pwsh.exe') -and
            $command -notmatch '(?:^|\s)-(?:command|encodedcommand|c|e)(?:\s|$)' -and
            $command -match $launcherPattern
        $isBatchLauncher = $process.Name -eq 'cmd.exe' -and $command -match $batchPattern
        if ($isBackend -or $isFrontend -or $isLauncher -or $isBatchLauncher) { [void]$owned.Add([int]$process.ProcessId) }
    }
    # Only descendants of strongly identified project processes are included.
    do {
        $added = $false
        foreach ($process in $processes) {
            if ($process.ProcessId -ne $PID -and $owned.Contains([int]$process.ParentProcessId) -and -not $owned.Contains([int]$process.ProcessId)) {
                $parent = $processes | Where-Object { $_.ProcessId -eq $process.ParentProcessId } | Select-Object -First 1
                if ($parent -and $process.CreationDate -ge $parent.CreationDate) {
                    [void]$owned.Add([int]$process.ProcessId)
                    $added = $true
                }
            }
        }
    } while ($added)
    return @($processes | Where-Object { $owned.Contains([int]$_.ProcessId) })
}

function Remove-ContractWeaverGeneratedDirectory {
    param([Parameter(Mandatory = $true)][string]$ProjectRoot, [Parameter(Mandatory = $true)][string]$RelativePath)
    $target = [IO.Path]::GetFullPath((Join-Path $ProjectRoot $RelativePath))
    if (-not $target.StartsWith($ProjectRoot.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Cleanup target is outside the project.'
    }
    if (-not (Test-Path -LiteralPath $target)) { return }
    # A junction/symlink may point outside this project; refuse rather than traverse it.
    $ancestor = Get-Item -LiteralPath $target -Force
    while ($ancestor -and $ancestor.FullName -ne $ProjectRoot) {
        if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing linked cleanup target: $RelativePath" }
        $ancestor = $ancestor.Parent
    }
    $linked = Get-ChildItem -LiteralPath $target -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint } | Select-Object -First 1
    if ($linked) { throw "Refusing cleanup containing linked files: $RelativePath" }
    Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction Stop
    Write-Host "Removed generated directory: $RelativePath"
}
