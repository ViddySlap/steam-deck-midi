$ErrorActionPreference='Stop'
$wg='C:\Users\Ben\AppData\Local\Temp\sdwin\wg'
$src=Join-Path $wg 'step0-snapshot.json'; $dst=Join-Path $wg 'mutant-baseline-traypid.json'
$j = [IO.File]::ReadAllText($src) | ConvertFrom-Json
$row = @($j.protectedProcesses | Where-Object { $_.pid -eq 23640 })
if ($row.Count -ne 1) { Write-Output "tray pid 23640 row count $($row.Count)"; exit 2 }
$row[0].pid = 23641
[IO.File]::WriteAllText($dst, ($j | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding($false)))
Write-Output "mutant written: protectedProcesses pid 23640 -> 23641; src sha=$((Get-FileHash $src).Hash.Substring(0,12)) dst sha=$((Get-FileHash $dst).Hash.Substring(0,12))"
exit 0
