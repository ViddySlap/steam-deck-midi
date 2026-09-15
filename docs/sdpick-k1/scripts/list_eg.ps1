# sdpick K1 (i): READ-ONLY listing of EG's laptop work directory top level (name, length, mtime, sha256 of results).
$ErrorActionPreference='Stop'
$d='C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate'
foreach ($f in @(Get-ChildItem -LiteralPath $d -File | Sort-Object Name)) {
  $h=''; if ($f.Name -match '\.(json|gz|log|txt)$') { $h=(Get-FileHash -Algorithm SHA256 -LiteralPath $f.FullName).Hash.ToLowerInvariant() }
  Write-Output ("FILE {0} {1} {2} {3}" -f $f.Name,$f.Length,$f.LastWriteTime.ToString('s'),$h)
}
foreach ($f in @(Get-ChildItem -LiteralPath $d -Directory | Sort-Object Name)) { Write-Output "DIR $($f.Name)" }
exit 0
