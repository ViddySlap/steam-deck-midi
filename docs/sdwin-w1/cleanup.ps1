Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
foreach ($knownId in @(272308, 276236, 273052)) {
    if (Get-Process -Id $knownId -ErrorAction SilentlyContinue) { throw "Known pid still exists: $knownId" }
    Write-Output "GET-PROCESS GONE $knownId"
}
$leaks = @(Get-Process | Where-Object { $_.ProcessName -in @('python','pythonw') } | ForEach-Object {
    if (-not $_.Path) { throw "Unreadable python path: $($_.Id)" }
    if ($_.Path.StartsWith($clone + '\', [StringComparison]::OrdinalIgnoreCase) -or $_.Path.StartsWith('C:\Users\Ben\AppData\Local\Temp\sdwin\', [StringComparison]::OrdinalIgnoreCase)) { $_ }
})
if ($leaks.Count -ne 0) { throw "Python leaks: $($leaks.Id)" }
Write-Output 'GET-PROCESS: no python.exe or pythonw.exe under CLONE or LAPTOP WORK'
$head = & git -C $clone rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $head -ne '84e583b329bff502553864d1b5f3663dadd6559a') { throw 'Clone identity mismatch' }
$status = @(& git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $status.Count -ne 0) { throw "Clone not clean: $status" }
Write-Output "CLONE_HEAD $head; PORCELAIN EMPTY"
exit 0
