param([string]$Label, [string]$Root, [string]$Arguments)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$env:PYSTRAY_BACKEND='dummy'
$env:BROWSER='C:/Windows/System32/cmd.exe /c rem %s'
$env:TEMP=$PSScriptRoot
$env:TMP=$PSScriptRoot
$python=Join-Path $clone '.venv\Scripts\python.exe'
$out=Join-Path $PSScriptRoot "$Label.stdout.log"
$err=Join-Path $PSScriptRoot "$Label.stderr.log"
Write-Output "COMMAND $python $Arguments"
Write-Output "CWD $Root"
$child=Start-Process -FilePath $python -ArgumentList $Arguments -WorkingDirectory $Root -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
$null=$child.Handle
$cid=$child.Id
Write-Output "LAUNCHER_PID $cid"
$seen=@{}
while (-not $child.HasExited) {
    foreach ($p in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$cid")) { $seen[[int]$p.ProcessId]=[string]$p.ExecutablePath }
    Start-Sleep -Milliseconds 100
}
$child.WaitForExit()
$code=$child.ExitCode
Get-Content -LiteralPath $out
Get-Content -LiteralPath $err
foreach ($i in @($cid)+@($seen.Keys)) {
    $alive=@(Get-Process -Id $i -ErrorAction SilentlyContinue)
    Write-Output "PID $i gone=$($alive.Count -eq 0)"
    if ($alive.Count) { throw "pid alive $i" }
}
$leak=@(Get-Process -Name python,pythonw -ErrorAction SilentlyContinue | Where-Object {
    if (-not $_.Path) { throw "Unreadable python path $($_.Id)" }
    $_.Path.StartsWith($clone+'\',[StringComparison]::OrdinalIgnoreCase) -or $_.Path.StartsWith('C:\Users\Ben\AppData\Local\Temp\sdwin\',[StringComparison]::OrdinalIgnoreCase)
})
Write-Output "PYTHON_UNDER_CLONE_OR_WORK $($leak.Count)"
if ($leak.Count) { throw 'Python process leak' }
Write-Output "EXIT $code"
exit $code
