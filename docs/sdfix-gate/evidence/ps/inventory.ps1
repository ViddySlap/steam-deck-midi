Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work='C:\Users\Ben\AppData\Local\Temp\sdwin'
$self=$PID
$all=@(Get-CimInstance Win32_Process)
$hits=0
foreach ($p in $all) {
  if ($p.ProcessId -eq $self) { continue }
  $cl=[string]$p.CommandLine; $ep=[string]$p.ExecutablePath
  if (($cl -like "*sdwin*") -or ($cl -like "*steam-deck-midi-rc*") -or ($ep -like "$clone\*") -or ($ep -like "$work\*")) { $hits++; Write-Output ("MATCH pid={0} ppid={1} name={2} exe={3} cmd={4}" -f $p.ProcessId,$p.ParentProcessId,$p.Name,$ep,$cl) }
}
$py=@($all | Where-Object { $_.Name -in @('python.exe','pythonw.exe') })
Write-Output "SELF $self MATCHING $hits PYTHON_MACHINE_WIDE $($py.Count)"
foreach ($l in $py) { Write-Output "PY $($l.ProcessId) $($l.ExecutablePath) $($l.CommandLine)" }
Get-ChildItem -LiteralPath (Join-Path $work 'ug\results') -ErrorAction SilentlyContinue | ForEach-Object { Write-Output ("RESULT {0} {1}" -f $_.Name,$_.Length) }
exit 0
