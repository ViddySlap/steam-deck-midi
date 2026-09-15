param([string]$Label='x')
$ErrorActionPreference='Stop'
$inst='C:\Program Files\STEAMDECK MIDI Receiver 2'
$orphan='C:\Users\Ben\Documents\project-workspaces\steam-deck-midi'
$lines=New-Object System.Collections.Generic.List[string]
function Add([string]$s){ $lines.Add($s) }
Add "label=$Label"
# ports via netstat (a different instrument from Get-NetUDPEndpoint)
$ns = & netstat.exe -ano
foreach ($l in $ns) { if ($l -match '^\s*UDP\s+\S+:45123\s' -or $l -match '^\s*TCP\s+\S+:7723\s+\S+\s+LISTENING') { Add ("netstat: " + ($l -replace '\s+',' ').Trim()) } }
# processes via CIM (different from Get-Process)
foreach ($p in @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'STEAMDECK-MIDI-RECEIVER-2*' -or $_.Name -like 'loopMIDI*' } | Sort-Object ProcessId)) {
  Add ("proc: pid={0} name={1} created={2}" -f $p.ProcessId,$p.Name,$p.CreationDate.ToUniversalTime().ToString('o'))
}
# Program Files inventory via .NET enumeration
$fi = @([IO.Directory]::EnumerateFiles($inst,'*',[IO.SearchOption]::AllDirectories) | ForEach-Object { New-Object IO.FileInfo $_ })
$newest = $fi | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
Add ("progfiles: count={0} newest={1} {2}" -f $fi.Count, $newest.LastWriteTimeUtc.ToString('o'), $newest.FullName.Substring($inst.Length+1))
# user config sha256 via .NET SHA256 (not Get-FileHash)
$cfg = Join-Path $inst 'config'
$sha=[Security.Cryptography.SHA256]::Create()
foreach ($f in @([IO.Directory]::EnumerateFiles($cfg,'*',[IO.SearchOption]::AllDirectories) | Sort-Object)) {
  $b=[IO.File]::ReadAllBytes($f)
  $h=([BitConverter]::ToString($sha.ComputeHash($b))).Replace('-','').ToLowerInvariant()
  Add ("cfg: {0} {1}" -f $h, $f.Substring($cfg.Length+1))
}
$head = & git --no-optional-locks -C $orphan rev-parse HEAD; Add "orphan_head_exit=$LASTEXITCODE head=$head"
$por = @(& git --no-optional-locks -C $orphan status --porcelain); Add "orphan_porcelain_exit=$LASTEXITCODE lines=$($por.Count)"
foreach ($x in $por) { Add "orphan_porcelain: $x" }
$py=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') })
Add "python_processes_total=$($py.Count)"
foreach ($x in $py) { Add ("python: pid={0} exe={1} cmd={2}" -f $x.ProcessId,$x.ExecutablePath,$x.CommandLine) }
$w4b='C:\Users\Ben\AppData\Local\Temp\sdwin\w4\before.json'
if (Test-Path -LiteralPath $w4b) { $b=[IO.File]::ReadAllBytes($w4b); Add ("w4_before_sha256=" + ([BitConverter]::ToString($sha.ComputeHash($b))).Replace('-','').ToLowerInvariant()) }
$lines | ForEach-Object { Write-Output $_ }
exit 0
