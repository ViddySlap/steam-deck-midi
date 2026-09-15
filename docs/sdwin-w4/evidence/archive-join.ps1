Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
git --no-optional-locks -C 'C:\Users\Ben\Documents\project-workspaces\steam-deck-midi' archive --format=tar --output=C:\Users\Ben\AppData\Local\Temp\sdwin\w4\installed-join.tar d136787 -- config/engines.factory/osc_sync.json windows/engines/osc_sync.py windows/engines/stageflow_bridge.py
exit $LASTEXITCODE
