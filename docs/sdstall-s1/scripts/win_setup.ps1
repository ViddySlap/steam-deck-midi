# sdstall S1 item d, step 1: verify the railed payload and expand it.
# Nothing here touches the clone, the installed tray, loopMIDI or Resolume.
param(
  [Parameter(Mandatory=$true)][string]$Work,
  [Parameter(Mandatory=$true)][string]$BaseSha256,
  [Parameter(Mandatory=$true)][string]$HeadSha256,
  [Parameter(Mandatory=$true)][string]$FixturesSha256
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
function Sha([string]$p) { return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() }
$pairs = @(
  @{ name='base.zip';     expect=$BaseSha256 },
  @{ name='head.zip';     expect=$HeadSha256 },
  @{ name='fixtures.zip'; expect=$FixturesSha256 }
)
foreach ($p in $pairs) {
  $path = Join-Path $Work $p.name
  if (-not (Test-Path -LiteralPath $path)) { throw "missing $($p.name)" }
  $got = Sha $path
  Write-Output ("SHA256 " + $p.name + " " + $got + " bytes=" + (Get-Item -LiteralPath $path).Length)
  if ($got -ne $p.expect.ToLowerInvariant()) { throw "sha256 mismatch for $($p.name): got $got expected $($p.expect)" }
  Write-Output ("SHA256_MATCH " + $p.name)
}
foreach ($n in @('base','head','fixtures')) {
  $dst = Join-Path $Work $n
  if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }
  Expand-Archive -LiteralPath (Join-Path $Work "$n.zip") -DestinationPath $dst -Force
  $count = @(Get-ChildItem -LiteralPath $dst -Recurse -File -Force).Count
  Write-Output ("EXPANDED " + $n + " files=" + $count)
}
$preset = Join-Path $Work 'fixtures\mac\presets\EDM Show.json'
Write-Output ("PRESET_EXISTS=" + (Test-Path -LiteralPath $preset))
Write-Output ("BASE_WIN_RECV=" + (Test-Path -LiteralPath (Join-Path $Work 'base\windows\win_recv.py')))
Write-Output ("HEAD_WIN_RECV=" + (Test-Path -LiteralPath (Join-Path $Work 'head\windows\win_recv.py')))
Write-Output ("BASE_HAS_RECEIVER_TASKS=" + (Test-Path -LiteralPath (Join-Path $Work 'base\windows\receiver_tasks.py')))
Write-Output ("HEAD_HAS_RECEIVER_TASKS=" + (Test-Path -LiteralPath (Join-Path $Work 'head\windows\receiver_tasks.py')))
Write-Output 'SETUP_OK'
