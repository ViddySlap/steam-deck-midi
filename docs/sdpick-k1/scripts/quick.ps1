# sdpick K1: READ-ONLY quick look (Get-Process only, no CIM): top CPU and names of interest.
$ErrorActionPreference='Continue'
Write-Output "NOW $(Get-Date -Format o) SELF $PID"
Get-Process | Sort-Object CPU -Descending | Select-Object -First 15 | ForEach-Object { Write-Output ("TOP {0} {1} cpu={2} ws={3}MB si={4} start={5}" -f $_.Id,$_.ProcessName,[int]$_.CPU,[int]($_.WorkingSet64/1MB),$_.SessionId,$(try{$_.StartTime.ToString('s')}catch{'?'})) }
Get-Process -Name python,pythonw,powershell,pwsh,node,msedge,chrome,firefox,WmiPrvSE -ErrorAction SilentlyContinue | ForEach-Object { Write-Output ("NAMED {0} {1} si={2} start={3} path={4}" -f $_.Id,$_.ProcessName,$_.SessionId,$(try{$_.StartTime.ToString('s')}catch{'?'}),$(try{$_.Path}catch{'?'})) }
exit 0
