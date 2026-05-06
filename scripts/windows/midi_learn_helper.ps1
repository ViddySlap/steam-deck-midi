param(
    [int]$Channel = 1,         # 1-16 (1-indexed)
    [int]$Cc = 110,            # 0-127
    [int]$Value = 64,          # 0-127
    [int]$Repeats = 30,        # number of pings
    [int]$IntervalMs = 80,     # ms between pings
    [string]$Port = "DECK_IN"
)

# Helper: send a stream of CC pings on DECK_IN so Resolume's MIDI Learn UI
# can capture the channel/CC for binding to a parameter.
#
# Usage:
#   1. In Resolume, right-click the parameter you want to bind (e.g. group's
#      master fader). Choose Shortcuts -> Edit -> Learn (or just hit the keyboard
#      shortcut for "MIDI Learn" while the param is selected).
#   2. Run this helper:  pwsh -File midi_learn_helper.ps1 -Channel 1 -Cc 110
#   3. Resolume captures the CC and creates the binding. Repeat for the next
#      parameter with a different -Cc.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$pyScript = @"
import sys, time
sys.path.insert(0, r'$repoRoot')
from windows.midi import open_midi_output
mo = open_midi_output('$Port', dry_run=False)
ch = $Channel - 1  # convert to mido 0-indexed
print(f'Sending ch{$Channel} (mido ch={ch}) CC $Cc = $Value x $Repeats times', flush=True)
for _ in range($Repeats):
    mo.control_change(ch, $Cc, $Value)
    time.sleep($IntervalMs / 1000.0)
mo.close()
print('done', flush=True)
"@

$tmpFile = New-TemporaryFile
$pyFile = $tmpFile.FullName + ".py"
Set-Content -Path $pyFile -Value $pyScript -Encoding utf8
try {
    & py -3.12 $pyFile
} finally {
    Remove-Item $pyFile -ErrorAction SilentlyContinue
    Remove-Item $tmpFile -ErrorAction SilentlyContinue
}
