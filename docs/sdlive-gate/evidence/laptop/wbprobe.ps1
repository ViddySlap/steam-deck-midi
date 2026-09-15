$ErrorActionPreference='Continue'
$python='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\.venv\Scripts\python.exe'
$out=Join-Path $PSScriptRoot 'wbprobe2.out.txt'; $err=Join-Path $PSScriptRoot 'wbprobe2.err.txt'
$child=Start-Process -FilePath $python -ArgumentList ('-B "' + (Join-Path $PSScriptRoot 'wbprobe2.py') + '"') -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
$null=$child.Handle; $child.WaitForExit()
Write-Output "EXIT $($child.ExitCode) PID $($child.Id)"
Get-Content $out; Get-Content $err
Start-Sleep -Seconds 1
Write-Output "PID_GONE $(@(Get-Process -Id $child.Id -ErrorAction SilentlyContinue).Count -eq 0)"
exit 0
