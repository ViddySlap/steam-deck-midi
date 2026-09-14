$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot 'kit-check'
Expand-Archive -LiteralPath (Join-Path $PSScriptRoot 'kit-check.zip') -DestinationPath $root -Force
Set-Location -LiteralPath $root
$python = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\.venv\Scripts\python.exe'
$child = Start-Process -FilePath $python -ArgumentList '-m unittest discover -s tests -p test_showready_rail.py -v' -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot 'kit-check.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'kit-check.stderr.log')
$null = $child.Handle
$childId = $child.Id
$child.WaitForExit()
$code = $child.ExitCode
Get-Content (Join-Path $PSScriptRoot 'kit-check.stdout.log')
Get-Content (Join-Path $PSScriptRoot 'kit-check.stderr.log')
if (Get-Process -Id $childId -ErrorAction SilentlyContinue) { throw "Leaked pid $childId" }
Write-Output "GONE kit-check PID $childId EXIT $code"
exit $code
