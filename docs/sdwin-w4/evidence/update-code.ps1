Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$orphan = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi'
$fixtures = 'C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures'
$expected = 'b3b28612c3be1a9e841c82c557a219e72b73eaea'
if (@(git -C $clone status --porcelain).Count -ne 0) { throw 'Clone dirty' }
git -C $clone pull --ff-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$head = git -C $clone rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $head -ne $expected) { throw "HEAD mismatch $head" }
$tag = git -C $clone rev-parse 'v0.4.9^{commit}'
if ($LASTEXITCODE -ne 0 -or $tag -ne 'e66ff44b36eadb6d43db01680c65279df82cd63c') { throw "Tag mismatch $tag" }
$pins = @()
foreach ($line in [IO.File]::ReadAllLines((Join-Path $clone 'scripts\showready\SHA256SUMS'))) {
    $parts = $line -split '  ', 2
    $actual = (Get-FileHash -LiteralPath (Join-Path $clone $parts[1]) -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $parts[0]) { throw "Pin mismatch $($parts[1])" }
    $pins += [ordered]@{ path=$parts[1]; expected=$parts[0]; actual=$actual }
}
$dir = Join-Path $fixtures 'windows-installed'
$manifest = [IO.File]::ReadAllText((Join-Path $dir 'MANIFEST.sha256')) | ConvertFrom-Json
if (@($manifest.entries).Count -ne 11) { throw 'Missing fixture entries' }
$verified = @()
foreach ($row in $manifest.entries) {
    $path = Join-Path $dir $row.relative
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $row.sha256_before -or $actual -ne $row.sha256_after -or $actual -ne $row.sha256_copy -or (Get-Item -LiteralPath $path).Length -ne $row.bytes) { throw "Fixture mismatch $path" }
    $verified += [ordered]@{path=$row.relative; sha256=$actual; bytes=$row.bytes}
}
$orphanHead = git --no-optional-locks -C $orphan rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Orphan HEAD read failed' }
$dirty = @(git --no-optional-locks -C $orphan status --porcelain -- windows config deck protocol)
if ($LASTEXITCODE -ne 0) { throw 'Orphan status read failed' }
$installed = @(git --no-optional-locks -C $orphan ls-tree -r d136787 -- windows config deck protocol)
if ($LASTEXITCODE -ne 0 -or $installed.Count -eq 0) { throw 'Installed tree unread' }
$tagTree = @(git -C $clone ls-tree -r e66ff44 -- windows config deck protocol)
if ($LASTEXITCODE -ne 0 -or $tagTree.Count -eq 0) { throw 'Tag tree unread' }
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot 'installed-tree.txt'), [string[]]$installed)
[IO.File]::WriteAllLines((Join-Path $PSScriptRoot 'tag-tree.txt'), [string[]]$tagTree)
$udp = @(Get-NetUDPEndpoint | Sort-Object LocalPort,OwningProcess | Select-Object LocalAddress,LocalPort,OwningProcess)
$tcp = @(Get-NetTCPConnection | Sort-Object LocalPort,OwningProcess | Select-Object LocalAddress,LocalPort,RemoteAddress,RemotePort,State,OwningProcess)
$record = [ordered]@{head=$head; tag=$tag; pins=$pins; fixtures=$verified; manifest_sha256=(Get-FileHash -LiteralPath (Join-Path $dir 'MANIFEST.sha256')).Hash.ToLower(); orphan_head=$orphanHead; orphan_dirty=$dirty; installed_tree=$installed; tag_tree=$tagTree; tree_difference=@(Compare-Object $installed $tagTree); udp=$udp; tcp=$tcp; mac_fixtures_present=(Test-Path -LiteralPath (Join-Path $fixtures 'mac\MANIFEST.sha256')); tracked_default_sha256=(Get-FileHash -LiteralPath (Join-Path $clone 'config\presets\default.json')).Hash.ToLower()}
$record | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'preflight-final.json') -Encoding UTF8
Write-Output "PREFLIGHT GREEN HEAD=$head TAG=$tag pins=$($pins.Count) fixtures=$($verified.Count) orphan=$orphanHead dirty=$($dirty.Count) differences=$(@($record.tree_difference).Count) mac_fixtures_present=$($record.mac_fixtures_present)"
$record.tree_difference | Format-Table -AutoSize
$dirty
