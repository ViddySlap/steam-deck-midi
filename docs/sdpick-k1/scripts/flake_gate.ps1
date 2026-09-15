# 6b: 300 in-process runs of the flaky test at HEAD (clone) and at the pre-fix BASE (archive under work).
param([ValidateSet('head','base')][string]$Which)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work='C:\Users\Ben\AppData\Local\Temp\sdwin\sdpick-k1'
$python=Join-Path $clone '.venv\Scripts\python.exe'
$env:PYSTRAY_BACKEND='dummy'; $env:BROWSER=((Join-Path $clone '.venv\Scripts\python.exe') -replace '\\','/') + ' -c pass %s'; $env:TEMP=$work; $env:TMP=$work
$repeat=Join-Path $clone 'docs\sdlive-e0\scripts\repeat.py'
if ($Which -eq 'base') {
  $root=Join-Path $work 'e0-base'
  if (-not (Test-Path $root)) {
    New-Item -ItemType Directory -Path $root | Out-Null
    git -C $clone archive --format=tar --output="$work\e0-base.tar" 14aa21824843dbe148dc3ac3d0bf58929ef34c3a
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    tar -xf "$work\e0-base.tar" -C $root
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }
  $expected='red'
} else { $root=$clone; $expected='green' }
$outjson=Join-Path $work "flake-$Which.json"
$argline='-B "' + $repeat + '" "' + $root + '" 300 test_malformed_json_and_unsupported_method_are_json ' + $expected + ' "' + $outjson + '"'
Write-Output "ROOT $root"
Write-Output "COMMAND $python $argline"
$c=Start-Process -FilePath $python -ArgumentList $argline -WorkingDirectory $root -NoNewWindow -PassThru -RedirectStandardOutput "$work\flake-$Which.stdout.log" -RedirectStandardError "$work\flake-$Which.stderr.log"
$null=$c.Handle; $seen=@{}
while (-not $c.HasExited) { foreach ($p in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($c.Id)")) { $seen[[int]$p.ProcessId]=1 }; Start-Sleep -Milliseconds 500 }
$c.WaitForExit(); $code=$c.ExitCode
Get-Content "$work\flake-$Which.stdout.log" | ForEach-Object { Write-Output "OUT $_" }
Get-Content "$work\flake-$Which.stderr.log" -Tail 3 | ForEach-Object { Write-Output "ERR $_" }
Start-Sleep -Seconds 1
foreach ($i in @($c.Id)+@($seen.Keys)) { $g=@(Get-Process -Id $i -ErrorAction SilentlyContinue); Write-Output "PID $i gone=$($g.Count -eq 0)"; if ($g.Count) { throw "alive $i" } }
Write-Output "EXIT $code (repeat.py: 0 means the expected $expected outcome was observed)"
exit $code
