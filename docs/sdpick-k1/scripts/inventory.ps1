# sdpick K1: READ-ONLY inventory. Browsers + lane-relevant processes with SessionId, parent, times, paths, command lines,
# plus EG's recorded pid evidence files. Writes only its JSON output under LAPTOP WORK\sdpick-k1.
param([string]$Label='inv')
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$work='C:\Users\Ben\AppData\Local\Temp\sdwin'
$me=$PID
$names=@('chrome.exe','msedge.exe','firefox.exe','python.exe','pythonw.exe','powershell.exe','pwsh.exe','node.exe')
$procs=@(Get-CimInstance Win32_Process | Where-Object { $names -contains $_.Name } | Sort-Object ProcessId | ForEach-Object {
  [ordered]@{ pid=[int]$_.ProcessId; ppid=[int]$_.ParentProcessId; name=[string]$_.Name; session=[int]$_.SessionId;
    created=$(if ($_.CreationDate) { ([datetime]$_.CreationDate).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz') } else { '' });
    exe=[string]$_.ExecutablePath; cmd=[string]$_.CommandLine }
})
# Parent chain helper data: every process's pid/ppid/name/session (no command lines) so the Mac can walk chains.
$all=@(Get-CimInstance Win32_Process | Sort-Object ProcessId | ForEach-Object {
  [ordered]@{ pid=[int]$_.ProcessId; ppid=[int]$_.ParentProcessId; name=[string]$_.Name; session=[int]$_.SessionId;
    created=$(if ($_.CreationDate) { ([datetime]$_.CreationDate).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz') } else { '' }) }
})
$records=[ordered]@{}
foreach ($d in @(Get-ChildItem -LiteralPath $work -Directory -ErrorAction Stop)) {
  foreach ($f in @(Get-ChildItem -LiteralPath $d.FullName -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'owned-tree-*.txt' -or $_.Name -eq 'python-pids.txt' })) {
    $records[[string]$f.FullName]=[string[]]@(Get-Content -LiteralPath $f.FullName | ForEach-Object { [string]$_ })
  }
}
$out=[ordered]@{ label=$Label; taken=(Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz'); self_pid=$me; processes=$procs; all=$all; records=$records }
$json=ConvertTo-Json -InputObject $out -Depth 4 -Compress
$path=Join-Path (Join-Path $work 'sdpick-k1') "inventory-$Label.json"
[IO.File]::WriteAllText($path,$json,(New-Object Text.UTF8Encoding($false)))
Write-Output "INVENTORY_FILE $path"
Write-Output "SELF_PID $me"
Write-Output "PROCESSES $($procs.Count) ALL $($all.Count) RECORD_FILES $($records.Count)"
exit 0
