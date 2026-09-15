#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
G=/tmp/sdfix-gate/ab
.venv/bin/python -B scripts/showready/deck_script.py --out $G/deck-script.json > $G/script.log 2>&1
echo "script exit $?" > $G/EXITS
run() { n=$1; shift; TMPDIR=$G/tmp-$n .venv/bin/python -B scripts/showready/ab_run.py --candidate 19cd48e0dd6e8d36126812c5e687504928e4fcbd "$@" --script $G/deck-script.json --scratch $G/scr-$n --out $G/mac-$n.json > $G/mac-$n.log 2>&1; echo "$n exit $?" >> $G/EXITS; }
mkdir -p $G/tmp-edm $G/tmp-ptz $G/tmp-default $G/scr-edm $G/scr-ptz $G/scr-default
run edm --preset '.showready/fixtures/mac/presets/EDM Show.json' --section windows &
run ptz --preset '.showready/fixtures/mac/presets/PTZ.json' --section windows &
run default --preset '.showready/fixtures/mac/presets/default.json' &
wait
echo "ALL DONE" >> $G/EXITS
