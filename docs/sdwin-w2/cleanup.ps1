Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$workRoot = 'C:\Users\Ben\AppData\Local\Temp\sdwin\'
$rows = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'final-arms.json')) | ConvertFrom-Json
$checkIds = @(268372,273344,274976)
foreach ($row in $rows) { $checkIds += $row.powershell_pid; foreach ($call in $row.calls) { $checkIds += $call.pid } }
Get-ChildItem -LiteralPath $PSScriptRoot -Recurse -File -Filter 'argv.jsonl' | ForEach-Object {
    Get-Content -LiteralPath $_.FullName | ForEach-Object { $checkIds += ($_ | ConvertFrom-Json).pid }
}
foreach ($childId in ($checkIds | Sort-Object -Unique)) {
    if (Get-Process -Id $childId -ErrorAction SilentlyContinue) { throw "Recorded child still running: $childId" }
    Write-Output "GET-PROCESS GONE $childId"
}
$all = @(Get-CimInstance Win32_Process)
$self = $all | Where-Object ProcessId -eq $PID
foreach ($proc in $all) {
    $path = [string]$proc.ExecutablePath
    if ($path.StartsWith($clone + '\', [StringComparison]::OrdinalIgnoreCase) -or $path.StartsWith($workRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "Process under clone/work: $($proc.ProcessId) $path" }
    if ($proc.ProcessId -in @($PID,$self.ParentProcessId)) { continue }
    if ($proc.Name -in @('powershell.exe','pwsh.exe','cmd.exe') -and $proc.CommandLine -like '*sdwin*w2*') { throw "Work shell remains: $($proc.ProcessId)" }
}
Get-Process | Where-Object ProcessName -in @('python','pythonw') | ForEach-Object {
    if (-not $_.Path) { throw "Unreadable Python path $($_.Id)" }
    if ($_.Path.StartsWith($clone + '\', [StringComparison]::OrdinalIgnoreCase) -or $_.Path.StartsWith($workRoot, [StringComparison]::OrdinalIgnoreCase)) { throw "Python remains $($_.Id)" }
}
$head = & git -C $clone rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $head -ne '72d3a21239fbb79d3b2552c690bee4769b604c74') { throw "Unexpected clone HEAD $head" }
$status = @(& git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $status.Count) { throw 'Clone is dirty' }
Write-Output "CLONE HEAD $head; porcelain empty"
Write-Output "POWERSHELL $($PSVersionTable.PSVersion.ToString())"
Write-Output 'NO processes under CLONE or LAPTOP WORK; NO other W2 shells; all recorded PIDs gone'
exit 0
