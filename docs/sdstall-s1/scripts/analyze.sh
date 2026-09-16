#!/bin/zsh
# sdstall S1: the whole post-hoc analysis, in one command.
# MASTER 13, 17:02 (6): this NEVER runs while an arm is running. Call it after a
# session's last arm, or while the only work in flight is on the laptop.
#   analyze.sh <session> [<session> ...]
set -u
R=/Users/viddyslap/Documents/project-workspaces/steam-deck-midi
S=$R/docs/sdstall-s1/scripts
E=$R/docs/sdstall-s1/evidence
PRESET=$R/.showready/fixtures/mac/presets/EDM\ Show.json
cd $R
mkdir -p $E/classify
echo "ANALYZE start $(date '+%H:%M:%S') load1=$(sysctl -n vm.loadavg)"

# 1. Per-arm artefact classification (MASTER 17:02 (1) first, Recv-Q beside it).
for SESS in "$@"; do
  for f in /tmp/sdstall/$SESS/*-a*.json.gz; do
    [[ -e $f ]] || continue
    LBL=$(basename $f .json.gz)
    N=$(echo $LBL | sed -n 's/.*-a\([0-9][0-9]\)-.*/\1/p' | sed 's/^0//')
    REV=$(echo $LBL | sed -n 's/.*-a[0-9][0-9]-\(.*\)/\1/p')
    [[ $REV == base ]] && TREE=/tmp/sdstall/base-70cebd0 || TREE=/tmp/sdstall/head-e291976
    ARMDIR=$TREE/$SESS/timing-$SESS/r$N-CLOSED-try1
    .venv/bin/python -B $S/stall_classify.py --result $f --label $LBL \
      --armdir $ARMDIR --recvq /tmp/sdstall/$SESS/watch/$LBL.recvq.jsonl \
      --preset "$PRESET" --out $E/classify/$LBL.json >> $E/classify/classify.log 2>&1
  done
done

# 2. The authoritative census, from the raw files only.
ARGS=()
for SESS in "$@"; do ARGS+=(--session $SESS --dir /tmp/sdstall/$SESS); done
.venv/bin/python -B $S/census.py "${ARGS[@]}" --out $E/census.json

# 3. Render the report tables.
.venv/bin/python -B $S/report_tables.py --census $E/census.json \
  --classify "$E/classify/*-a*.json" --out $E/tables.md
echo "ANALYZE end $(date '+%H:%M:%S') load1=$(sysctl -n vm.loadavg)"
