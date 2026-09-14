param([string]$Label = 'windows-before', [switch]$Utf8)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$status = @(git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $status.Count -ne 0) { throw 'Clone not clean' }
$branch = git -C $clone branch --show-current
if ($branch -ne 'chain/steamdeck-20260914') { throw 'Wrong clone branch' }
git -C $clone pull --ff-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$head = git -C $clone rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $head -ne 'e5293b40d7806819dbd970b04dd5c1a774426286') { throw "Clone HEAD mismatch: $head" }
Write-Output "VERIFIED_CLONE_HEAD $head"
Set-Location -LiteralPath $clone
$env:PYSTRAY_BACKEND = 'dummy'
$env:BROWSER = 'C:/Windows/System32/cmd.exe /c rem %s'
$env:TEMP = $PSScriptRoot
$env:TMP = $PSScriptRoot
$python = Join-Path $clone '.venv\Scripts\python.exe'
$arguments = '-m unittest discover -s tests -p "test_*.py"'
if ($Utf8) { $arguments = '-X utf8 ' + $arguments }
Write-Output "SUITE $python $arguments"
$stdout = Join-Path $PSScriptRoot "$Label.stdout.log"
$stderr = Join-Path $PSScriptRoot "$Label.stderr.log"
$child = Start-Process -FilePath $python -ArgumentList $arguments -NoNewWindow -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
$null = $child.Handle
    $childId = $child.Id
Write-Output "SUITE_PID $childId"
$child.WaitForExit()
$code = $child.ExitCode
Get-Content -LiteralPath $stdout
Get-Content -LiteralPath $stderr
if (Get-Process -Id $childId -ErrorAction SilentlyContinue) { throw "Suite pid remains: $childId" }
Write-Output "GONE suite PID $childId EXIT $code"
Get-Process | Where-Object { $_.ProcessName -in @('python','pythonw') } | ForEach-Object {
    if (-not $_.Path) { throw "Unreadable python path: $($_.Id)" }
    if ($_.Path.StartsWith($clone + '\', [StringComparison]::OrdinalIgnoreCase) -or $_.Path.StartsWith('C:\Users\Ben\AppData\Local\Temp\sdwin\', [StringComparison]::OrdinalIgnoreCase)) { throw "Python leak: $($_.Id) $($_.Path)" }
}
Write-Output 'GET-PROCESS: no python under CLONE or LAPTOP WORK'
exit $code
