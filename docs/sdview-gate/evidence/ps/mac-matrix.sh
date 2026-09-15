#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
G=/tmp/sdview-gate/ab
.venv/bin/python -B scripts/showready/deck_script.py --out $G/deck-script.json > $G/script.log 2>&1
echo "script exit $?" > $G/EXITS
run() { n=$1; shift; TMPDIR=$G/tmp-$n .venv/bin/python -B scripts/showready/ab_run.py --candidate b38ffb23c3d9bfb78f8fc2337abe61cb00336907 "$@" --script $G/deck-script.json --scratch $G/scr-$n --out $G/mac-$n.json > $G/mac-$n.log 2>&1; echo "$n exit $?" >> $G/EXITS; }
mkdir -p $G/tmp-edm $G/tmp-ptz $G/tmp-default
run edm --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows &
run ptz --preset '.showready/fixtures/mac/presets/PTZ.json' --section windows &
run default --preset '.showready/fixtures/mac/presets/default.json' &
wait
echo "ALL DONE" >> $G/EXITS
