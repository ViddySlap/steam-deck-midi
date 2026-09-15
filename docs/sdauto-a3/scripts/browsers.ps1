# sdauto A3: READ-ONLY browser listing (BROWSER CLASS RULE b).
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
Write-Output "NOW $((Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz'))"
$b=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('chrome.exe','msedge.exe','firefox.exe') } | Sort-Object ProcessId)
Write-Output "BROWSER_PROCESSES $($b.Count)"
foreach ($p in $b) { Write-Output ("BROWSER {0} {1} session={2} created={3}" -f $p.ProcessId, $p.Name, $p.SessionId, ([datetime]$p.CreationDate).ToString('yyyy-MM-ddTHH:mm:ss')) }
$py=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') })
Write-Output "PYTHON_PROCESSES $($py.Count)"
exit 0
