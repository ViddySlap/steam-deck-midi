param([Parameter(Mandatory=$true)][string]$Work)
$ErrorActionPreference='Stop'
Get-ChildItem -LiteralPath $Work -File -Filter 'win-a*.json.gz' | ForEach-Object {
  Write-Output ("RESULT " + $_.Name + " " + $_.Length)
}
foreach ($n in @('arms.log','python-pids.txt')) {
  $p = Join-Path $Work $n
  if (Test-Path -LiteralPath $p) { Write-Output ("RESULT " + $n + " " + (Get-Item -LiteralPath $p).Length) }
}
