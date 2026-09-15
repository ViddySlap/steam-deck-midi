$ErrorActionPreference='Continue'
$work='C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate'
foreach ($d in @(Get-ChildItem -LiteralPath $work -Directory -Recurse -Filter 'r1-*-try1')) {
  Write-Output "===== $($d.FullName)"
  $x=Join-Path $d.FullName 'bridge.log'
  Select-String -LiteralPath $x -Pattern 'GET |POST |HTTP/1|UI server|listening|Running on|clients' | Select-Object -First 30 | ForEach-Object { Write-Output ("L{0}: {1}" -f $_.LineNumber, $_.Line) }
  Get-Content $x -TotalCount 25 | ForEach-Object { Write-Output "HEAD: $_" }
  Write-Output ("TRACEBACK_COUNT " + (Select-String -LiteralPath $x -Pattern 'engine_registry.on_axis_event failed' | Measure-Object).Count)
  Get-ChildItem -LiteralPath $d.FullName | ForEach-Object { Write-Output "FILE $($_.Name) $($_.Length) $($_.LastWriteTime.ToString('HH:mm:ss.fff'))" }
}
exit 0
