$ErrorActionPreference='Continue'
$roots=@('C:\Users\Ben\Documents\project-workspaces','C:\Users\Ben\AppData\Roaming\npm','C:\Program Files\nodejs\node_modules','C:\Users\Ben\AppData\Local\npm-cache')
foreach ($r in $roots) {
  if (-not (Test-Path -LiteralPath $r)) { Write-Output "ROOT_ABSENT $r"; continue }
  Get-ChildItem -LiteralPath $r -Directory -Recurse -Depth 6 -Filter 'playwright-core' -ErrorAction SilentlyContinue | ForEach-Object {
    $pkg=Join-Path $_.FullName 'package.json'
    if (Test-Path -LiteralPath $pkg) { $v=(Get-Content -Raw -LiteralPath $pkg | ConvertFrom-Json).version; Write-Output "FOUND $($_.FullName) $v" }
  }
}
Write-Output 'DONE'
exit 0
