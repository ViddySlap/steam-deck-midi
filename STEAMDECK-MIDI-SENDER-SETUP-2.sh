#!/usr/bin/env bash
set -euo pipefail

# Installs or updates the Steam Deck sender as v3: ~/steam-deck-midi-v3,
# buttons read straight from the controller (button_source hidraw, ADR 0003),
# one "Steamdeck Midi Sender 3" launcher. Local settings and bindings are never
# deleted: anything that is not a clean git checkout of this repo is moved
# aside and its config copied back. The directories can be overridden for a
# dry run or an offline install (STEAMDECK_MIDI_REPO_URL, STEAMDECK_MIDI_INSTALL_DIR, STEAMDECK_MIDI_APPLICATIONS_DIR,
# STEAMDECK_MIDI_DESKTOP_DIR).

REPO_URL="${STEAMDECK_MIDI_REPO_URL:-https://github.com/ViddySlap/steam-deck-midi.git}"
INSTALL_DIR="${STEAMDECK_MIDI_INSTALL_DIR:-${HOME}/steam-deck-midi-v3}"
APPLICATIONS_DIR="${STEAMDECK_MIDI_APPLICATIONS_DIR:-${HOME}/.local/share/applications}"
DESKTOP_DIR="${STEAMDECK_MIDI_DESKTOP_DIR:-${HOME}/Desktop}"
SEND_NAME="Steamdeck Midi Sender 3"
SEND_DESKTOP="${APPLICATIONS_DIR}/steamdeck-midi-sender-3.desktop"
SEND_ICON_PATH="${INSTALL_DIR}/assets/deck/sender-icon.png"
LOCAL_CONFIG_FILES=(
  "config/deck_runtime_settings.local.json"
  "config/deck_bindings.json"
)

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

# Move an install we can't update in place aside, clone fresh, and carry the
# local config over. Nothing is deleted; the old tree stays next to the new one.
reinstall_keeping_config() {
  local backup="${INSTALL_DIR}.bak-$(date +%Y%m%d-%H%M%S)"
  echo "Moving the existing install aside: ${backup}"
  mv "${INSTALL_DIR}" "${backup}"
  git clone "${REPO_URL}" "${INSTALL_DIR}"
  local rel
  for rel in "${LOCAL_CONFIG_FILES[@]}"; do
    if [[ -f "${backup}/${rel}" ]]; then
      cp -p "${backup}/${rel}" "${INSTALL_DIR}/${rel}"
      echo "Kept ${rel}"
    fi
  done
}

require_command git
require_command python3

mkdir -p "${APPLICATIONS_DIR}" "${DESKTOP_DIR}"

if [[ -d "${INSTALL_DIR}/.git" ]] && git -C "${INSTALL_DIR}" pull --ff-only; then
  :
elif [[ -e "${INSTALL_DIR}" ]]; then
  # Not a git checkout (hand-deployed), or its history no longer matches.
  reinstall_keeping_config
else
  git clone "${REPO_URL}" "${INSTALL_DIR}"
fi

# New installs read buttons from the controller (hidraw). An existing local
# settings file is left exactly as it is.
if [[ ! -f "${INSTALL_DIR}/config/deck_runtime_settings.local.json" ]]; then
  cp \
    "${INSTALL_DIR}/config/deck_runtime_settings.example.json" \
    "${INSTALL_DIR}/config/deck_runtime_settings.local.json"
fi

icon_value="applications-games"
if [[ -f "${SEND_ICON_PATH}" ]]; then
  icon_value="${SEND_ICON_PATH}"
fi

cat >"${SEND_DESKTOP}" <<EOF
[Desktop Entry]
Categories=Utility;
Comment=Steam Deck MIDI sender v3: buttons read straight from the controller (hidraw)
Exec=${INSTALL_DIR}/scripts/deck/run_sender.sh
Icon=${icon_value}
Name[en_US]=${SEND_NAME}
Name=${SEND_NAME}
Terminal=true
Type=Application
Version=1.0
EOF
chmod +x "${SEND_DESKTOP}"
cp "${SEND_DESKTOP}" "${DESKTOP_DIR}/${SEND_NAME}.desktop"
chmod +x "${DESKTOP_DIR}/${SEND_NAME}.desktop"

echo ""
echo "Steam Deck install complete."
echo "Repo: ${INSTALL_DIR}"
echo "Desktop launcher: ${SEND_NAME}"
echo ""
echo "Buttons come straight from the controller (button_source: hidraw), so"
echo "no Steam Input key bindings or learn step are needed."
