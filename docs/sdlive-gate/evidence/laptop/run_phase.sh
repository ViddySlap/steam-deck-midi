#!/bin/zsh
# run_phase.sh <phase> <logname> [extra args]
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
phase=$1; logf=/tmp/sdlive-gate/laptop/$2; shift 2
date '+START %Y-%m-%dT%H:%M:%S' > $logf
scripts/showready/win_rail.sh run sdlive-gate /tmp/sdlive-gate/laptop/timing.ps1 -Phase $phase "$@" >> $logf 2>&1
echo "RAIL_EXIT $?" >> $logf
date '+END %Y-%m-%dT%H:%M:%S' >> $logf
