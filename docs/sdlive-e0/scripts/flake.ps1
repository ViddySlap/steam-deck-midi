param([int]$N=300)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$env:PYSTRAY_BACKEND='dummy'; $env:BROWSER='C:/Windows/System32/cmd.exe /c rem %s'
$env:TEMP=$PSScriptRoot; $env:TMP=$PSScriptRoot
$python=Join-Path $clone '.venv\Scripts\python.exe'
$py=Join-Path $PSScriptRoot 'flake_rate.py'
$out=Join-Path $PSScriptRoot 'flake.stdout.log'; $err=Join-Path $PSScriptRoot 'flake.stderr.log'
Write-Output "HEAD $(& git -C $clone rev-parse HEAD)"
$child=Start-Process -FilePath $python -ArgumentList "-B `"$py`" $N" -WorkingDirectory $clone -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
$null=$child.Handle; $cid=$child.Id; Write-Output "LAUNCHER_PID $cid"
$seen=@{}
while (-not $child.HasExited) { foreach ($p in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$cid")) { $seen[[int]$p.ProcessId]=[string]$p.ExecutablePath }; Start-Sleep -Milliseconds 500 }
$child.WaitForExit(); $code=$child.ExitCode
Get-Content -LiteralPath $out | ForEach-Object { Write-Output "OUT $_" }
foreach ($i in @($cid)+@($seen.Keys)) { $g=@(Get-Process -Id $i -ErrorAction SilentlyContinue); Write-Output ("PID {0} gone={1}" -f $i, ($g.Count -eq 0)); if ($g.Count) { throw "pid alive $i" } }
$leak=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') })
Write-Output "PYTHON_PROCESSES_AFTER $($leak.Count)"
Write-Output "EXIT $code"
exit $code
