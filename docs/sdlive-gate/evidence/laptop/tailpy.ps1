$d = Get-ChildItem -LiteralPath 'C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate\python-sensitivity' -Directory | Sort-Object LastWriteTime | Select-Object -Last 1
Get-Content (Join-Path $d.FullName 'r1-OPEN-try1\bridge.log') -Tail 2
exit 0
