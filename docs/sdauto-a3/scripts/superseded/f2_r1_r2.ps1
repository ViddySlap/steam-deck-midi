# sdauto A3: Windows F2 arm. -Which head (clone at pushed HEAD) or v049 (git archive of v0.4.9 into LAPTOP WORK).
# Never --tray, never a real MIDI port (--dry-run), UI off (--no-ui), engines/pulse/relay off, loopback non-default ports.
param([ValidateSet('head','v049')][string]$Which, [int]$Udp, [int]$Ui)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work=Join-Path $PSScriptRoot "f2-$Which"
$python=Join-Path $clone '.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $work) { throw "work dir exists: $work" }
New-Item -ItemType Directory -Path $work | Out-Null
Write-Output "CLONE_HEAD $(& git --no-optional-locks -C $clone rev-parse HEAD)"
if ($Which -eq 'head') {
  $tree=$clone
  Copy-Item -LiteralPath (Join-Path $clone 'config') -Destination (Join-Path $work 'config') -Recurse
  $map=Join-Path $work 'config\windows_midi_map.json'
  $extra=@('--no-browser')
} else {
  $tree=Join-Path $work 'tree'
  New-Item -ItemType Directory -Path $tree | Out-Null
  $commit=(& git --no-optional-locks -C $clone rev-parse 'v0.4.9^{commit}')
  Write-Output "V049_COMMIT $commit"
  & git --no-optional-locks -C $clone archive --format=tar -o (Join-Path $work 'v049.tar') $commit
  if ($LASTEXITCODE -ne 0) { throw 'git archive failed' }
  & tar.exe -xf (Join-Path $work 'v049.tar') -C $tree
  if ($LASTEXITCODE -ne 0) { throw 'tar failed' }
  $map=Join-Path $tree 'config\windows_midi_map.json'
  $extra=@()
}
foreach ($port in @($Udp)) {
  if (@(Get-NetUDPEndpoint -LocalPort $port -ErrorAction SilentlyContinue).Count) { throw "udp $port in use" }
}
if (@(Get-NetTCPConnection -LocalPort $Ui -ErrorAction SilentlyContinue).Count) { throw "tcp $Ui in use" }
Write-Output "PORTS_FREE udp=$Udp ui=$Ui"
$browser=($python -replace '\\','/') + ' -c pass %s'
$cfg=[ordered]@{ label=$Which; python=$python; tree=$tree; map=$map; udp=$Udp; ui=$Ui; extra=$extra; browser=$browser;
  work=$work; out=(Join-Path $work 'result.json'); log=(Join-Path $work 'bridge.log'); record=(Join-Path $work "owned-tree-$Which.txt") }
$cfgPath=Join-Path $work 'arm.json'
[IO.File]::WriteAllText($cfgPath,(ConvertTo-Json -InputObject $cfg -Depth 3),(New-Object Text.UTF8Encoding($false)))
$driver=Start-Process -FilePath $python -ArgumentList @('-B', (Join-Path $PSScriptRoot 'win_f2.py'), $cfgPath) -PassThru -NoNewWindow
$null=$driver.Handle
$did=$driver.Id
Write-Output "DRIVER_LAUNCHER_PID $did"
$seen=@{}
$sw=[Diagnostics.Stopwatch]::StartNew()
while (-not $driver.HasExited -and $sw.Elapsed.TotalSeconds -lt 180) {
  foreach ($p in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$did")) { $seen[[int]$p.ProcessId]=[string]$p.ExecutablePath }
  Start-Sleep -Milliseconds 500
}
Write-Output "DRIVER_EXITED $($driver.HasExited) after $([int]$sw.Elapsed.TotalSeconds)s code=$(if($driver.HasExited){$driver.ExitCode}else{'n/a'})"
$recorded=@()
if (Test-Path -LiteralPath $cfg.record) { $recorded=@(Get-Content -LiteralPath $cfg.record | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ }) }
Write-Output "RECORDED_TREE $($recorded -join ',')"
if (Test-Path -LiteralPath $cfg.out) { Get-Content -LiteralPath $cfg.out | ForEach-Object { Write-Output "JSON $_" } } else { Write-Output 'NO_RESULT_JSON' }
# Fail-safe: a recorded lane pid (this arm's own record) still alive is stopped by pid; never session 1 or protected paths.
foreach ($r in $recorded) {
  $cim=@(Get-CimInstance Win32_Process -Filter "ProcessId=$r")
  if ($cim.Count -eq 0) { continue }
  $exe=[string]$cim[0].ExecutablePath
  if ($cim[0].SessionId -eq 1 -or $exe -like 'C:\Program Files\STEAMDECK MIDI Receiver 2\*' -or $exe -like 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi\*') {
    Write-Output "NEEDS-MASTER: sdauto protected process in lane record $r $($cim[0].CommandLine)"; continue
  }
  Write-Output "FAILSAFE_STOP $r $exe"
  Stop-Process -Id $r -Force
}
Start-Sleep -Seconds 1
$ids=@($did)+@($seen.Keys)+$recorded | Sort-Object -Unique
foreach ($i in $ids) {
  $g=@(Get-Process -Id $i -ErrorAction SilentlyContinue)
  Write-Output ("PID {0} gone={1}" -f $i, ($g.Count -eq 0))
}
$lane=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') })
Write-Output "PYTHON_PROCESSES_AFTER $($lane.Count)"
foreach ($l in $lane) { Write-Output "PY $($l.ProcessId) session=$($l.SessionId) $($l.ExecutablePath) $($l.CommandLine)" }
exit 0
