Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$base=Join-Path $PSScriptRoot 'base'
Copy-Item -LiteralPath (Join-Path $clone 'tests\test_deck_control_api.py') -Destination (Join-Path $base 'tests\test_deck_control_api.py')
Write-Output 'Copied only HEAD regression tests to the archived BASE; BASE deck source unchanged.'
Get-FileHash -LiteralPath (Join-Path $base 'deck\control_api.py') -Algorithm SHA256
exit 0
