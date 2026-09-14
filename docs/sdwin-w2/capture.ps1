Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$status = @(& git -C $clone status --porcelain)
if ($LASTEXITCODE -ne 0 -or $status.Count -ne 0) { throw 'Clone not clean' }
& git -C $clone pull --ff-only
if ($LASTEXITCODE -ne 0) { throw 'Clone pull failed' }
$head = & git -C $clone rev-parse HEAD
if ($head -ne '72d3a21239fbb79d3b2552c690bee4769b604c74') { throw "Unexpected HEAD $head" }
Write-Output "CLONE_HEAD $head"
$install = 'C:\Program Files\STEAMDECK MIDI Receiver 2'
$config = Join-Path $install 'config'
$layout = @(Get-ChildItem -LiteralPath $install -Force | Select-Object Name,Mode)
$processes = @(Get-CimInstance Win32_Process | Where-Object Name -like 'STEAMDECK-MIDI-RECEIVER-2*' | Select-Object ProcessId,ExecutablePath,CommandLine)
if ($processes.Count -lt 1) { throw 'No installed tray observation' }
$map = Join-Path $config 'windows_midi_map.json'
foreach ($proc in $processes) {
    if (-not $proc.CommandLine.Contains('--map "' + $map + '"')) { throw "Unconfirmed map path for PID $($proc.ProcessId)" }
}
$destRoot = 'C:\Users\Ben\AppData\Local\Temp\sdwin\fixtures\windows-installed'
if (Test-Path -LiteralPath $destRoot) { throw 'Fixture directory already exists; refuse overwrite' }
New-Item -ItemType Directory -Path $destRoot | Out-Null
$presetRoot = Join-Path $config 'presets'
$presets = @(Get-ChildItem -LiteralPath $presetRoot -Recurse -Force -File)
foreach ($name in @('EDM Show.json','PTZ.json','default.json','.active')) {
    if (-not (Test-Path -LiteralPath (Join-Path $presetRoot $name) -PathType Leaf)) { throw "Missing required preset/marker $name" }
}
$sources = @($presets.FullName) + @((Join-Path $config 'macro_library.json'), $map)
$settings = Join-Path $config 'windows_receiver_settings.local.json'
if (Test-Path -LiteralPath $settings -PathType Leaf) { $sources += $settings }
$entries = @()
foreach ($source in ($sources | Sort-Object -Unique)) {
    $relative = $source.Substring($config.Length + 1)
    $dest = Join-Path $destRoot $relative
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null
    $before = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    Copy-Item -LiteralPath $source -Destination $dest
    $after = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    $copy = (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($before -ne $after -or $before -ne $copy) { throw "Copy mismatch $source" }
    (Get-Item -LiteralPath $dest).IsReadOnly = $true
    $entries += [ordered]@{source=$source; destination=$dest; relative=$relative.Replace('\','/'); sha256_before=$before; sha256_after=$after; sha256_copy=$copy; bytes=(Get-Item -LiteralPath $dest).Length}
}
$manifest = [ordered]@{schema='sdwin-fixtures/1'; entries=$entries}
$manifestPath = Join-Path $destRoot 'MANIFEST.sha256'
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), (New-Object Text.UTF8Encoding($false)))
(Get-Item -LiteralPath $manifestPath).IsReadOnly = $true
[ordered]@{clone_head=$head; install=$install; config=$config; layout=$layout; tray=$processes; files=$entries; settings_present=(Test-Path -LiteralPath $settings)} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'capture.json') -Encoding UTF8
Write-Output "CAPTURE $($entries.Count) files; all before/after/copy hashes equal"
$presets | Select-Object Name,Length | Format-Table | Out-String | Write-Output
