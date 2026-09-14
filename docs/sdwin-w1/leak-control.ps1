$ErrorActionPreference = 'Stop'
$python = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc\.venv\Scripts\python.exe'
$stop = Join-Path $PSScriptRoot 'leak-stop'
$pidFile = Join-Path $PSScriptRoot 'leak-child.pid'
if (Test-Path $stop) { throw 'Leak control stop file already exists' }
$child = Start-Process -FilePath $python -ArgumentList ('"' + (Join-Path $PSScriptRoot 'leak-child.py') + '" "' + $PSScriptRoot + '"') -NoNewWindow -PassThru
$null = $child.Handle
$childId = $child.Id
$workerId = $null
$code = 2
try {
    for ($i=0; $i -lt 100 -and -not (Test-Path $pidFile); $i++) { Start-Sleep -Milliseconds 50 }
    if (-not (Test-Path $pidFile)) { throw 'No child pid observation' }
    $workerId = [int](Get-Content $pidFile)
    Get-Process -Id $childId,$workerId | Select-Object Id,ProcessName,Path | Format-Table
    & (Join-Path $PSScriptRoot 'win_guard.ps1') -Mode compare -Baseline (Join-Path $PSScriptRoot 'baseline.json') -Out (Join-Path $PSScriptRoot 'guard-leak.json')
    $code = $LASTEXITCODE
    Write-Output "LEAK_COMPARE_EXIT $code"
} finally {
    [IO.File]::WriteAllText($stop, 'stop')
    if (-not $child.WaitForExit(10000)) {
        if ($workerId -and (Get-Process -Id $workerId -ErrorAction SilentlyContinue)) { Stop-Process -Id $workerId -Force }
        if (Get-Process -Id $childId -ErrorAction SilentlyContinue) { Stop-Process -Id $childId -Force }
        $child.WaitForExit()
    }
    foreach ($knownId in @($childId,$workerId) | Where-Object { $_ } | Select-Object -Unique) {
        if (Get-Process -Id $knownId -ErrorAction SilentlyContinue) { throw "Leak pid still running: $knownId" }
        Write-Output "GET-PROCESS GONE $knownId"
    }
}
if ($code -ne 1) { throw "Expected live Python detector RED, got $code" }
exit 0
