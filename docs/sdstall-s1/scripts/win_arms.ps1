# sdstall S1 item d, step 2: the CLOSED-arm BASE/HEAD interleave on the laptop.
# DIAGNOSTIC. Never touches the installed tray, loopMIDI, Resolume, the orphan
# checkout or the clone's working tree. The clone is used READ-ONLY, for its venv
# interpreter and its pinned scripts/showready kit only.
param(
  [Parameter(Mandatory=$true)][string]$Work,
  [Parameter(Mandatory=$true)][int]$Target,
  [Parameter(Mandatory=$true)][int]$MaxArms
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$clone  = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$python = Join-Path $clone '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'clone venv python missing' }
$env:SDSTALL_KIT_ROOT = $clone
$env:PYSTRAY_BACKEND  = 'dummy'
# The no-op BROWSER proved to return 0 on this laptop (commit 51b1d5b). timing_ab
# sets the same value in each arm's own env; this is the outer belt.
$env:BROWSER = ('"' + ($python -replace '\\','/') + '" -c pass %s')
$env:TMP = $Work
$env:TEMP = $Work
$pidFile = Join-Path $Work 'python-pids.txt'
$log     = Join-Path $Work 'arms.log'
function Note([string]$m) { $line = ((Get-Date).ToString('s') + ' ' + $m); Write-Output $line; Add-Content -Encoding ascii -Path $log -Value $line }

function Invoke-TrackedPython([string[]]$PythonArgs) {
  $quoted = $PythonArgs | ForEach-Object { '"' + $_ + '"' }
  $child = Start-Process -FilePath $python -ArgumentList $quoted -PassThru -NoNewWindow
  $child.Id | Add-Content -Encoding ascii -Path $pidFile
  $null = $child.Handle
  $child.WaitForExit()
  $code = $child.ExitCode
  if (Get-Process -Id $child.Id -ErrorAction SilentlyContinue) { throw "Python PID $($child.Id) still exists" }
  return $code
}

$BASE = '70cebd0b6baed2ece86a2d218843e02b6298789d'
$HEAD = 'e2919763fe9174fe0fe44e2782f4279895cf0434'
$ok    = @{ base = 0; head = 0 }
$tried = @{ base = 0; head = 0 }
$n = 0
Note ("ARMS START target=$Target maxarms=$MaxArms work=$Work")
while (($ok['base'] -lt $Target) -or ($ok['head'] -lt $Target)) {
  foreach ($rev in @('base','head')) {
    if ($ok[$rev] -ge $Target) { continue }
    if ($tried[$rev] -ge $MaxArms) { continue }
    $n++; $tried[$rev] = $tried[$rev] + 1
    if ($rev -eq 'base') { $sha = $BASE } else { $sha = $HEAD }
    $label = ('win-a{0:d2}-{1}' -f $n, $rev)
    # ONE scratch and ONE candidate tree per REVISION, reused by all of its arms
    # through --work, exactly as the Mac session does: copying a 1,356 / 1,612
    # file tree before every arm is avoidable I/O during a timing measurement.
    $scratch = Join-Path $Work ('scratch-' + $rev)
    $workdir = Join-Path $scratch ('timing-' + $rev)
    $outf    = Join-Path $Work ($label + '.json.gz')
    Note ("ARM $n rev=$rev label=$label")
    $args = @('-B', (Join-Path $Work 'closed_only.py'),
              '--candidate', $sha,
              '--tree-from', (Join-Path $Work $rev),
              '--script',   (Join-Path $clone 'scripts\showready\timing_script.json'),
              '--fixtures', (Join-Path $Work 'fixtures'),
              '--preset',   (Join-Path $Work 'fixtures\mac\presets\EDM Show.json'),
              '--scratch',  $scratch,
              '--work',     $workdir,
              '--out',      $outf,
              '--valid-target', '1', '--max-arms', '1', '--first-repeat', "$n")
    $code = Invoke-TrackedPython $args
    Note ("ARM $n exit $code")
    if ($code -eq 0) { $ok[$rev] = $ok[$rev] + 1 }
    Note ("COUNT base=$($ok['base'])/$Target head=$($ok['head'])/$Target tried base=$($tried['base']) head=$($tried['head'])")
  }
  if (($tried['base'] -ge $MaxArms) -and ($tried['head'] -ge $MaxArms)) { Note 'MAX ARMS reached'; break }
}
Note ("ARMS END base=$($ok['base']) head=$($ok['head'])")
Write-Output 'ARMS_DONE'
