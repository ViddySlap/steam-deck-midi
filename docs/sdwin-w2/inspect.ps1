Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*STEAMDECK*' } | Select-Object ProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Depth 5
Get-ChildItem -LiteralPath 'C:\Program Files\STEAMDECK MIDI Receiver 2' -Force | Select-Object Name,Mode | Format-Table
