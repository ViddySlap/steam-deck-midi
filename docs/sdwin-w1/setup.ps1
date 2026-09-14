Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
Set-Location -LiteralPath $clone
function Run-Owned([string]$Exe, [string]$Arguments, [string]$Label) {
    $stdout = Join-Path $PSScriptRoot "$Label.stdout.log"
    $stderr = Join-Path $PSScriptRoot "$Label.stderr.log"
    $child = Start-Process -FilePath $Exe -ArgumentList $Arguments -PassThru -NoNewWindow -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $null = $child.Handle
    $childId = $child.Id
    Write-Output "STARTED $Label PID $childId"
    $child.WaitForExit()
    $code = $child.ExitCode
    Get-Content -LiteralPath $stdout
    Get-Content -LiteralPath $stderr
    if (Get-Process -Id $childId -ErrorAction SilentlyContinue) { throw "Still running: $childId" }
    Write-Output "GONE $Label PID $childId EXIT $code"
    if ($code -ne 0) { throw "$Label failed: $code" }
}
Run-Owned 'py' '-3.12 -m venv C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\.venv' 'venv'
$python = Join-Path $clone '.venv\Scripts\python.exe'
Run-Owned $python '-m pip install -r requirements.txt' 'pip'
Run-Owned $python '-m pip freeze' 'freeze'
$status = @(& git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $status.Count -gt 0) { throw "Clone not clean: $status" }
Write-Output 'CLONE PORCELAIN EMPTY'
Get-Process | Where-Object { $_.ProcessName -in @('python','pythonw') } | ForEach-Object {
    if (-not $_.Path) { throw "Unreadable python path for pid $($_.Id)" }
    if ($_.Path.StartsWith($clone + '\', [StringComparison]::OrdinalIgnoreCase) -or $_.Path.StartsWith('C:\Users\Ben\AppData\Local\Temp\sdwin\', [StringComparison]::OrdinalIgnoreCase)) { throw "Python leak: $($_.Id) $($_.Path)" }
}
Write-Output 'GET-PROCESS: no python under CLONE or LAPTOP WORK'
