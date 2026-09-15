param([string]$Expected)
Set-StrictMode -Version Latest
$ErrorActionPreference='Continue'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$dirty=@(& git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $dirty.Count) { Write-Output 'Clone is not clean'; exit 3 }
foreach ($sha in @('91e1b01708aa6f9de184b7f79de8286f32d42485','95d3da0a740911e0677a549b75bee648a198b2cc','bd1bdda42d9f9926ec23ab5d5218e029435f50a4','b2ca727c0acdc710a9ae98b6e01b76f3d4f28914',$Expected)) {
  $ok=$false
  foreach ($try in 1..3) {
    & git -C $clone -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=60 fetch origin $sha 2>&1 | ForEach-Object { Write-Output "FETCH $sha try$try $_" }
    if ($LASTEXITCODE -eq 0) { $ok=$true; break }
    Start-Sleep -Seconds 5
  }
  Write-Output "FETCHED $sha ok=$ok"
  if (-not $ok) { exit 4 }
}
& git -C $clone fetch origin 2>&1 | ForEach-Object { Write-Output "FETCHREF $_" }
Write-Output "FETCHREF_EXIT $LASTEXITCODE"
& git -C $clone merge --ff-only $Expected 2>&1 | Select-Object -Last 3 | ForEach-Object { Write-Output "MERGE $_" }
$head=(& git -C $clone rev-parse HEAD)
Write-Output "PINNED_HEAD $head"
$dirty=@(& git -C $clone status --porcelain)
Write-Output "PORCELAIN_LINES $($dirty.Count)"
if ($head -ne $Expected -or $dirty.Count) { exit 5 }
exit 0
