param(
    [Parameter(Mandatory=$true)][ValidateSet('snapshot','compare')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$Out,
    [string]$Baseline
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$install = 'C:\Program Files\STEAMDECK MIDI Receiver 2'
$clone = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi-rc'
$work = 'C:\Users\Ben\AppData\Local\Temp\sdwin'
$orphan = 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi'

function Hash-Text([string]$Text) {
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
}
function Under-Root([string]$Path, [string]$Root) {
    return $Path.StartsWith($Root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
}
function Get-Snapshot {
    $all = @(Get-Process -ErrorAction Stop)
    $protected = @($all | Where-Object { $_.ProcessName -like 'STEAMDECK-MIDI-RECEIVER-2*' -or $_.ProcessName -eq 'loopMIDI' } | Sort-Object Id | ForEach-Object {
        [ordered]@{ pid=$_.Id; name=$_.ProcessName; startTimeUtc=$_.StartTime.ToUniversalTime().ToString('o') }
    })
    $python = @($all | Where-Object { $_.ProcessName -in @('python','pythonw') } | Sort-Object Id | ForEach-Object {
        $path = $_.Path
        if (-not $path) { throw "Cannot read python path for pid $($_.Id)" }
        if ((Under-Root $path $clone) -or (Under-Root $path $work)) {
            [ordered]@{ pid=$_.Id; name=$_.ProcessName; path=$path; startTimeUtc=$_.StartTime.ToUniversalTime().ToString('o') }
        }
    })
    $udp = @(Get-NetUDPEndpoint -ErrorAction Stop | Where-Object LocalPort -eq 45123 | Sort-Object LocalAddress,OwningProcess | ForEach-Object {
        [ordered]@{ address=$_.LocalAddress; port=$_.LocalPort; pid=$_.OwningProcess; name=(Get-Process -Id $_.OwningProcess -ErrorAction Stop).ProcessName }
    })
    $tcp = @(Get-NetTCPConnection -State Listen -ErrorAction Stop | Where-Object LocalPort -eq 7723 | Sort-Object LocalAddress,OwningProcess | ForEach-Object {
        [ordered]@{ address=$_.LocalAddress; port=$_.LocalPort; pid=$_.OwningProcess; name=(Get-Process -Id $_.OwningProcess -ErrorAction Stop).ProcessName }
    })
    $files = @(Get-ChildItem -LiteralPath $install -Recurse -Force -File -ErrorAction Stop | Sort-Object FullName | ForEach-Object {
        [ordered]@{ path=$_.FullName.Substring($install.Length + 1); length=$_.Length; lastWriteTimeUtc=$_.LastWriteTimeUtc.ToString('o') }
    })
    # Installer v2 [Dirs]/[Icons] and start_installed_receiver_v2.ps1 put
    # mutable config beside the installed EXE. tray.py LOCALAPPDATA is logs.
    $configPath = Join-Path $install 'config'
    $looked = @($configPath,
        'C:\Users\Ben\AppData\Local\STEAMDECK MIDI Receiver 2\config',
        'C:\Users\Ben\AppData\Roaming\STEAMDECK MIDI Receiver 2\config',
        'C:\Users\Ben\AppData\Local\VirtualStore\Program Files\STEAMDECK MIDI Receiver 2\config')
    $locations = @($looked | ForEach-Object {
        $candidate = $_
        $exists = Test-Path -LiteralPath $candidate -PathType Container
        $hashes = @()
        if ($exists) {
            $hashes = @(Get-ChildItem -LiteralPath $candidate -Recurse -Force -File -ErrorAction Stop | Sort-Object FullName | ForEach-Object {
                [ordered]@{ path=$_.FullName.Substring($candidate.Length + 1); sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant() }
            })
        }
        [ordered]@{ path=$candidate; exists=$exists; files=$hashes }
    })
    $configStatus = if (Test-Path -LiteralPath $configPath -PathType Container) { 'FOUND' } else { 'NOT FOUND' }
    $head = @(& git --no-optional-locks -C $orphan rev-parse HEAD)
    if ($LASTEXITCODE -ne 0) { throw 'Orphan HEAD read failed' }
    $status = @(& git --no-optional-locks -C $orphan status --porcelain)
    if ($LASTEXITCODE -ne 0) { throw 'Orphan status read failed' }
    return [ordered]@{
        schema='sdwin-guard/1'
        udp45123=$udp; tcp7723=$tcp; protectedProcesses=$protected
        install=[ordered]@{ path=$install; fileCount=$files.Count; metadataSha256=(Hash-Text (ConvertTo-Json -InputObject $files -Depth 8 -Compress)) }
        userConfig=[ordered]@{ status=$configStatus; path=$configPath; locations=$locations }
        orphan=[ordered]@{ path=$orphan; head=($head -join "`n"); statusSha256=(Hash-Text ($status -join "`n")) }
        pythonProcesses=$python
    }
}
function Flatten($Value, [string]$Path, $Dest) {
    if ($null -eq $Value) { $Dest[$Path]='null'; return }
    if ($Value -is [string] -or $Value -is [ValueType]) {
        $Dest[$Path] = ConvertTo-Json -InputObject $Value -Compress
    } elseif ($Value -is [System.Collections.IDictionary]) {
        $Dest["$Path.keys"] = ConvertTo-Json -InputObject @($Value.Keys | Sort-Object) -Compress
        foreach ($key in $Value.Keys) { Flatten $Value[$key] "$Path.$key" $Dest }
    } elseif ($Value -is [pscustomobject]) {
        $Dest["$Path.keys"] = ConvertTo-Json -InputObject @($Value.PSObject.Properties | ForEach-Object { $_.Name } | Sort-Object) -Compress
        foreach ($prop in $Value.PSObject.Properties) { Flatten $prop.Value "$Path.$($prop.Name)" $Dest }
    } elseif ($Value -is [array]) {
        $Dest["$Path.count"] = [string]$Value.Count
        for ($i=0; $i -lt $Value.Count; $i++) { Flatten $Value[$i] "$Path[$i]" $Dest }
    } else { $Dest[$Path] = ConvertTo-Json -InputObject $Value -Compress }
}

try {
    $outPath = [IO.Path]::GetFullPath($Out)
    if (-not (Under-Root $outPath $work)) { throw 'Out must be under the sdwin work directory' }
    if ($Mode -eq 'compare') {
        if (-not $Baseline) { throw 'compare requires -Baseline' }
        if ($outPath -eq [IO.Path]::GetFullPath($Baseline)) { throw 'Out must not overwrite Baseline' }
        $before = Get-Content -LiteralPath $Baseline -Raw | ConvertFrom-Json
    }
    $snapshot = Get-Snapshot
    # Only Out is written; its parent must already exist.
    [IO.File]::WriteAllText($outPath, (ConvertTo-Json -InputObject $snapshot -Depth 20), (New-Object Text.UTF8Encoding($false)))
    $bad = $false
    if ($snapshot.udp45123.Count -eq 0 -or $snapshot.tcp7723.Count -eq 0 -or $snapshot.protectedProcesses.Count -eq 0 -or $snapshot.install.fileCount -eq 0 -or $snapshot.userConfig.locations[0].files.Count -eq 0) {
        Write-Output 'GUARD RED: protected observations missing'; $bad = $true
    }
    if ($snapshot.pythonProcesses.Count -gt 0) {
        Write-Output ('GUARD RED: pythonProcesses ' + (ConvertTo-Json -InputObject $snapshot.pythonProcesses -Compress)); $bad = $true
    }
    if ($Mode -eq 'compare') {
        $left = @{}; $right = @{}
        Flatten $before '$' $left
        Flatten $snapshot '$' $right
        foreach ($key in @(@($left.Keys) + @($right.Keys) | Sort-Object -Unique)) {
            if (-not $left.ContainsKey($key) -or -not $right.ContainsKey($key) -or $left[$key] -cne $right[$key]) {
                Write-Output "DIFF $key baseline=$($left[$key]) current=$($right[$key])"; $bad = $true
            }
        }
    }
    if ($bad) { exit 1 }
    Write-Output "GUARD GREEN: $Mode; protected state observed; pythonProcesses=0"
    exit 0
} catch {
    [Console]::Error.WriteLine("GUARD ERROR: $($_.Exception.Message)")
    [Console]::Error.WriteLine($_.ScriptStackTrace)
    exit 2
}
