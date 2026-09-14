param([string]$ExpectedHead)
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$status = @(& git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $status.Count -gt 0) { throw "Clone not clean: $status" }
& git -C $clone pull --ff-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$head = & git -C $clone rev-parse HEAD
Write-Output "CLONE_HEAD $head"
if ($head -ne $ExpectedHead) { throw 'Clone HEAD mismatch' }
$status = @(& git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $status.Count -gt 0) { throw "Clone not clean: $status" }
Write-Output 'CLONE PORCELAIN EMPTY'
