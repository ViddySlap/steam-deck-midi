param([ValidateSet('pins','sensitivity','clean','ctl10')][string]$Phase, [switch]$PythonClient)
# README "QUALIFYING commands: laptop with headless Edge" body, split by phase, plus owned PID-tree sampling.
$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work = 'C:\Users\Ben\AppData\Local\Temp\sdwin\sdlive-gate'
New-Item -ItemType Directory -Force -Path $work | Out-Null
$python = (Resolve-Path '.\.venv\Scripts\python.exe').Path
$env:PYSTRAY_BACKEND = 'dummy'
$env:BROWSER = ((Resolve-Path '.\.venv\Scripts\python.exe').Path -replace '\\','/') + ' -c pass %s'  # MASTER 02:58: no-op that really exits 0
$env:TMP = $work
$env:TEMP = $work
$env:PLAYWRIGHT_CORE = 'C:\Users\Ben\Documents\project-workspaces\life-os-tbex-chain\web-ui-server\node_modules\playwright-core'
$fixtures = 'C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures'
$owned = Join-Path $work ("owned-tree-$Phase.txt")
function Get-Tree([int]$Root, $seen) {
  $procs = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='node.exe' OR Name='msedge.exe' OR Name='powershell.exe'")
  $changed = $true
  while ($changed) {
    $changed = $false
    foreach ($p in $procs) {
      $id = [int]$p.ProcessId; $parent = [int]$p.ParentProcessId
      if (-not $seen.ContainsKey($id) -and ($parent -eq $Root -or $seen.ContainsKey($parent))) {
        $seen[$id] = "$($p.Name) parent=$parent start=$($p.CreationDate)"; $changed = $true
      }
    }
  }
}
function Invoke-TrackedPython([string[]]$PythonArgs) {
  $quoted = $PythonArgs | ForEach-Object { '"' + $_ + '"' }
  Write-Output ("COMMAND " + $python + " " + ($quoted -join ' '))
  $child = Start-Process -FilePath $python -ArgumentList $quoted -PassThru -NoNewWindow
  $child.Id | Add-Content -Encoding ascii -Path "$work\python-pids.txt"
  $null = $child.Handle
  $seen = @{}
  while (-not $child.HasExited) { Get-Tree $child.Id $seen; Start-Sleep -Seconds 2 }
  $child.WaitForExit()
  $code = $child.ExitCode
  if (Get-Process -Id $child.Id -ErrorAction SilentlyContinue) { throw 'Python PID still exists' }
  Start-Sleep -Seconds 2
  $alive = 0
  foreach ($k in $seen.Keys) {
    $g = @(Get-Process -Id $k -ErrorAction SilentlyContinue)
    "$($child.Id) $k $($seen[$k]) gone=$($g.Count -eq 0)" | Add-Content -Encoding ascii -Path $owned
    if ($g.Count) { $alive++ }
  }
  Write-Output "LAUNCHER $($child.Id) EXIT $code OWNED_DESCENDANTS $($seen.Count) ALIVE $alive"
  if ($alive) { throw "Owned descendant PIDs alive: $alive" }
  return $code
}
if ($Phase -eq 'pins') {
  $code = Invoke-TrackedPython @('-B', '-m', 'unittest', 'tests.test_showready_rail.ShowreadyPinTests.test_pins_match_exact_file_set_and_bytes')
  if ($code[-1] -ne 0) { exit $code[-1] }
  $code = Invoke-TrackedPython @('-B', 'scripts/showready/deck_script.py', '--fixtures', $fixtures, '--out', "$work\deck-script.json")
  if ($code[-1] -ne 0) { exit $code[-1] }
  $code = Invoke-TrackedPython @('-B', 'scripts/showready/timing_subset_check.py', 'scripts/showready/timing_script.json', "$work\deck-script.json")
  exit $code[-1]
}
$common = @('-B', 'scripts/showready/timing_ab.py', '--candidate', 'HEAD', '--script', 'scripts/showready/timing_script.json', '--fixtures', $fixtures, '--preset', "$fixtures\mac\presets\EDM Show.json")
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if (-not (Test-Path $edge)) { $edge = 'C:\Program Files\Microsoft\Edge\Application\msedge.exe' }
$node = Get-Command node -ErrorAction SilentlyContinue
if (-not $PythonClient -and ((-not (Test-Path $edge)) -or (-not $node) -or (-not $env:PLAYWRIGHT_CORE) -or (-not (Test-Path $env:PLAYWRIGHT_CORE)))) {
  $PythonClient = $true
  'Python fallback: existing Edge/Node/PLAYWRIGHT_CORE unavailable; real-browser case measured on Mac only.' | Set-Content -Encoding ascii "$work\client-choice.txt"
}
if (-not $PythonClient) {
  $client = @($node.Source, "$PWD\scripts\showready\timing_browser.cjs", '{url}', '{stop}', '{receipt}', $edge) | ConvertTo-Json -Compress
  $client | Set-Content -Encoding ascii -Path "$work\client-command.json"
  $common += @('--client-cmd-file', "$work\client-command.json")
  $label = 'edge'
} else {
  $label = 'python'
}
Write-Output "CLIENT $label"
if ($Phase -eq 'ctl10') {
  # MASTER 02:58 Windows control: scratch repo with 2 ms on every 10th published event; never the clone.
  $ctl = Join-Path $work 'ctl10-repo'
  if (-not (Test-Path $ctl)) {
    & git clone -q --no-hardlinks 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc' $ctl
    if ($LASTEXITCODE -ne 0) { exit 20 }
    & git -C $ctl fetch -q (Join-Path $work 'ctl10.bundle') 'gate-ctl10'
    if ($LASTEXITCODE -ne 0) { exit 21 }
  }
  $sha = (& git -C $ctl rev-parse FETCH_HEAD)
  Write-Output "CTL10_SHA $sha"
  if ($sha -ne 'cc4c7698951de835700082b46a03bded3d503210') { exit 22 }
  $code = Invoke-TrackedPython ($common + @('--repo', $ctl, '--candidate', $sha, '--repeats', '3', '--scratch', "$work\$label-ctl10", '--out', "$work\$label-ctl10.json.gz"))
  exit $code[-1]
}
if ($Phase -eq 'sensitivity') {
  $code = Invoke-TrackedPython ($common + @('--repeats', '3', '--scratch', "$work\$label-sensitivity", '--out', "$work\$label-sensitivity.json.gz", '--control', 'sensitivity'))
  exit $code[-1]
}
$cleanExit = Invoke-TrackedPython ($common + @('--repeats', '5', '--scratch', "$work\$label-clean", '--out', "$work\$label-clean.json.gz", '--sensitivity-result', "$work\$label-sensitivity.json.gz"))
exit $cleanExit[-1]
