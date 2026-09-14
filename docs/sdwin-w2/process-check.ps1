$ErrorActionPreference = 'Stop'
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*sdwin*w2*' -or $_.ExecutablePath -like '*steam-deck-midi-rc*' } | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Depth 3
Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*arms*' | Select-Object Name,Length,LastWriteTime | Format-Table
