param([string]$Expected)
Set-StrictMode -Version Latest
$ErrorActionPreference='Continue'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$bundle=Join-Path $PSScriptRoot 'sdlive.bundle'
$dirty=@(& git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $dirty.Count) { Write-Output 'Clone is not clean'; exit 3 }
Write-Output "BUNDLE_SHA256 $((Get-FileHash -Algorithm SHA256 -LiteralPath $bundle).Hash.ToLowerInvariant())"
& git -C $clone bundle verify $bundle 2>&1 | ForEach-Object { Write-Output "VERIFY $_" }
if ($LASTEXITCODE -ne 0) { exit 4 }
& git -C $clone fetch $bundle chain/steamdeck-20260914 2>&1 | ForEach-Object { Write-Output "FETCH $_" }
if ($LASTEXITCODE -ne 0) { exit 5 }
$fetched=(& git -C $clone rev-parse FETCH_HEAD)
Write-Output "FETCH_HEAD $fetched"
if ($fetched -ne $Expected) { exit 6 }
& git -C $clone merge --ff-only $Expected 2>&1 | Select-Object -Last 2 | ForEach-Object { Write-Output "MERGE $_" }
if ($LASTEXITCODE -ne 0) { exit 7 }
$head=(& git -C $clone rev-parse HEAD)
$dirty=@(& git -C $clone status --porcelain)
Write-Output "PINNED_HEAD $head"
Write-Output "PORCELAIN_LINES $($dirty.Count)"
if ($head -ne $Expected -or $dirty.Count) { exit 8 }
exit 0
