#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
F=.showready/fixtures
run() {
  local name=$1; shift
  /usr/bin/env TMPDIR=/tmp/sdwin-gate/abscratch .venv/bin/python -B scripts/showready/ab_run.py --candidate HEAD "$@" --script /tmp/sdwin-gate/deck-script.json --scratch /tmp/sdwin-gate/abscratch --out /tmp/sdwin-gate/results/mac/$name.json > /tmp/sdwin-gate/results/mac/$name.stdout 2> /tmp/sdwin-gate/results/mac/$name.stderr
  echo "$name exit=$?" >> /tmp/sdwin-gate/results/mac/EXITS
}
run mac-edm --preset "$F/mac/presets/EDM Show.json" --section windows &
run mac-ptz --preset "$F/mac/presets/PTZ.json" --section windows &
run mac-default --preset "$F/mac/presets/default.json" &
run win-edm --preset "$F/windows-installed/presets/EDM Show.json" &
run win-ptz --preset "$F/windows-installed/presets/PTZ.json" &
run win-default --preset "$F/windows-installed/presets/default.json" &
run tracked-default --preset config/presets/default.json &
wait
echo ALLDONE >> /tmp/sdwin-gate/results/mac/EXITS
