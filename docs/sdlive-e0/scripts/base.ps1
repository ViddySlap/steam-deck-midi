Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$expected='14aa21824843dbe148dc3ac3d0bf58929ef34c3a'
$dirty=@(& git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $dirty.Count) { throw 'Clone is not clean' }
git -C $clone pull --ff-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$head=(& git -C $clone rev-parse HEAD)
if ($LASTEXITCODE -ne 0 -or $head -ne $expected) { throw "Unexpected HEAD $head" }
Write-Output "BASE $head"
$base=Join-Path $PSScriptRoot 'base'
if (Test-Path $base) { throw 'Scratch base already exists' }
New-Item -ItemType Directory -Path $base | Out-Null
git -C $clone archive --format=tar --output="$PSScriptRoot\base.tar" $expected
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
tar -xf "$PSScriptRoot\base.tar" -C $base
exit $LASTEXITCODE
