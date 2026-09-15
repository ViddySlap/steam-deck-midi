# sdpick K1: stop ONE process this link started, only if every identity field matches; then prove it gone.
param([int]$TargetPid, [string]$Created, [string]$CmdNeedle)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Write-Output "NOW $(Get-Date -Format o) SELF $PID"
$p=@(Get-CimInstance Win32_Process -Filter "ProcessId=$TargetPid" -OperationTimeoutSec 30)
if ($p.Count -ne 1) { Write-Output "TARGET $TargetPid not present"; exit 0 }
$p=$p[0]; $cr=([datetime]$p.CreationDate).ToString('yyyy-MM-ddTHH:mm:ss')
Write-Output "TARGET pid=$($p.ProcessId) ppid=$($p.ParentProcessId) name=$($p.Name) si=$($p.SessionId) created=$cr cmd=$($p.CommandLine)"
$kids=@(Get-CimInstance Win32_Process -Filter "ParentProcessId=$TargetPid" -OperationTimeoutSec 30 | Where-Object { ([datetime]$_.CreationDate) -ge ([datetime]$p.CreationDate) })
foreach ($k in $kids) { Write-Output "CHILD pid=$($k.ProcessId) name=$($k.Name) si=$($k.SessionId) cmd=$($k.CommandLine)" }
$ok = ($p.Name -eq 'powershell.exe') -and ($p.SessionId -eq 0) -and ($cr -eq $Created) -and ([string]$p.CommandLine).ToLowerInvariant().Contains($CmdNeedle.ToLowerInvariant())
if (-not $ok) { Write-Output 'IDENTITY MISMATCH: not stopping'; exit 3 }
foreach ($k in $kids) { Stop-Process -Id ([int]$k.ProcessId) -Force; Write-Output "STOPPED child $($k.ProcessId)" }
Stop-Process -Id $TargetPid -Force
Write-Output "STOPPED $TargetPid"
Start-Sleep -Seconds 2
$bad=0
foreach ($i in @($TargetPid)+@($kids | ForEach-Object { [int]$_.ProcessId })) { $g=@(Get-Process -Id $i -ErrorAction SilentlyContinue); Write-Output "PID $i gone=$($g.Count -eq 0)"; if ($g.Count) { $bad++ } }
exit $bad
