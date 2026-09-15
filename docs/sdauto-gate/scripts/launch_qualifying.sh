#!/bin/zsh
until grep -q "CLEAN2 END" /tmp/sdauto-gate/bar3/status.txt; do sleep 10; done
tmux -L sdauto-gate new-session -d -s bar3q /Users/viddyslap/Documents/project-workspaces/steam-deck-midi/docs/sdauto-gate/scripts/bar3_supervised.sh
echo "LAUNCHED bar3q $(date +%T)" >> /tmp/sdauto-gate/bar3/status.txt
