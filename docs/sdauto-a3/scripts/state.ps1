# sdauto A3: READ-ONLY state: laptop time, clone HEAD/porcelain, browsers, installed tray pids, lane-path python.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
Write-Output "NOW $((Get-Date).ToString('yyyy-MM-ddTHH:mm:ss.fffzzz'))"
Write-Output "CLONE_HEAD $(& git --no-optional-locks -C $clone rev-parse HEAD)"
Write-Output "CLONE_PORCELAIN_LINES $(@(& git --no-optional-locks -C $clone status --porcelain).Count)"
Write-Output "LOGICAL_CORES $([Environment]::ProcessorCount)"
foreach ($p in @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('chrome.exe','msedge.exe','firefox.exe') } | Sort-Object ProcessId)) {
  Write-Output ("BROWSER {0} {1} session={2} created={3} ppid={4}" -f $p.ProcessId, $p.Name, $p.SessionId, ([datetime]$p.CreationDate).ToString('yyyy-MM-ddTHH:mm:ss'), $p.ParentProcessId)
}
foreach ($p in @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'STEAMDECK-MIDI-RECEIVER-2*' -or $_.Name -in @('python.exe','pythonw.exe') } | Sort-Object ProcessId)) {
  Write-Output ("PROC {0} {1} session={2} ppid={3} exe={4}" -f $p.ProcessId, $p.Name, $p.SessionId, $p.ParentProcessId, $p.ExecutablePath)
}
exit 0
