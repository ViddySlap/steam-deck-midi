$ErrorActionPreference='Continue'
foreach ($r in @('C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\.showready\fixtures','C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures')) {
  Write-Output "ROOT $r exists=$(Test-Path -LiteralPath $r)"
  if (Test-Path -LiteralPath $r) { Get-ChildItem -LiteralPath $r -Recurse -File | ForEach-Object { Write-Output "  $($_.FullName) $($_.Length) $((Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant())" } }
}
Get-ChildItem -LiteralPath 'C:\Users\Ben\AppData\Local\Temp\sdwin' -Directory | ForEach-Object { Write-Output "WORKDIR $($_.Name)" }
exit 0
