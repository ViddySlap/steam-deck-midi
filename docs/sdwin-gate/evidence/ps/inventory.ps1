Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work='C:\Users\Ben\AppData\Local\Temp\sdwin'
$self=$PID
$w4pids=@(266512,262176,278440,250436,277756,267656,233432,272232,274080,251680,275832,274184,278016,262056,254412)
$all=@(Get-CimInstance Win32_Process)
$rows=@()
foreach ($p in $all) {
  if ($p.ProcessId -eq $self) { continue }
  $cl=[string]$p.CommandLine; $ep=[string]$p.ExecutablePath
  $hit = ($cl -like "*sdwin*") -or ($cl -like "*steam-deck-midi-rc*") -or ($ep -like "$clone\*") -or ($ep -like "$work\*") -or ($w4pids -contains [int]$p.ProcessId)
  if ($hit) { $rows += [ordered]@{pid=$p.ProcessId; ppid=$p.ParentProcessId; name=$p.Name; exe=$ep; created=[string]$p.CreationDate; cmd=$cl} }
}
$py=@($all | Where-Object { $_.Name -in @('python.exe','pythonw.exe') } | ForEach-Object { [ordered]@{pid=$_.ProcessId; ppid=$_.ParentProcessId; exe=[string]$_.ExecutablePath; cmd=[string]$_.CommandLine} })
$w4live=@(foreach ($id in $w4pids) { $g=@(Get-Process -Id $id -ErrorAction SilentlyContinue); [ordered]@{pid=$id; alive=($g.Count -ne 0); name=$(if($g.Count){$g[0].ProcessName}else{''})} })
Write-Output "SELF PID $self"
Write-Output "== MATCHING (sdwin/clone/W4 pid) processes: $($rows.Count)"
$rows | ConvertTo-Json -Depth 4
Write-Output "== ALL python/pythonw: $($py.Count)"
$py | ConvertTo-Json -Depth 4
Write-Output "== W4 recorded PIDs"
$w4live | ForEach-Object { "$($_.pid) alive=$($_.alive) $($_.name)" }
Write-Output "== W4 work top-level"
Write-Output "listing skipped"
exit 0
