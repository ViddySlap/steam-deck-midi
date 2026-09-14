$ErrorActionPreference = 'Stop'
Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'STEAMDECK-MIDI-RECEIVER-2*' } | Select-Object ProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Depth 5
$paths = @('C:\Program Files\STEAMDECK MIDI Receiver 2\config', 'C:\Users\Ben\AppData\Local\STEAMDECK MIDI Receiver 2', 'C:\Users\Ben\AppData\Roaming\STEAMDECK MIDI Receiver 2', 'C:\Users\Ben\AppData\Local\VirtualStore\Program Files\STEAMDECK MIDI Receiver 2\config')
foreach ($path in $paths) {
    Write-Output "PATH $path EXISTS $(Test-Path -LiteralPath $path)"
    if (Test-Path -LiteralPath $path) { Get-ChildItem -LiteralPath $path -Force | Select-Object Name,Mode }
}
Write-Output "CLONE_EXISTS $(Test-Path -LiteralPath 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc')"
