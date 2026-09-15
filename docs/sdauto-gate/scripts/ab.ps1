# sdauto gate: EG ab.ps1 via sdpick K1, re-pointed at sdwin\sdauto-gate; deck script, then Windows bar 1 EDM, PTZ, default; then engine_ab windows EDM and PTZ.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work='C:\Users\Ben\AppData\Local\Temp\sdwin\sdauto-gate'
$fx='C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures'
$python=Join-Path $clone '.venv\Scripts\python.exe'
$env:PYSTRAY_BACKEND='dummy'; $env:BROWSER=((Join-Path $clone '.venv\Scripts\python.exe') -replace '\\','/') + ' -c pass %s'; $env:TEMP=$work; $env:TMP=$work
Set-Location -LiteralPath $clone
$head=(& git -C $clone rev-parse HEAD)
Write-Output "HEAD $head"
$g=Start-Process -FilePath $python -ArgumentList ('-B scripts/showready/deck_script.py --fixtures "' + $fx + '" --out "' + "$work\deck-script.json" + '"') -NoNewWindow -PassThru -RedirectStandardOutput "$work\deck-script.stdout.log" -RedirectStandardError "$work\deck-script.stderr.log"
$null=$g.Handle; $g.WaitForExit(); Write-Output "DECK_SCRIPT EXIT $($g.ExitCode) PID $($g.Id)"; Get-Content "$work\deck-script.stdout.log" | ForEach-Object { Write-Output "DECK_SCRIPT_OUT $_" }
Start-Sleep -Milliseconds 500; if (@(Get-Process -Id $g.Id -ErrorAction SilentlyContinue).Count) { throw "alive $($g.Id)" }; Write-Output "PID $($g.Id) gone=True"
if ($g.ExitCode -ne 0) { exit 10 }
$jobs=@()
foreach ($p in @(@('win-edm','EDM Show.json'),@('win-ptz','PTZ.json'),@('win-default','default.json'))) {
  $name=$p[0]; $preset="$fx\windows-installed\presets\$($p[1])"
  $argline='-B scripts/showready/ab_run.py --candidate ' + $head + ' --preset "' + $preset + '" --script "' + "$work\deck-script.json" + '" --fixtures "' + $fx + '" --scratch "' + "$work\ab-$name" + '" --out "' + "$work\ab-$name.json" + '"'
  Write-Output "COMMAND $name $python $argline"
  $c=Start-Process -FilePath $python -ArgumentList $argline -NoNewWindow -PassThru -RedirectStandardOutput "$work\ab-$name.stdout.log" -RedirectStandardError "$work\ab-$name.stderr.log"
  $null=$c.Handle
  $jobs+=,@($name,$c)
}
$seen=@{}
while (@($jobs | Where-Object { -not $_[1].HasExited }).Count) {
  $procs=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'")
  $changed=$true
  while ($changed) { $changed=$false; foreach ($pr in $procs) { $id=[int]$pr.ProcessId; $pa=[int]$pr.ParentProcessId; if (-not $seen.ContainsKey($id) -and ($seen.ContainsKey($pa) -or @($jobs | Where-Object { $_[1].Id -eq $pa }).Count)) { $seen[$id]=$pa; $changed=$true } } }
  Start-Sleep -Seconds 3
}
$bad=0
foreach ($j in $jobs) { $j[1].WaitForExit(); Write-Output "EXIT $($j[0]) $($j[1].ExitCode) PID $($j[1].Id)"; Get-Content "$work\ab-$($j[0]).stdout.log" | Select-Object -Last 1 | ForEach-Object { Write-Output ("OUT {0} {1}" -f $j[0], $_.Substring(0,[Math]::Min(400,$_.Length))) }; if ($j[1].ExitCode -ne 0) { $bad++ } }
foreach ($p in @(@('eab-win-edm','EDM Show.json'),@('eab-win-ptz','PTZ.json'))) {
  $name=$p[0]; $preset="$fx\windows-installed\presets\$($p[1])"
  $argline='-B scripts/showready/engine_ab.py --candidate ' + $head + ' --preset "' + $preset + '" --fixtures "' + $fx + '" --scratch "' + "$work\$name" + '" --out "' + "$work\$name.json" + '"'
  Write-Output "COMMAND $name $python $argline"
  $c=Start-Process -FilePath $python -ArgumentList $argline -NoNewWindow -PassThru -RedirectStandardOutput "$work\$name.stdout.log" -RedirectStandardError "$work\$name.stderr.log"
  $null=$c.Handle
  while (-not $c.HasExited) { foreach ($pr in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($c.Id)")) { $seen[[int]$pr.ProcessId]=$c.Id }; Start-Sleep -Milliseconds 300 }
  $c.WaitForExit(); Write-Output "EXIT $name $($c.ExitCode) PID $($c.Id)"; Get-Content "$work\$name.stdout.log" | Select-Object -Last 1 | ForEach-Object { Write-Output ("OUT {0} {1}" -f $name, $_.Substring(0,[Math]::Min(400,$_.Length))) }; if ($c.ExitCode -ne 0) { $bad++ }
  $jobs+=,@($name,$c)
}
Start-Sleep -Seconds 2
foreach ($id in @($jobs | ForEach-Object { $_[1].Id }) + @($seen.Keys)) { $g=@(Get-Process -Id $id -ErrorAction SilentlyContinue); Write-Output "PID $id gone=$($g.Count -eq 0)"; if ($g.Count) { throw "alive $id" } }
exit $bad
