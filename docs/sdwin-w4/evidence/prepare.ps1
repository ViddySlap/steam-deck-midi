Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$orphan = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi'
$fixtures = 'C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures'
if (Test-Path -LiteralPath (Join-Path $fixtures 'mac')) { throw 'Refuse replacing Mac fixture set' }
Expand-Archive -LiteralPath (Join-Path $PSScriptRoot 'mac-fixtures.zip') -DestinationPath $fixtures
foreach ($path in @('config/engines.factory/osc_sync.json','windows/engines/osc_sync.py','windows/engines/stageflow_bridge.py')) {
    $content = @(git --no-optional-locks -C $orphan show "d136787:$path")
    if ($LASTEXITCODE -ne 0) { throw "Read failed: $path" }
    [IO.File]::WriteAllLines((Join-Path $PSScriptRoot ('installed-' + [IO.Path]::GetFileName($path))), [string[]]$content)
}
Get-ChildItem -LiteralPath (Join-Path $fixtures 'mac') -File -Recurse | ForEach-Object { $_.IsReadOnly=$true }
$python = Join-Path $clone '.venv\Scripts\python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:TEMP=$PSScriptRoot
$env:TMP=$PSScriptRoot
$child = Start-Process -FilePath $python -ArgumentList '--version' -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'python-version.txt')
$null=$child.Handle
$child.WaitForExit()
if ($child.ExitCode -ne 0 -or (Get-Process -Id $child.Id -ErrorAction SilentlyContinue)) { throw 'Python version failed/left running' }
Get-Content -LiteralPath (Join-Path $PSScriptRoot 'python-version.txt')
Write-Output "GONE version PID $($child.Id)"
$arguments = '-B "' + (Join-Path $clone 'scripts\showready\deck_script.py') + '" --fixtures "' + $fixtures + '" --out "' + (Join-Path $PSScriptRoot 'deck-script.json') + '"'
$child = Start-Process -FilePath $python -ArgumentList $arguments -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'generator.stdout.txt') -RedirectStandardError (Join-Path $PSScriptRoot 'generator.stderr.txt')
$null=$child.Handle
$child.WaitForExit()
Get-Content -LiteralPath (Join-Path $PSScriptRoot 'generator.stdout.txt')
Get-Content -LiteralPath (Join-Path $PSScriptRoot 'generator.stderr.txt')
if ($child.ExitCode -ne 0 -or (Get-Process -Id $child.Id -ErrorAction SilentlyContinue)) { throw 'Generator failed/left running' }
Write-Output "GONE generator PID $($child.Id)"
