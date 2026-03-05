param(
    [string]$RepoRoot = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
} else {
    $RepoRoot = (Resolve-Path $RepoRoot).Path
}

$pythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python virtual environment not found at '$pythonExe'. Run install-windows.cmd first."
}

$localSettingsPath = Join-Path $RepoRoot "config\windows_receiver_settings.local.json"
$exampleSettingsPath = Join-Path $RepoRoot "config\windows_receiver_settings.example.json"
if (-not (Test-Path $exampleSettingsPath)) {
    throw "Receiver default settings file not found at '$exampleSettingsPath'."
}

$defaultSettings = Get-Content $exampleSettingsPath -Raw | ConvertFrom-Json
$settings = $null
if (Test-Path $localSettingsPath) {
    $settings = Get-Content $localSettingsPath -Raw | ConvertFrom-Json
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

if ($settingsUpdated -or -not (Test-Path $localSettingsPath)) {
    $settings | ConvertTo-Json -Depth 10 | Set-Content -Path $localSettingsPath -Encoding UTF8
}

$settingsPath = $localSettingsPath
$mapPath = Join-Path $RepoRoot $settings.map_path
if (-not (Test-Path $mapPath)) {
    throw "MIDI map file not found at '$mapPath'."
}

$args = @(
    "-m",
    "windows.win_recv",
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

Write-Host "STEAMDECK MIDI receiver"
Write-Host "Repo:     $RepoRoot"
Write-Host "Settings: $settingsPath"
Write-Host "Map:      $mapPath"
Write-Host "Port:     $($settings.midi_port)"
if ($settings.PSObject.Properties.Name -contains "feedback_port" -and -not [string]::IsNullOrWhiteSpace([string]$settings.feedback_port)) {
    Write-Host "Feedback: $($settings.feedback_port)"
}
Write-Host ""

Push-Location $RepoRoot
try {
    & $pythonExe @args
} finally {
    Pop-Location
}
