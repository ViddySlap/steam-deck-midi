param([string]$Label, [string]$Preset, [string]$Section='', [string]$Control='', [string]$Speed='1', [string]$Candidate='b3b28612c3be1a9e841c82c557a219e72b73eaea')
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$fixtures = 'C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures'
$python = Join-Path $clone '.venv\Scripts\python.exe'
$work = Join-Path $PSScriptRoot ('qpc-'+$Label)
if (Test-Path -LiteralPath $work) { throw 'Refuse existing run directory' }
New-Item -ItemType Directory -Path $work | Out-Null
$env:PYSTRAY_BACKEND='dummy'
$env:BROWSER='C:/Windows/System32/cmd.exe /c rem %s'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=$work
$env:TMP=$work
$presetPath = if ($Preset -eq 'tracked-default') { Join-Path $clone 'config\presets\default.json' } else { Join-Path $fixtures $Preset }
$argv = @('-B',(Join-Path $clone 'scripts\showready\ab_run.py'),'--candidate',$Candidate,'--preset',$presetPath,'--script',(Join-Path $PSScriptRoot 'deck-script.json'),'--fixtures',$fixtures,'--scratch',$work,'--speed',$Speed,'--out',(Join-Path $PSScriptRoot ($Label+'.json')))
if ($Section) { $argv += @('--section',$Section) }
if ($Control) { $argv += @('--control',$Control,'--mapping','BTN_A') }
$arguments = ($argv | ForEach-Object { '"' + $_ + '"' }) -join ' '
$record = [ordered]@{label=$Label; command=(@($python)+$argv); udp_before=@(Get-NetUDPEndpoint | Select-Object LocalAddress,LocalPort,OwningProcess); tcp_before=@(Get-NetTCPConnection | Select-Object LocalAddress,LocalPort,State,OwningProcess); ready=@(); live=@(); python_pids=@(); cleanup=@(); exit=$null; cleanup_passed=$false}
$child = Start-Process -FilePath $python -ArgumentList $arguments -NoNewWindow -PassThru -RedirectStandardOutput (Join-Path $PSScriptRoot ($Label+'.stdout.txt')) -RedirectStandardError (Join-Path $PSScriptRoot ($Label+'.stderr.txt'))
$null=$child.Handle
$record.driver_pid=$child.Id
$observed=@{}
$watch=[Diagnostics.Stopwatch]::StartNew()
while (-not $child.HasExited) {
    foreach ($file in @(Get-ChildItem -LiteralPath $work -Filter '*.ready.json' -Recurse -File)) {
        if ($observed.ContainsKey($file.FullName)) { continue }
        try { $ready=[IO.File]::ReadAllText($file.FullName) | ConvertFrom-Json } catch { continue }
        $observed[$file.FullName]=$ready
        $record.ready += $ready
        $record.python_pids += @(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -and $_.CommandLine.Contains($work) } | ForEach-Object { $_.ProcessId })
        $udp=@(Get-NetUDPEndpoint | Where-Object { $_.LocalPort -in @($ready.bound[1],45123) } | Select-Object LocalAddress,LocalPort,OwningProcess)
        $tcp=@(Get-NetTCPConnection | Where-Object { $_.LocalPort -eq 7723 } | Select-Object LocalAddress,LocalPort,State,OwningProcess)
        $record.live += [ordered]@{ready=$ready; udp=$udp; tcp=$tcp; process=@(Get-Process -Id $ready.pid -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path)}
        Write-Output "LIVE $Label arm PID=$($ready.pid) UDP=$($ready.bound[1])"
        $record | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ($Label+'.observation.json')) -Encoding UTF8
    }
    if ($watch.Elapsed.TotalSeconds -gt 1200) { throw 'Run exceeded 1200 seconds' }
    Start-Sleep -Milliseconds 500
    $child.Refresh()
}
$child.WaitForExit()
$record.exit=$child.ExitCode
$ids=@($child.Id)+@($record.python_pids)+@($record.ready | ForEach-Object { $_.pid })
$leaked=$false
foreach ($childId in $ids) {
    $alive=@(Get-Process -Id $childId -ErrorAction SilentlyContinue)
    $row=[ordered]@{pid=$childId; gone=($alive.Count -eq 0); forced_cleanup=$false}
    if ($alive.Count -gt 0 -and $childId -ne $child.Id) {
        # This exact PID came from the owned runner's socket-ready artifact.
        $identity=Get-CimInstance Win32_Process -Filter "ProcessId=$childId"
        if (-not $identity.CommandLine.Contains('capture_runner.py') -or -not $identity.CommandLine.Contains($work)) { throw "Refuse stopping unowned PID $childId" }
        $row.command_line=$identity.CommandLine
        Stop-Process -Id $childId
        $alive[0].WaitForExit(10000) | Out-Null
        $row.forced_cleanup=$true
        $row.gone_after_cleanup=(@(Get-Process -Id $childId -ErrorAction SilentlyContinue).Count -eq 0)
        $leaked=$true
    }
    $record.cleanup += $row
}
$record.cleanup_passed=(-not $leaked -and @($record.cleanup | Where-Object {-not $_.gone}).Count -eq 0 -and $record.ready.Count -ge 2)
$record | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ($Label+'.observation.json')) -Encoding UTF8
Get-Content -LiteralPath (Join-Path $PSScriptRoot ($Label+'.stdout.txt'))
Get-Content -LiteralPath (Join-Path $PSScriptRoot ($Label+'.stderr.txt'))
Write-Output "RESULT $Label EXIT=$($record.exit) CLEANUP=$($record.cleanup_passed)"
if (-not $record.cleanup_passed) { exit 2 }
exit $record.exit
