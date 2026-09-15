Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$clone='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$ids=@(279004,267200,278204,281692,287416,285720)
# Additional PIDs are passed in the evidence file written by the Mac before upload.
$ids+=@(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'owned-pids.txt') | ForEach-Object { [int]$_ })
foreach ($i in ($ids | Sort-Object -Unique)) {
    $found=@(Get-Process -Id $i -ErrorAction SilentlyContinue)
    Write-Output "PID $i gone=$($found.Count -eq 0)"
    if ($found.Count) { throw "Owned PID remains $i" }
}
$python=@(Get-Process -Name python,pythonw -ErrorAction SilentlyContinue | ForEach-Object {
    if (-not $_.Path) { throw "Unreadable Python path $($_.Id)" }
    if ($_.Path.StartsWith($clone+'\',[StringComparison]::OrdinalIgnoreCase) -or $_.Path.StartsWith('C:\Users\Ben\AppData\Local\Temp\sdwin\',[StringComparison]::OrdinalIgnoreCase)) { $_ }
})
Write-Output "PYTHON_UNDER_CLONE_OR_WORK $($python.Count)"
if ($python.Count) { throw 'Python leak' }
$dirty=@(& git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $dirty.Count) { throw 'Clone is not clean' }
Write-Output "CLONE_HEAD $(& git -C $clone rev-parse HEAD)"
$expected=@{
    'deck\control_api.py'='b1d40b8017b32361e0a2aef3f36846fbd51a4b1dd685e45935e55d582c49820a'
    'tests\test_deck_control_api.py'='fa56305ed7509464e6cf90fdb4c01ce9158abfa78d250e6fc2e393aab1239d0d'
}
foreach ($relative in $expected.Keys) {
    $file=Join-Path $clone $relative
    $normalized=[IO.File]::ReadAllText($file).Replace("`r`n","`n")
    $sha=[Security.Cryptography.SHA256]::Create()
    try { $hash=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($normalized)))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
    Write-Output "SOURCE_LF_SHA256 $relative $hash"
    if ($hash -ne $expected[$relative]) { throw "Source differs from Mac candidate: $relative" }
}
exit 0
