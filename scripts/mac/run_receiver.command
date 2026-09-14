#!/bin/bash
# STEAMDECK MIDI Receiver - macOS launcher (M3 node, specs/mac-rollout.md)
# Double-click to start the bridge. The Terminal window stays open as the live log.

# 1. Configuration
# Resolve the repo root from this script's own location (scripts/mac -> repo root) so
# the launcher works from any clone path. Symlinks are followed, so a Dock alias or a
# ~/bin symlink still resolves back to the real checkout.
SOURCE="${BASH_SOURCE[0]}"
while [ -L "$SOURCE" ]; do
    LINK_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
    SOURCE="$(readlink "$SOURCE")"
    case "$SOURCE" in
        /*) ;;
        *) SOURCE="$LINK_DIR/$SOURCE" ;;
    esac
done
SCRIPT_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
PROJECT_DIR="$(cd -P "$SCRIPT_DIR/../.." && pwd)"

LOG_FILE="$PROJECT_DIR/logs/bridge.log"
UI_URL="http://127.0.0.1:7723"

# 2. Log setup (ensure dir exists)
mkdir -p "$(dirname "$LOG_FILE")"

echo "Starting STEAMDECK MIDI Receiver..."
echo "Target: $PROJECT_DIR"
echo "Log:    $LOG_FILE"
echo "UI:     $UI_URL"
echo "--------------------------------------------------"

# 3. Move into the repo so local imports and the venv resolve correctly
cd "$PROJECT_DIR" || { echo "ERROR: project dir not found: $PROJECT_DIR"; read -r; exit 1; }

# 4. Open the web UI a few seconds after launch (backgrounded so it does not block the bridge)
( sleep 3 && open "$UI_URL" ) &

# 5. Activate the venv and run the bridge with the full macOS IAC Driver port names.
#    Do NOT use --tray on macOS (windows/tray.py imports ctypes.wintypes). tee mirrors output to the log.
source .venv/bin/activate
# Read the same machine-local setting as direct bridge startup. Keep it one
# argv element even when the section name contains spaces.
SECTION_ARGS=()
if [ -f config/bridge.local.json ]; then
    PRESET_SECTION=$(python -c 'from pathlib import Path; from windows.bridge_settings import BridgeSettings; print(BridgeSettings.load(Path("config/bridge.local.json")).preset_section or "")') || exit 1
    if [ -n "$PRESET_SECTION" ]; then
        SECTION_ARGS=(--preset-section "$PRESET_SECTION")
    fi
fi
python -m windows.win_recv "${SECTION_ARGS[@]}" \
    --listen 0.0.0.0:45123 \
    --map config/windows_midi_map.json \
    --midi-port "IAC Driver DECK_IN" \
    --feedback-port "IAC Driver DECK_OUT" \
    --pulse-port "IAC Driver PULSE_OUT" \
    --timeout 2.0 \
    --ui-port 7723 2>&1 | tee -a "$LOG_FILE"

echo ""
echo "--------------------------------------------------"
echo "Process exited. Press [Enter] to close this window."
echo "--------------------------------------------------"
read -r
