param([string]$Label='suite', [switch]$Verbose)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
Set-Location -LiteralPath $clone
$env:PYSTRAY_BACKEND='dummy'
$env:BROWSER='C:/Windows/System32/cmd.exe /c rem %s'
$env:TEMP=$PSScriptRoot; $env:TMP=$PSScriptRoot
$python=Join-Path $clone '.venv\Scripts\python.exe'
$arguments='-m unittest discover -s tests -p "test_*.py"'
if ($Verbose) { $arguments='-m unittest discover -v -s tests -p "test_*.py"' }
Write-Output "HEAD $(& git -C $clone rev-parse HEAD)"
Write-Output "SUITE $python $arguments"
$out=Join-Path $PSScriptRoot "$Label.stdout.log"; $err=Join-Path $PSScriptRoot "$Label.stderr.log"
$child=Start-Process -FilePath $python -ArgumentList $arguments -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
$null=$child.Handle
$cid=$child.Id
Write-Output "LAUNCHER_PID $cid"
$seen=@{}
while (-not $child.HasExited) {
  foreach ($p in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$cid")) { $seen[[int]$p.ProcessId]=[string]$p.ExecutablePath }
  Start-Sleep -Milliseconds 500
}
$child.WaitForExit(); $code=$child.ExitCode
Get-Content -LiteralPath $err | Select-String -Pattern '^(Ran \d+ tests|OK|FAILED)' | ForEach-Object { Write-Output "SUMMARY $($_.Line)" }
if ($Verbose) { Get-Content -LiteralPath $err | Select-String -Pattern "skipped '" | ForEach-Object { Write-Output "SKIP $($_.Line)" } }
Get-Content -LiteralPath $err -Tail 3 | ForEach-Object { Write-Output "TAIL $_" }
$ids=@($cid)+@($seen.Keys)
foreach ($i in $ids) { $g=@(Get-Process -Id $i -ErrorAction SilentlyContinue); Write-Output ("PID {0} {1} gone={2}" -f $i, $(if($seen.ContainsKey($i)){'child '+$seen[$i]}else{'launcher'}), ($g.Count -eq 0)); if ($g.Count) { throw "pid alive $i" } }
$leak=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') })
Write-Output "PYTHON_PROCESSES_AFTER $($leak.Count)"
foreach ($l in $leak) { Write-Output "PY $($l.ProcessId) $($l.ExecutablePath) $($l.CommandLine)" }
Write-Output "EXIT $code"
exit $code
