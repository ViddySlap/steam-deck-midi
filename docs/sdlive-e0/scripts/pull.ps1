param([string]$Expected)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$dirty=@(& git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $dirty.Count) { throw 'Clone is not clean' }
git -C $clone pull --ff-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$head=(& git -C $clone rev-parse HEAD)
if ($LASTEXITCODE -ne 0 -or $head -ne $Expected) { throw "Unexpected HEAD $head" }
Write-Output "PINNED_HEAD $head"
exit 0
