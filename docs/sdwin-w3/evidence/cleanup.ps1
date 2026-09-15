Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work = 'C:\Users\Ben\AppData\Local\Temp\sdwin\'
foreach ($childId in @(274068, 272392, 273716, 276348, 262116)) {
    if (Get-Process -Id $childId -ErrorAction SilentlyContinue) { throw "Owned suite PID remains: $childId" }
    Write-Output "GET-PROCESS GONE $childId"
}
Get-Process | Where-Object { $_.ProcessName -in @('python','pythonw') } | ForEach-Object {
    if (-not $_.Path) { throw "Unreadable Python path: $($_.Id)" }
    if ($_.Path.StartsWith($clone + '\', [StringComparison]::OrdinalIgnoreCase) -or $_.Path.StartsWith($work, [StringComparison]::OrdinalIgnoreCase)) { throw "Python leak: $($_.Id) $($_.Path)" }
}
Write-Output 'GET-PROCESS: no python.exe or pythonw.exe under CLONE or LAPTOP WORK'
$head = git -C $clone rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $head -ne 'e8a64f4efe526ba3210731083355c95472915e2e') { throw "Clone identity mismatch: $head" }
$status = @(git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $status.Count -ne 0) { throw 'Clone not clean' }
Write-Output "CLEAN_CLONE_HEAD $head"
