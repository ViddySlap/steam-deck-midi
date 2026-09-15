#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
L=/tmp/sdlive-gate/laptop
while [ ! -f $L/chain.done ]; do sleep 10; done
/tmp/sdlive-gate/laptop/run_phase.sh ctl10 L21-edge-ctl10.txt
step() { name=$1; shift; date '+START %H:%M:%S' > $L/$name.txt; scripts/showready/win_rail.sh run sdlive-gate "$@" >> $L/$name.txt 2>&1; echo "RAIL_EXIT $?" >> $L/$name.txt; date '+END %H:%M:%S' >> $L/$name.txt; }
step L22-ab /tmp/sdlive-gate/laptop/ab.ps1
step L23-browserfix-red /tmp/sdlive-gate/laptop/browserfix_red.ps1
step L24-flake-head /tmp/sdlive-gate/laptop/flake_gate.ps1 -Which head
step L25-flake-base /tmp/sdlive-gate/laptop/flake_gate.ps1 -Which base
step L26-suite1 /tmp/sdlive-gate/laptop/suite.ps1 -Label gate-suite1
step L27-suite2 /tmp/sdlive-gate/laptop/suite.ps1 -Label gate-suite2
date '+POST_DONE %H:%M:%S' > $L/post.done
