param([string]$Batch='all')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$wg='C:\Users\Ben\AppData\Local\Temp\sdwin\wg'
$fx='C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures'
$res=Join-Path $wg 'results'; $scr=Join-Path $wg 'ab'
New-Item -ItemType Directory -Force -Path $res,$scr | Out-Null
$py=Join-Path $clone '.venv\Scripts\python.exe'
$script=Join-Path $wg 'deck-script.json'
$env:PYSTRAY_BACKEND='dummy'; $env:BROWSER='C:/Windows/System32/cmd.exe /c rem %s'; $env:TEMP=$scr; $env:TMP=$scr
Set-Location -LiteralPath $clone
Write-Output "HEAD $(& git -C $clone rev-parse HEAD)"
if (-not (Test-Path -LiteralPath $script)) {
  $g = & $py -B scripts\showready\deck_script.py --fixtures $fx --out $script; Write-Output "GEN exit=$LASTEXITCODE $g"
  if ($LASTEXITCODE -ne 0) { exit 3 }
}
$all=[ordered]@{
 'mac-edm'=@("$fx\mac\presets\EDM Show.json",'windows');
 'mac-ptz'=@("$fx\mac\presets\PTZ.json",'windows');
 'mac-default'=@("$fx\mac\presets\default.json",'');
 'win-edm'=@("$fx\windows-installed\presets\EDM Show.json",'');
 'win-ptz'=@("$fx\windows-installed\presets\PTZ.json",'');
 'win-default'=@("$fx\windows-installed\presets\default.json",'');
 'tracked-default'=@("$clone\config\presets\default.json",'')
}
$names = switch ($Batch) { '1' { @('mac-edm','mac-ptz','win-edm','win-ptz') } '2' { @('mac-default','win-default','tracked-default') } default { @($all.Keys) } }
$procs=@{}
foreach ($n in $names) {
  $preset=$all[$n][0]; $sec=$all[$n][1]
  $a = "-B scripts\showready\ab_run.py --candidate HEAD --preset `"$preset`""
  if ($sec) { $a += " --section $sec" }
  $a += " --script `"$script`" --fixtures `"$fx`" --scratch `"$scr`" --out `"$res\$n.json`""
  $p=Start-Process -FilePath $py -ArgumentList $a -NoNewWindow -PassThru -RedirectStandardOutput "$res\$n.stdout" -RedirectStandardError "$res\$n.stderr"
  $null=$p.Handle
  $procs[$n]=$p
  Write-Output "START $n pid=$($p.Id) args=$a"
}
$seen=@{}
function Desc([int[]]$roots) {
  $cim=@(Get-CimInstance Win32_Process)
  $set=New-Object 'System.Collections.Generic.HashSet[int]'; foreach($r in $roots){[void]$set.Add($r)}
  $changed=$true
  while ($changed) { $changed=$false; foreach ($c in $cim) { if ($set.Contains([int]$c.ParentProcessId) -and -not $set.Contains([int]$c.ProcessId)) { [void]$set.Add([int]$c.ProcessId); $changed=$true } } }
  foreach ($c in $cim) { if ($set.Contains([int]$c.ProcessId)) { $script:seen[[int]$c.ProcessId]=("{0} {1}" -f $c.Name,[string]$c.CommandLine) } }
  return $set
}
$t0=Get-Date; $ports=0
while (@($procs.Values | Where-Object { -not $_.HasExited }).Count -gt 0) {
  $set = Desc @($procs.Values | ForEach-Object { $_.Id })
  $el=[int]((Get-Date)-$t0).TotalSeconds
  Write-Output "TICK t=${el}s alive=$(@($procs.Values | Where-Object { -not $_.HasExited }).Count) tree=$($set.Count)"
  if (($el -ge 60 -and $ports -eq 0) -or ($el -ge 300 -and $ports -eq 1)) {
    $ports++
    Write-Output "PORTS snapshot $ports at t=${el}s"
    Get-NetUDPEndpoint | Where-Object { $_.LocalPort -eq 45123 -or $set.Contains([int]$_.OwningProcess) } | Sort-Object LocalPort | ForEach-Object { Write-Output ("  UDP {0}:{1} pid={2} {3}" -f $_.LocalAddress,$_.LocalPort,$_.OwningProcess,(Get-Process -Id $_.OwningProcess).ProcessName) }
    Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -eq 7723 -or $set.Contains([int]$_.OwningProcess) } | Sort-Object LocalPort | ForEach-Object { Write-Output ("  TCP {0}:{1} pid={2} {3}" -f $_.LocalAddress,$_.LocalPort,$_.OwningProcess,(Get-Process -Id $_.OwningProcess).ProcessName) }
  }
  Start-Sleep -Seconds 20
}
$bad=0
foreach ($n in $names) { $p=$procs[$n]; $p.WaitForExit(); Write-Output "EXIT $n code=$($p.ExitCode)"; Get-Content -LiteralPath "$res\$n.stdout" | ForEach-Object { Write-Output "  OUT $_" }; Get-Content -LiteralPath "$res\$n.stderr" -Tail 5 | ForEach-Object { Write-Output "  ERR $_" } }
foreach ($k in @($seen.Keys | Sort-Object)) { $g=@(Get-Process -Id $k -ErrorAction SilentlyContinue); if ($g.Count) { $bad++ }; Write-Output ("GONE pid={0} gone={1} :: {2}" -f $k,($g.Count -eq 0),$seen[$k].Substring(0,[Math]::Min(160,$seen[$k].Length))) }
$left=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') })
Write-Output "PYTHON_LEFT $($left.Count)"; foreach ($l in $left) { Write-Output "  PY $($l.ProcessId) $($l.ExecutablePath) $($l.CommandLine)"; $bad++ }
Write-Output "SEEN_PIDS $($seen.Count) ALIVE_AFTER $bad"
if ($bad) { exit 9 }
exit 0
