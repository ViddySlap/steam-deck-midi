$ErrorActionPreference = 'Stop'
$probeId = 273344
$probe = Get-CimInstance Win32_Process -Filter "ProcessId=$probeId"
if ($null -ne $probe) {
    if ($probe.Name -ne 'powershell.exe' -or $probe.CommandLine -notlike '*sdwin/w2/arms.ps1*executed*') { throw 'Refuse mismatched process identity' }
    Stop-Process -Id $probeId -ErrorAction Stop
    Wait-Process -Id $probeId -ErrorAction SilentlyContinue
}
if (Get-Process -Id $probeId -ErrorAction SilentlyContinue) { throw 'Probe remains' }
Write-Output "GONE owned evidence serializer PID $probeId"
