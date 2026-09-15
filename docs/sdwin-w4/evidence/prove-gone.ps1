param([string]$Label)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$path=Join-Path $PSScriptRoot ($Label+'.json.gz')
$stream=[IO.File]::OpenRead($path)
$zip=[IO.Compression.GZipStream]::new($stream,[IO.Compression.CompressionMode]::Decompress)
$reader=[IO.StreamReader]::new($zip)
try { $result=$reader.ReadToEnd() | ConvertFrom-Json } finally {$reader.Dispose();$zip.Dispose();$stream.Dispose()}
$observation=[IO.File]::ReadAllText((Join-Path $PSScriptRoot ($Label+'.observation.json'))) | ConvertFrom-Json
$ids=@($observation.driver_pid)
foreach ($arm in $result.arms.PSObject.Properties) { $ids += @($arm.Value.pid,$arm.Value.ready.pid) }
$rows=@()
foreach ($childId in @($ids | Sort-Object -Unique)) {
    $found=@(Get-Process -Id $childId -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,Path)
    $rows += [ordered]@{pid=$childId; found=$found; gone=($found.Count -eq 0)}
}
$rows | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot ($Label+'.gone.json')) -Encoding UTF8
if (@($rows | Where-Object {-not $_.gone}).Count -gt 0) { throw 'Owned PID still alive' }
Write-Output "GET-PROCESS GREEN $Label driver and all launcher/worker PIDs=$($rows.Count) gone"
