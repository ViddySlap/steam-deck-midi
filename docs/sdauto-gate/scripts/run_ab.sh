#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
echo "START $(date +%T)" > /tmp/sdauto-gate/win/L04-ab.txt
scripts/showready/win_rail.sh run sdauto-gate /tmp/sdauto-gate/win/ab.ps1 >> /tmp/sdauto-gate/win/L04-ab.txt 2>&1
echo "RAIL_EXIT $? $(date +%T)" >> /tmp/sdauto-gate/win/L04-ab.txt
