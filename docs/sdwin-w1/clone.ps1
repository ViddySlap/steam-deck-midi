param([string]$ExpectedHead)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
if (Test-Path -LiteralPath $clone) { throw 'CLONE EXISTS: refusing overwrite' }
& git clone --branch chain/steamdeck-20260914 https://github.com/ViddySlap/steam-deck-midi.git $clone
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$head = & git -C $clone rev-parse HEAD
$tag = & git -C $clone rev-parse 'v0.4.9^{commit}'
Write-Output "CLONE_HEAD $head"
Write-Output "TAG_COMMIT $tag"
if ($head -ne $ExpectedHead -or $tag -ne 'e66ff44b36eadb6d43db01680c65279df82cd63c') { throw 'Clone identity mismatch' }
& py -3.12 --version
if ($LASTEXITCODE -ne 0) { Write-Output 'NEEDS-MASTER: Python 3.12 unavailable'; exit 3 }
exit 0
