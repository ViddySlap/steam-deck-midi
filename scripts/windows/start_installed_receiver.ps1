param(
    [string]$InstallRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($InstallRoot)) {
    $InstallRoot = Split-Path -Parent $PSScriptRoot
} else {
    $InstallRoot = (Resolve-Path $InstallRoot).Path
}

$exePath = Join-Path $InstallRoot "STEAMDECK-MIDI-RECEIVER.exe"
if (-not (Test-Path $exePath)) {
    throw "Receiver executable not found at '$exePath'."
}

$settingsPath = Join-Path $InstallRoot "config\windows_receiver_settings.local.json"
$exampleSettingsPath = Join-Path $InstallRoot "config\windows_receiver_settings.example.json"
if (-not (Test-Path $exampleSettingsPath)) {
    throw "Receiver default settings file not found at '$exampleSettingsPath'."
}

$defaultSettings = Get-Content $exampleSettingsPath -Raw | ConvertFrom-Json
$settings = $null
if (Test-Path $settingsPath) {
    $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json
} else {
    $settings = [pscustomobject]@{}
}

$settingsUpdated = $false
foreach ($property in $defaultSettings.PSObject.Properties) {
    if ($settings.PSObject.Properties.Name -contains $property.Name) {
        continue
    }
    Add-Member -InputObject $settings -MemberType NoteProperty -Name $property.Name -Value $property.Value
    $settingsUpdated = $true
}

if ($settingsUpdated -or -not (Test-Path $settingsPath)) {
    $settings | ConvertTo-Json -Depth 10 | Set-Content -Path $settingsPath -Encoding UTF8
}

$mapPath = Join-Path $InstallRoot $settings.map_path
if (-not (Test-Path $mapPath)) {
    throw "MIDI map file not found at '$mapPath'."
}

$args = @(
    "--listen",
    [string]$settings.listen,
    "--map",
    $mapPath,
    "--midi-port",
    [string]$settings.midi_port,
    "--timeout",
    [string]$settings.timeout
)

if ($settings.verbose) {
    $args += "--verbose"
}
if ($settings.PSObject.Properties.Name -contains "feedback_port" -and -not [string]::IsNullOrWhiteSpace([string]$settings.feedback_port)) {
    $args += "--feedback-port"
    $args += [string]$settings.feedback_port
}

Write-Host "STEAMDECK MIDI Receiver"
Write-Host "Install:   $InstallRoot"
Write-Host "Settings:  $settingsPath"
Write-Host "Map:       $mapPath"
Write-Host "MIDI port: $($settings.midi_port)"
if ($settings.PSObject.Properties.Name -contains "feedback_port" -and -not [string]::IsNullOrWhiteSpace([string]$settings.feedback_port)) {
    Write-Host "Feedback:  $($settings.feedback_port)"
}
Write-Host ""

Push-Location $InstallRoot
try {
    $checkArgs = @("--check-midi-port", "--midi-port", [string]$settings.midi_port)
    if ($settings.PSObject.Properties.Name -contains "feedback_port" -and -not [string]::IsNullOrWhiteSpace([string]$settings.feedback_port)) {
        $checkArgs += "--feedback-port"
        $checkArgs += [string]$settings.feedback_port
    }
    & $exePath @checkArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Configured MIDI port check failed."
        Write-Host "Install loopMIDI, create DECK_IN and DECK_OUT ports, then relaunch the receiver."
        exit $LASTEXITCODE
    }

    & $exePath @args
} finally {
    Pop-Location
}
