$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$env:PYSTRAY_BACKEND = 'dummy'
$env:BROWSER = 'C:/Windows/System32/cmd.exe /c rem %s'
$env:TEMP = $PSScriptRoot
$env:TMP = $PSScriptRoot
$python = Join-Path $env:PYTHONPATH '.venv\Scripts\python.exe'
$names = @('test_learn_full_capture_confirm_duplicate_skip_and_save','test_learn_single_action_preserves_siblings_and_cancel_does_not_write','test_learn_single_skip_cancels_and_invalid_action_is_rejected')
foreach ($phase in @('fixed','mutant','fixed')) {
    $arguments = '-m unittest -v ' + (($names | ForEach-Object { "test_control_$phase.DeckControlAPITests.$_" }) -join ' ')
    $stdout = Join-Path $PSScriptRoot "pipe-$phase.stdout.log"
    $stderr = Join-Path $PSScriptRoot "pipe-$phase.stderr.log"
    $child = Start-Process -FilePath $python -ArgumentList $arguments -NoNewWindow -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $null = $child.Handle
    $childId = $child.Id
    $child.WaitForExit()
    $code = $child.ExitCode
    Get-Content $stdout
    Get-Content $stderr
    if (Get-Process -Id $childId -ErrorAction SilentlyContinue) { throw "Leaked pid $childId" }
    Write-Output "GONE $phase PID $childId EXIT $code"
    $expected = if ($phase -eq 'mutant') { 1 } else { 0 }
    if ($code -ne $expected) { throw "Wrong exit: $code expected $expected" }
}
exit 0
