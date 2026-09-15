#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
date '+START_SENS %Y-%m-%dT%H:%M:%S' > /tmp/sdlive-gate/laptop/L7-edge-sensitivity.txt
scripts/showready/win_rail.sh run sdlive-gate /tmp/sdlive-gate/laptop/timing.ps1 -Phase sensitivity >> /tmp/sdlive-gate/laptop/L7-edge-sensitivity.txt 2>&1
echo "RAIL_EXIT $?" >> /tmp/sdlive-gate/laptop/L7-edge-sensitivity.txt
date '+END_SENS %Y-%m-%dT%H:%M:%S' >> /tmp/sdlive-gate/laptop/L7-edge-sensitivity.txt
date '+START_CLEAN %Y-%m-%dT%H:%M:%S' > /tmp/sdlive-gate/laptop/L8-edge-clean.txt
scripts/showready/win_rail.sh run sdlive-gate /tmp/sdlive-gate/laptop/timing.ps1 -Phase clean >> /tmp/sdlive-gate/laptop/L8-edge-clean.txt 2>&1
echo "RAIL_EXIT $?" >> /tmp/sdlive-gate/laptop/L8-edge-clean.txt
date '+END_CLEAN %Y-%m-%dT%H:%M:%S' >> /tmp/sdlive-gate/laptop/L8-edge-clean.txt
