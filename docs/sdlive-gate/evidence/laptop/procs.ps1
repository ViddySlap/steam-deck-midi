$ErrorActionPreference='Continue'
$work='C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate'
foreach ($p in @(Get-CimInstance Win32_Process -Filter "Name='msedge.exe' OR Name='node.exe' OR Name='python.exe' OR Name='pythonw.exe'")) {
  $cl = [string]$p.CommandLine; if ($cl.Length -gt 260) { $cl = $cl.Substring(0,260) }
  Write-Output "PROC $($p.ProcessId) parent=$($p.ParentProcessId) $($p.Name) start=$($p.CreationDate) $cl"
}
foreach ($f in @('owned-tree-sensitivity.txt','owned-tree-clean.txt','python-pids.txt')) { $x=Join-Path $work $f; if (Test-Path $x) { Write-Output "== $f"; Get-Content $x } }
foreach ($c in @(Get-NetTCPConnection -State Established,SynSent -ErrorAction SilentlyContinue | Where-Object { $_.RemoteAddress -eq '127.0.0.1' -and $_.RemotePort -ne 7723 })) { Write-Output "TCP $($c.LocalPort)->$($c.RemotePort) $($c.State) pid=$($c.OwningProcess)" }
exit 0
