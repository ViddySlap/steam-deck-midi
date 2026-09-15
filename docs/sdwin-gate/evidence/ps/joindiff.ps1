$ErrorActionPreference='Continue'
$orphan='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
foreach ($path in @('config/engines.factory/osc_sync.json','windows/engines/osc_sync.py','windows/engines/stageflow_bridge.py')) {
  $a = (& cmd.exe /c "git --no-optional-locks -C `"$orphan`" show d136787:$path") ; $ea=$LASTEXITCODE
  $b = (& cmd.exe /c "git -C `"$clone`" show e66ff44:$path"); $eb=$LASTEXITCODE
  $diffIdx=@(); for ($i=0; $i -lt [Math]::Max($a.Count,$b.Count); $i++) { if ($a[$i] -cne $b[$i]) { $diffIdx += $i } }
  $subst = @($a | ForEach-Object { $_.Replace('C:/Users/Ben/','C:/Users/USERNAME/').Replace('C:\\Users\\Ben\\','C:\\Users\\USERNAME\\') })
  $eq = ($subst.Count -eq $b.Count); if ($eq) { for ($i=0; $i -lt $b.Count; $i++) { if ($subst[$i] -cne $b[$i]) { $eq=$false } } }
  $lines = ($diffIdx | ForEach-Object { $_+1 }) -join ','
  $shape = ($diffIdx | ForEach-Object { ($b[$_] -replace '"[^"]*USERNAME[^"]*"','"<C:/Users/USERNAME/...>"' -replace "'[^']*USERNAME[^']*'","'<C:/Users/USERNAME/...>'").Trim() }) -join ' || '
  Write-Output ("{0}: show exits {1}/{2}; lines {3}/{4}; differing line numbers [{5}]; orphan-with-Ben->USERNAME equals tag: {6}; tag side shape: {7}" -f $path,$ea,$eb,$a.Count,$b.Count,$lines,$eq,$shape)
}
exit 0
