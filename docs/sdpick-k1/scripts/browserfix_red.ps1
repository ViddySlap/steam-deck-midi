# Revert control for the gate's NOOP_BROWSER fix: old cmd.exe string in a scratch copy -> test RED; HEAD copy -> GREEN.
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work='C:\Users\Ben\AppData\Local\Temp\sdwin\sdpick-k1'
$python=Join-Path $clone '.venv\Scripts\python.exe'
$env:PYSTRAY_BACKEND='dummy'; $env:TEMP=$work; $env:TMP=$work
foreach ($arm in @('reverted','head')) {
  $root=Join-Path $work "browserfix-$arm"
  if (Test-Path $root) { throw "exists $root" }
  New-Item -ItemType Directory -Path $root | Out-Null
  git -C $clone archive --format=tar --output="$root.tar" HEAD scripts/showready tests
  tar -xf "$root.tar" -C $root
  $f=Join-Path $root 'scripts\showready\timing_ab.py'
  $t=[IO.File]::ReadAllText($f)
  if ($arm -eq 'reverted') {
    $needle="NOOP_BROWSER = shlex.quote(sys.executable.replace('\\', '/')) + ' -c pass %s' if os.name == 'nt' else '/usr/bin/true'"
    if (([regex]::Matches($t,[regex]::Escape($needle))).Count -ne 1) { throw 'needle' }
    $t=$t.Replace($needle,"NOOP_BROWSER = 'C:/Windows/System32/cmd.exe /c rem %s' if os.name == 'nt' else '/usr/bin/true'")
    [IO.File]::WriteAllText($f,$t)
  }
  $out="$root.log"
  $c=Start-Process -FilePath $python -ArgumentList '-B -m unittest -v tests.test_showready_timing.TimingTests.test_bridge_noop_browser_command_really_succeeds' -WorkingDirectory $root -NoNewWindow -PassThru -RedirectStandardOutput "$root.out.log" -RedirectStandardError $out
  $null=$c.Handle; $c.WaitForExit()
  Write-Output "ARM $arm EXIT $($c.ExitCode)"
  Get-Content $out | Select-String -Pattern 'FAIL|OK|Error|test_bridge' | ForEach-Object { Write-Output "  $($_.Line)" }
  Start-Sleep -Milliseconds 500
  Write-Output "PID $($c.Id) gone=$(@(Get-Process -Id $c.Id -ErrorAction SilentlyContinue).Count -eq 0)"
}
exit 0
