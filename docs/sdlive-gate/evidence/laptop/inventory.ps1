Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
Write-Output "CLONE_HEAD $(& git -C $clone rev-parse HEAD)"
Write-Output "CLONE_BRANCH $(& git -C $clone rev-parse --abbrev-ref HEAD)"
$dirty=@(& git -C $clone status --porcelain)
Write-Output "CLONE_PORCELAIN_LINES $($dirty.Count)"
foreach ($p in @('C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe','C:\Program Files\Microsoft\Edge\Application\msedge.exe')) { if (Test-Path -LiteralPath $p) { Write-Output "EDGE $p $((Get-Item -LiteralPath $p).VersionInfo.ProductVersion)" } else { Write-Output "EDGE_ABSENT $p" } }
$node=Get-Command node -ErrorAction SilentlyContinue
if ($node) { Write-Output "NODE $($node.Source) $(& $node.Source --version)" } else { Write-Output 'NODE_ABSENT' }
Write-Output "PLAYWRIGHT_CORE_ENV $env:PLAYWRIGHT_CORE"
foreach ($d in @("$env:APPDATA\npm\node_modules\playwright-core","$env:USERPROFILE\node_modules\playwright-core")) { Write-Output "PWCORE $d $(Test-Path -LiteralPath $d)" }
$edges=@(Get-Process -Name msedge -ErrorAction SilentlyContinue)
Write-Output "MSEDGE_PROCESSES_NOW $($edges.Count)"
$py=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') })
Write-Output "PYTHON_PROCESSES $($py.Count)"
foreach ($l in $py) { Write-Output "PY $($l.ProcessId) $($l.ExecutablePath)" }
foreach ($c in @(Get-NetUDPEndpoint -LocalPort 45123 -ErrorAction SilentlyContinue)) { Write-Output "UDP45123 pid=$($c.OwningProcess)" }
foreach ($c in @(Get-NetTCPConnection -LocalPort 7723 -State Listen -ErrorAction SilentlyContinue)) { Write-Output "TCP7723 pid=$($c.OwningProcess)" }
Write-Output "CPU $((Get-CimInstance Win32_Processor | Select-Object -First 1).Name) LOGICAL $((Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors)"
Write-Output "PY_VERSION $(& (Join-Path $clone '.venv\Scripts\python.exe') --version)"
exit 0
