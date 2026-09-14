$ErrorActionPreference = 'Stop'
foreach ($probeId in @(273344,274976)) {
    $p = Get-Process -Id $probeId -ErrorAction SilentlyContinue
    if ($null -ne $p) { throw "Owned probe/parent remains: $probeId" }
    Write-Output "GET-PROCESS GONE $probeId"
}
