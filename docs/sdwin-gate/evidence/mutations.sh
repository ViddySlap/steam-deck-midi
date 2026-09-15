#!/bin/zsh
R=/tmp/sdwin-gate/mut/repo
RR=/Users/viddyslap/Documents/project-workspaces/steam-deck-midi
PY=$RR/.venv/bin/python
FX=$RR/.showready/fixtures
EDM="$FX/windows-installed/presets/EDM Show.json"
O=/tmp/sdwin-gate/mutations
mkdir -p $O /tmp/sdwin-gate/mutscratch
cd $R
ab() { # name candidate script [extra]
  local name=$1 cand=$2 scr=$3; shift 3
  $PY -B scripts/showready/ab_run.py --candidate $cand --preset "$EDM" --script $scr --fixtures $FX --scratch /tmp/sdwin-gate/mutscratch --speed 50 --out $O/$name.json "$@" > $O/$name.stdout 2> $O/$name.stderr
  echo "$name exit=$?" | tee -a $O/EXITS
}
git checkout -q chain/steamdeck-20260914
$PY -B scripts/showready/deck_script.py --fixtures $FX --out $O/script-clean.json > $O/gen-clean.txt 2>&1; echo "gen-clean exit=$?" | tee -a $O/EXITS
# (a) code mutant in candidate tree
ab a-red mut-a $O/script-clean.json
ab a-green 27e3ad0 $O/script-clean.json
# (a') built-in sensitivity control on an EDM Show note mapping
ab a2-sensitivity-red 27e3ad0 $O/script-clean.json --control sensitivity --mapping BTN_X
# (b) recorder records nothing
cp scripts/showready/capture_runner.py $O/capture_runner.orig
sed -i '' 's/        if not self.dead:/        if False:  # GATE MUTANT b/' scripts/showready/capture_runner.py
grep -c "GATE MUTANT b" scripts/showready/capture_runner.py | sed 's/^/b-applied=/' | tee -a $O/EXITS
ab b-red 27e3ad0 $O/script-clean.json
git checkout -- scripts/showready/capture_runner.py; cmp scripts/showready/capture_runner.py $O/capture_runner.orig && echo b-restored | tee -a $O/EXITS
ab b-green 27e3ad0 $O/script-clean.json
# (c) one Action ID removed from the generated script
sed -i '' 's/^    for action in ids:$/    for action in [i for i in ids if i != "BTN_X"]:  # GATE MUTANT c/' scripts/showready/deck_script.py
grep -c "GATE MUTANT c" scripts/showready/deck_script.py | sed 's/^/c-applied=/' | tee -a $O/EXITS
$PY -B scripts/showready/deck_script.py --fixtures $FX --out $O/script-c.json > $O/gen-c.txt 2>&1; echo "gen-c exit=$?" | tee -a $O/EXITS
ab c-red 27e3ad0 $O/script-c.json
git checkout -- scripts/showready/deck_script.py; git status --porcelain | sed 's/^/porcelain: /' | tee -a $O/EXITS
$PY -B scripts/showready/deck_script.py --fixtures $FX --out $O/script-c-restored.json > $O/gen-c-restored.txt 2>&1; echo "gen-c-restored exit=$?" | tee -a $O/EXITS
ab c-green 27e3ad0 $O/script-c-restored.json
# (f) candidate attempts a real MIDI port open
ab f-red mut-f $O/script-clean.json
ab f-green 27e3ad0 $O/script-clean.json
echo ALLDONE | tee -a $O/EXITS
