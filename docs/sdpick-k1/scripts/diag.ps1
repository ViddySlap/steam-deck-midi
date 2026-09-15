# sdpick K1: READ-ONLY WMI diagnosis. SCM query (no WMI), then timed CIM queries, then directory listing.
$ErrorActionPreference='Continue'
Write-Output "NOW $(Get-Date -Format o) SELF $PID"
& sc.exe queryex winmgmt | ForEach-Object { Write-Output "SC $_" }
Get-Process -Name powershell,WmiPrvSE -ErrorAction SilentlyContinue | ForEach-Object { Write-Output ("PROC {0} {1} si={2} start={3} cpu={4}" -f $_.Id,$_.ProcessName,$_.SessionId,$_.StartTime.ToString('o'),[int]$_.CPU) }
$sw=[Diagnostics.Stopwatch]::StartNew()
try { $r=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'" -OperationTimeoutSec 20 -ErrorAction Stop); Write-Output "CIM_FILTERED ok count=$($r.Count) ms=$($sw.ElapsedMilliseconds)" } catch { Write-Output "CIM_FILTERED error ms=$($sw.ElapsedMilliseconds) $($_.Exception.Message)" }
$sw.Restart()
Get-ChildItem -LiteralPath 'C:\Users\Ben\AppData\Local\Temp\sdwin' -Directory | ForEach-Object { Write-Output "DIR $($_.Name)" }
Write-Output "DIRLIST ms=$($sw.ElapsedMilliseconds)"
exit 0
