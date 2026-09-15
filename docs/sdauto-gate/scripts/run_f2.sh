#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
W=/tmp/sdauto-gate/win
R=scripts/showready/win_rail.sh
for f in win_f2.py win_ctrl.py; do $R put sdauto-gate $W/f2/$f; echo "put $f $?" >> $W/L07-f2-status.txt; done
i=0
for spec in "head 47311 17311 g1 -EnableCtrlC" "v049 47312 17312 g2 -EnableCtrlC" "head 47313 17313 g3" "v049 47314 17314 g4"; do
  i=$((i+1)); parts=(${=spec})
  echo "START ${parts[1]} ${parts[4]} $(date +%T)" >> $W/L07-f2-status.txt
  $R run sdauto-gate $W/f2/f2.ps1 -Which ${parts[1]} -Udp ${parts[2]} -Ui ${parts[3]} -Run ${parts[4]} ${parts[5]} > $W/L07-f2-${parts[1]}-${parts[4]}.txt 2>&1
  echo "END ${parts[1]} ${parts[4]} RAIL_EXIT $? $(date +%T)" >> $W/L07-f2-status.txt
done
echo "START tray_cpu $(date +%T)" >> $W/L07-f2-status.txt
$R run sdauto-gate $W/f2/tray_cpu.ps1 -Seconds 60 > $W/L08-tray-cpu.txt 2>&1
echo "END tray_cpu RAIL_EXIT $? $(date +%T)" >> $W/L07-f2-status.txt
echo ALLDONE >> $W/L07-f2-status.txt
