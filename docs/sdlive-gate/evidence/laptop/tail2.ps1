$work='C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate\edge-sensitivity'
$d = Get-ChildItem -LiteralPath $work -Directory | Sort-Object LastWriteTime | Select-Object -Last 1
$x = Join-Path $d.FullName 'r1-OPEN-try1\bridge.log'
Get-Content $x -Tail 6
Select-String -LiteralPath $x -Pattern 'syntax of the command' | Measure-Object | ForEach-Object { "SYNTAX_LINES $($_.Count)" }
exit 0
