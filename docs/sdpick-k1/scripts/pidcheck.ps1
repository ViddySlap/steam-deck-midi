# sdpick K1: READ-ONLY check of specific pids (Get-Process by id only).
param([string]$Ids)
$ErrorActionPreference='Continue'
Write-Output "NOW $(Get-Date -Format o) SELF $PID"
foreach ($i in ($Ids -split ' ')) { if (-not $i) { continue }; $g=@(Get-Process -Id ([int]$i) -ErrorAction SilentlyContinue); if ($g.Count) { Write-Output ("PID {0} ALIVE {1} si={2} start={3} cpu={4}" -f $i,$g[0].ProcessName,$g[0].SessionId,$g[0].StartTime.ToString('o'),[int]$g[0].CPU) } else { Write-Output "PID $i gone=True" } }
exit 0
