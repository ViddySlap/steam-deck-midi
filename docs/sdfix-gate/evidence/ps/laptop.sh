#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
L=/tmp/sdfix-gate/laptop; mkdir -p $L; R=scripts/showready/win_rail.sh; W='C:\Users\Ben\AppData\Local\Temp\sdwin\ug'
step() { n=$1; shift; echo "== $n $(date '+%H:%M:%S') :: $*" >> $L/STEPS; "$@" > $L/$n.txt 2>&1; c=$?; echo "$n exit=$c $(date '+%H:%M:%S')" >> $L/STEPS; return $c; }
step 0-guard-snapshot $R run ug scripts/showready/win_guard.ps1 -Mode snapshot -Out "$W\\before.json" || { step 9-guard-compare $R run ug scripts/showready/win_guard.ps1 -Mode compare -Baseline "$W\\before.json" -Out "$W\\after.json"; echo STOPPED >> $L/STEPS; exit 1; }
step 1-inventory-pre $R run ug /tmp/sdfix-gate/ps/inventory.ps1
if step 2-pins $R run ug /tmp/sdfix-gate/ps/pins.ps1; then
  step 3-winmatrix $R run ug /tmp/sdfix-gate/ps/winmatrix.ps1
  step 4-suite $R run ug /tmp/sdfix-gate/ps/suite.ps1 -Label suite
  step 5-inventory-post $R run ug /tmp/sdfix-gate/ps/inventory.ps1
  for n in win-edm win-ptz win-default; do
    step 6-get-$n.gz $R get "$W\\results\\$n.json.gz" $L/$n.json.gz || step 6-get-$n $R get "$W\\results\\$n.json" $L/$n.json
  done
  step 7-get-before $R get "$W\\before.json" $L/before.json
fi
step 9-guard-compare $R run ug scripts/showready/win_guard.ps1 -Mode compare -Baseline "$W\\before.json" -Out "$W\\after.json"
echo ALLDONE >> $L/STEPS
