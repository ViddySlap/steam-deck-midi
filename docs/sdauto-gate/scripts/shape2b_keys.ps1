# sdauto gate 2b: READ-ONLY key names (no values except protocol-like strings) of the installed user audio_opacity.json.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$f='C:\Program Files\STEAMDECK MIDI Receiver 2\config\engines\audio_opacity.json'
$j=Get-Content -LiteralPath $f -Raw | ConvertFrom-Json
Write-Output ("TOP_KEYS " + (($j.PSObject.Properties.Name) -join ','))
foreach ($k in @('outputs','output')) { if ($j.PSObject.Properties.Name -contains $k) { Write-Output ("$k KEYS " + (($j.$k.PSObject.Properties.Name) -join ',')); foreach ($n in $j.$k.PSObject.Properties.Name) { $v=$j.$k.$n; if ($v -is [string]) { Write-Output "$k.$n = $v" } } } }
Write-Output ("type = " + [string]$j.type)
exit 0
