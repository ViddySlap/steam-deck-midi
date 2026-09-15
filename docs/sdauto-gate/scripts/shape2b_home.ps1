# sdauto gate 2b: READ-ONLY. Does the installed factory osc_preset_path equal USERPROFILE joined with HEAD's suffix? Booleans only.
param([string]$HeadSuffix)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$j=Get-Content -LiteralPath 'C:\Program Files\STEAMDECK MIDI Receiver 2\config\engines.factory\osc_sync.json' -Raw | ConvertFrom-Json
$installed=([string]$j.osc_preset_path) -replace '\\','/'
$joined=((Join-Path $env:USERPROFILE ($HeadSuffix -replace '/','\')) -replace '\\','/')
Write-Output ("equals_userprofile_join: {0}" -f ([string]($installed -ieq $joined)).ToLowerInvariant())
Write-Output ("joined_exists: {0}" -f (Test-Path -LiteralPath ($joined -replace '/','\')))
$tray=@(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'STEAMDECK-MIDI-RECEIVER-2*' })
foreach ($t in $tray) { $o=Invoke-CimMethod -InputObject $t -MethodName GetOwner; Write-Output ("tray_pid {0} owner_is_rail_user: {1}" -f $t.ProcessId, ([string]($o.User -ieq $env:USERNAME)).ToLowerInvariant()) }
exit 0
