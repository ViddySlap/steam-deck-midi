Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$python='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\.venv\Scripts\python.exe'
$arguments='-B "'+(Join-Path $PSScriptRoot 'clock-probe.py')+'"'
$child=Start-Process -FilePath $python -ArgumentList $arguments -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'clock-probe.json') -RedirectStandardError (Join-Path $PSScriptRoot 'clock-probe.stderr.txt')
$null=$child.Handle
$child.WaitForExit()
if ($child.ExitCode -ne 0) { throw 'Clock probe failed' }
$result=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'clock-probe.json')) | ConvertFrom-Json
foreach ($childId in @($child.Id,$result.pid)) { if (Get-Process -Id $childId -ErrorAction SilentlyContinue) { throw "Clock PID still alive $childId" }; Write-Output "GONE clock PID $childId" }
$result.monotonic | ConvertTo-Json -Compress
$result.perf_counter | ConvertTo-Json -Compress
