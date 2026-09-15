Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work='C:\Users\Ben\AppData\Local\Temp\sdwin\'
$rows=@()
foreach ($file in @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.gone.json' -File)) {
    $proof=[IO.File]::ReadAllText($file.FullName) | ConvertFrom-Json
    foreach ($row in $proof) {
        $alive=@(Get-Process -Id $row.pid -ErrorAction SilentlyContinue)
        $rows += [ordered]@{source=$file.Name; pid=$row.pid; gone=($alive.Count -eq 0)}
        if ($alive.Count -ne 0) { throw "Owned PID exists: $($row.pid)" }
    }
}
$python=@(Get-Process | Where-Object { $_.ProcessName -in @('python','pythonw') })
$inventory=@()
foreach ($process in $python) {
    if (-not $process.Path) { throw "Unreadable Python path $($process.Id)" }
    $inventory += [ordered]@{pid=$process.Id;path=$process.Path}
    if ($process.Path.StartsWith($clone+'\',[StringComparison]::OrdinalIgnoreCase) -or $process.Path.StartsWith($work,[StringComparison]::OrdinalIgnoreCase)) { throw "Python leak $($process.Id) $($process.Path)" }
}
# Also catch venv worker images residing in the system Python directory.
$cmdLeaks=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -and ($_.CommandLine.Contains($PSScriptRoot) -or $_.CommandLine.Contains($clone)) } | Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine)
if ($cmdLeaks.Count -ne 0) { throw 'Python command line still refers to W4/clone' }
$status=@(git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $status.Count -ne 0) { throw 'Clone dirty' }
$head=git -C $clone rev-parse HEAD
if ($head -ne 'b3b28612c3be1a9e841c82c557a219e72b73eaea') { throw 'Clone head changed' }
[ordered]@{head=$head;status=$status;pid_checks=$rows;python_inventory=$inventory;command_line_leaks=$cmdLeaks} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'cleanup.json') -Encoding UTF8
Write-Output "CLEANUP GREEN: $($rows.Count) recorded PID checks absent; no Python path under CLONE or LAPTOP WORK; no matching Python command line; clone clean at $head"
