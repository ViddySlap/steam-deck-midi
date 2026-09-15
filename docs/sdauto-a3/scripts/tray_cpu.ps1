# sdauto A3: READ-ONLY CPU-time sample of the RUNNING installed v0.4.9 tray. No signal, no attach, no debugger.
param([int]$Seconds=60)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$install='C:\Program Files\STEAMDECK MIDI Receiver 2\'
$cores=[Environment]::ProcessorCount
$procs=@(Get-Process -Name 'STEAMDECK-MIDI-RECEIVER-2*' | Sort-Object Id)
if ($procs.Count -eq 0) { Write-Output 'NO_TRAY_PROCESS'; exit 2 }
$before=@{}
foreach ($p in $procs) {
  if (-not $p.Path -or -not $p.Path.StartsWith($install, [StringComparison]::OrdinalIgnoreCase)) { Write-Output "SKIP $($p.Id) path=$($p.Path)"; continue }
  $before[$p.Id]=$p.TotalProcessorTime.TotalSeconds
  Write-Output ("BEFORE {0} {1} session={2} start={3} cpu_s={4}" -f $p.Id, $p.ProcessName, $p.SessionId, $p.StartTime.ToString('s'), $before[$p.Id])
}
$sw=[Diagnostics.Stopwatch]::StartNew()
Start-Sleep -Seconds $Seconds
$el=$sw.Elapsed.TotalSeconds
$sum=0.0
foreach ($id in @($before.Keys | Sort-Object)) {
  $p=Get-Process -Id $id -ErrorAction SilentlyContinue
  if (-not $p) { Write-Output "GONE_DURING_SAMPLE $id"; continue }
  $d=$p.TotalProcessorTime.TotalSeconds - $before[$id]
  $sum+=$d
  Write-Output ("AFTER {0} cpu_s={1} delta_s={2:N4} pct_one_core={3:N3} pct_all_cores={4:N4}" -f $id, $p.TotalProcessorTime.TotalSeconds, $d, (100*$d/$el), (100*$d/$el/$cores))
}
Write-Output ("TOTAL elapsed_s={0:N3} logical_cores={1} delta_s={2:N4} pct_one_core={3:N3} pct_all_cores={4:N4}" -f $el, $cores, $sum, (100*$sum/$el), (100*$sum/$el/$cores))
exit 0
