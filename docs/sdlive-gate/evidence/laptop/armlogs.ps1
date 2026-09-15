$ErrorActionPreference='Continue'
$work='C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate'
foreach ($d in @(Get-ChildItem -LiteralPath $work -Directory -Recurse -Filter 'r1-*-try1')) {
  Write-Output "===== $($d.FullName)"
  foreach ($f in @('bridge.log','client.log')) { $x=Join-Path $d.FullName $f; if (Test-Path $x) { Write-Output "--- $f ($((Get-Item $x).Length) bytes)"; Get-Content $x -Tail 40 } }
}
exit 0
