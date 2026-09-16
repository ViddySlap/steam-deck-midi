# sdstall S1 item d, step 3: prove every process this link started is gone, and
# classify what is running by the PROCESS-CLASS ORDER (MASTER 13, 10:48).
# READ-ONLY apart from stopping nothing: this script never stops any process.
param([Parameter(Mandatory=$true)][string]$Work)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$install = 'C:\Program Files\STEAMDECK MIDI Receiver 2\'
$clone   = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\'
$orphan  = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi\'
$sdwin   = 'C:\Users\Ben\AppData\Local\Temp\sdwin\'
$pidFile = Join-Path $Work 'python-pids.txt'
$recorded = @()
if (Test-Path -LiteralPath $pidFile) { $recorded = @(Get-Content -LiteralPath $pidFile | Where-Object { $_ -match '^\d+$' } | ForEach-Object { [int]$_ }) }
Write-Output ("RECORDED_PIDS=" + $recorded.Count)
$alive = @($recorded | Where-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue })
Write-Output ("RECORDED_PIDS_STILL_ALIVE=" + $alive.Count)
foreach ($p in $alive) { Write-Output ("STILL_ALIVE pid=$p") }

# Browser listing, session-aware (BROWSER CLASS RULE (b)).
$browsers = @(Get-CimInstance Win32_Process -Filter "Name='chrome.exe' OR Name='msedge.exe' OR Name='firefox.exe'" -ErrorAction SilentlyContinue)
Write-Output ("BROWSER_PROCESSES=" + $browsers.Count)
foreach ($b in $browsers) {
  Write-Output ("BROWSER pid=" + $b.ProcessId + " name=" + $b.Name + " session=" + $b.SessionId + " created=" + $b.CreationDate + " path=" + $b.ExecutablePath)
}

# Python inventory, classified IN ORDER: PROTECTED, RECORDED LANE PID, LANE PATH
# UNRECORDED, NOT LANE. Nothing is stopped here.
$py = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue)
Write-Output ("PYTHON_PROCESSES=" + $py.Count)
foreach ($p in $py) {
  $path = if ($p.ExecutablePath) { $p.ExecutablePath } else { '' }
  $cl   = if ($p.CommandLine) { $p.CommandLine } else { '' }
  $klass = 'NOT-LANE'
  if ($p.SessionId -eq 1 -or $path.StartsWith($install,'OrdinalIgnoreCase') -or $path.StartsWith($orphan,'OrdinalIgnoreCase') -or $cl -like "*$orphan*") {
    $klass = 'PROTECTED'
  } elseif ($recorded -contains $p.ProcessId) {
    $klass = 'RECORDED-LANE-PID'
  } elseif ($path.StartsWith($clone,'OrdinalIgnoreCase') -or $path.StartsWith($sdwin,'OrdinalIgnoreCase') -or $cl -like "*$sdwin*") {
    $klass = 'LANE-PATH-UNRECORDED'
  }
  Write-Output ("PYTHON class=$klass pid=" + $p.ProcessId + " session=" + $p.SessionId + " path=" + $path + " cmd=" + $cl.Substring(0, [Math]::Min(160, $cl.Length)))
}
$tray = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like 'STEAMDECK-MIDI-RECEIVER-2*' -or $_.ProcessName -eq 'loopMIDI' })
Write-Output ("PROTECTED_RUNNING=" + $tray.Count)
foreach ($t in $tray) { Write-Output ("PROTECTED name=" + $t.ProcessName + " pid=" + $t.Id) }
Write-Output 'TEARDOWN_REPORT_OK'
