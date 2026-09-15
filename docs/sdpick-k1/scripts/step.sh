#!/bin/zsh
# step.sh <name> <win_rail args...> ; logs to /tmp/sdpick-k1/logs/<name>.txt
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
name=$1; shift
L=/tmp/sdpick-k1/logs/$name.txt
{ date '+START %Y-%m-%dT%H:%M:%S'; print -r -- "CMD scripts/showready/win_rail.sh $*"; } > $L
scripts/showready/win_rail.sh "$@" >> $L 2>&1
rc=$?
{ echo "RAIL_EXIT $rc"; date '+END %Y-%m-%dT%H:%M:%S'; } >> $L
exit $rc
