#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
scripts/showready/win_rail.sh run wg /tmp/sdwin-gate/ps/winmatrix.ps1 -Batch 1 > /tmp/sdwin-gate/5-winmatrix-b1.txt 2>&1
echo "batch1 exit=$?" >> /tmp/sdwin-gate/WINEXITS
scripts/showready/win_rail.sh run wg /tmp/sdwin-gate/ps/winmatrix.ps1 -Batch 2 > /tmp/sdwin-gate/5-winmatrix-b2.txt 2>&1
echo "batch2 exit=$?" >> /tmp/sdwin-gate/WINEXITS
echo ALLDONE >> /tmp/sdwin-gate/WINEXITS
