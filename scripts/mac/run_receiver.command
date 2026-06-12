#!/bin/bash
# STEAMDECK MIDI Receiver - macOS launcher (M3 node, specs/mac-rollout.md)
# Double-click to start the bridge. The Terminal window stays open as the live log.

# 1. Configuration
PROJECT_DIR="/Users/viddyslap/Documents/project-workspaces/steam-deck-midi"
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
python -m windows.win_recv \
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
