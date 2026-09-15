# Bar 1 on the laptop: three concurrent ab_run arms-sets (script clock), Windows-installed fixtures.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work='C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate'
$fx='C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures'
$python=Join-Path $clone '.venv\Scripts\python.exe'
$env:PYSTRAY_BACKEND='dummy'; $env:BROWSER=((Join-Path $clone '.venv\Scripts\python.exe') -replace '\\','/') + ' -c pass %s'; $env:TEMP=$work; $env:TMP=$work
Set-Location -LiteralPath $clone
$head=(& git -C $clone rev-parse HEAD)
Write-Output "HEAD $head"
$jobs=@()
foreach ($p in @(@('win-edm','EDM Show.json'),@('win-ptz','PTZ.json'),@('win-default','default.json'))) {
  $name=$p[0]; $preset="$fx\windows-installed\presets\$($p[1])"
  $args='-B scripts/showready/ab_run.py --candidate ' + $head + ' --preset "' + $preset + '" --script "' + "$work\deck-script.json" + '" --fixtures "' + $fx + '" --scratch "' + "$work\ab-$name" + '" --out "' + "$work\ab-$name.json" + '"'
  Write-Output "COMMAND $name $python $args"
  $c=Start-Process -FilePath $python -ArgumentList $args -NoNewWindow -PassThru -RedirectStandardOutput "$work\ab-$name.stdout.log" -RedirectStandardError "$work\ab-$name.stderr.log"
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
Start-Sleep -Seconds 2
foreach ($id in @($jobs | ForEach-Object { $_[1].Id }) + @($seen.Keys)) { $g=@(Get-Process -Id $id -ErrorAction SilentlyContinue); Write-Output "PID $id gone=$($g.Count -eq 0)"; if ($g.Count) { throw "alive $id" } }
exit $bad
