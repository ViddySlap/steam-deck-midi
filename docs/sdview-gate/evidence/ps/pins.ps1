$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$fx='C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures'
$pre = & git -C $clone rev-parse HEAD; Write-Output "clone_head_before=$pre"
$porc0=@(& git -C $clone status --porcelain); Write-Output "clone_porcelain_before_lines=$($porc0.Count)"
$ErrorActionPreference='Continue'
$pout = & cmd.exe /c "git -C `"$clone`" pull --ff-only 2>&1"; $pe=$LASTEXITCODE
$ErrorActionPreference='Stop'
$pout | ForEach-Object { Write-Output "pull: $_" }; Write-Output "pull_exit=$pe"
if ($pe -ne 0) { exit 3 }
$head = & git -C $clone rev-parse HEAD; Write-Output "clone_head=$head"
$tag = & git -C $clone rev-parse 'v0.4.9^{commit}'; Write-Output "v049_peeled=$tag"
$porc=@(& git -C $clone status --porcelain); Write-Output "clone_porcelain_lines=$($porc.Count)"
$sums = Get-Content -LiteralPath (Join-Path $clone 'scripts\showready\SHA256SUMS')
$bad=0
foreach ($l in $sums) { if ($l -match '^([0-9a-f]{64})\s+(.+)$') { $want=$Matches[1]; $rel=$Matches[2]; $got=(Get-FileHash -LiteralPath (Join-Path $clone ($rel -replace '/','\')) -Algorithm SHA256).Hash.ToLowerInvariant(); $ok=($got -eq $want); if(-not $ok){$bad++}; Write-Output ("pin {0} {1} {2}" -f $(if($ok){'OK '}else{'BAD'}), $got, $rel) } }
Write-Output "pins_bad=$bad"
foreach ($set in @('mac','windows-installed')) {
  $root=Join-Path $fx $set
  $mp=Join-Path $root 'MANIFEST.sha256'
  if (-not (Test-Path -LiteralPath $mp)) { Write-Output "manifest $set ABSENT at $mp"; $bad++; continue }
  Write-Output ("manifest_file {0} sha256={1}" -f $set,(Get-FileHash -LiteralPath $mp -Algorithm SHA256).Hash.ToLowerInvariant())
  $m = [IO.File]::ReadAllText($mp) | ConvertFrom-Json
  $n=0
  foreach ($e in $m.entries) { $n++; $p=Join-Path $root ($e.relative -replace '/','\'); $fi=Get-Item -LiteralPath $p -Force; $h=(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant(); $ok=($h -eq $e.sha256_copy -and $fi.Length -eq $e.bytes); if(-not $ok){$bad++}; Write-Output ("fixture {0} {1} {2} {3} {4}" -f $(if($ok){'OK '}else{'BAD'}),$set,$h.Substring(0,12),$fi.Length,$e.relative) }
  Write-Output "manifest $set entries=$n"; if ($n -eq 0) { $bad++ }
}
Write-Output "total_bad=$bad"
if ($bad) { exit 1 } else { exit 0 }
