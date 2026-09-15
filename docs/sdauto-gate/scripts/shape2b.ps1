# sdauto gate 2b: READ-ONLY shape check of the INSTALLED osc_sync osc_preset_path and audio_opacity protocol.
# Prints only booleans, depth and protocol values; never the username or the raw path.
param([string]$HeadSuffix)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$root='C:\Program Files\STEAMDECK MIDI Receiver 2\config'
foreach ($rel in @('engines.factory\osc_sync.json','engines\osc_sync.json')) {
  $f=Join-Path $root $rel
  if (-not (Test-Path -LiteralPath $f)) { Write-Output "OSC_SYNC $rel present=false"; continue }
  $j=Get-Content -LiteralPath $f -Raw | ConvertFrom-Json
  if (-not ($j.PSObject.Properties.Name -contains 'osc_preset_path')) { Write-Output "OSC_SYNC $rel present=true key=false"; continue }
  $p=([string]$j.osc_preset_path) -replace '\\','/'
  $m=[regex]::Match($p,'^[A-Za-z]:/Users/[^/]+/(.*)$')
  $suffix= if ($m.Success) { $m.Groups[1].Value } else { $null }
  $depth=@($p.Split('/') | Where-Object { $_ -ne '' }).Count
  $exists=Test-Path -LiteralPath ($p -replace '/','\')
  Write-Output ("OSC_SYNC {0} present=true key=true home_form={1} suffix equal: {2} depth={3} exists={4}" -f $rel, $m.Success, ([string]($suffix -ceq $HeadSuffix)).ToLowerInvariant(), $depth, $exists)
}
foreach ($rel in @('engines.factory\audio_opacity.json','engines\audio_opacity.json')) {
  $f=Join-Path $root $rel
  if (-not (Test-Path -LiteralPath $f)) { Write-Output "AUDIO_OPACITY $rel present=false"; continue }
  $j=Get-Content -LiteralPath $f -Raw | ConvertFrom-Json
  $proto= if ($j.PSObject.Properties.Name -contains 'protocol') { [string]$j.protocol } elseif ($j.PSObject.Properties.Name -contains 'outputs' -and $j.outputs.PSObject.Properties.Name -contains 'protocol') { 'outputs.' + [string]$j.outputs.protocol } else { '(absent)' }
  Write-Output "AUDIO_OPACITY $rel present=true protocol=$proto"
}
exit 0
