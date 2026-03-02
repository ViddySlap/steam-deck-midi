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

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher for Windows ('py') was not found. Install Python 3.12 first."
}

$pythonCheck = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 is required. Install it, then rerun this build."
}

$venvPath = Join-Path $RepoRoot ".venv-build"
if (-not (Test-Path $venvPath)) {
    Write-Host "Creating build virtual environment..."
    & py -3.12 -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create build virtual environment."
    }
}

$venvPython = Join-Path $venvPath "Scripts\python.exe"
$specPath = Join-Path $RepoRoot "steam-deck-vj-receiver.spec"

Write-Host "Installing build dependencies..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip."
}
& $venvPython -m pip install -r (Join-Path $RepoRoot "requirements-build.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install build dependencies."
}

Push-Location $RepoRoot
try {
    Write-Host "Building executable..."
    & $venvPython -m PyInstaller --clean --noconfirm $specPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed."
    }
} finally {
    Pop-Location
}

$distDir = Join-Path $RepoRoot "dist"
$exePath = Join-Path $distDir "steam-deck-vj-receiver.exe"

Write-Host ""
Write-Host "Build complete."
Write-Host "Dist directory: $distDir"
Write-Host "Executable:     $exePath"
Write-Host ""
Write-Host "Example run:"
Write-Host ".\dist\steam-deck-vj-receiver.exe --map .\config\windows_midi_map.json --midi-port `"DECK_IN`" --verbose"
