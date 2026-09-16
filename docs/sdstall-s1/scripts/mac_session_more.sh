#!/bin/zsh
# sdstall S1: CONTINUATION of an existing Mac session, in the SAME session window
# and the SAME scratch/work directories, so the census still sees ONE session.
#   mac_session_more.sh <session> <base-target> <head-target> <first-arm-number> <max-extra-per-rev>
#
# Difference from mac_session.sh, declared in the report: this runner waits for
# load1 < 4.0 (instantaneous, cap QUIET_CAP seconds) IMMEDIATELY BEFORE each arm.
# The EXTENDED LOAD VALIDITY's own remedy for an INVALID arm is "wait until load1
# < 4.0 ... then start a FRESH run"; applying that gate per arm stops this Mac's
# background housekeeping (mds_stores, mobileassetd, fseventsd, iCloud) from
# burning the arm budget. It makes arms MORE likely to satisfy the cap, never
# less, and the cap itself is unchanged.
set -u
R=/Users/viddyslap/Documents/project-workspaces/steam-deck-midi
S=$R/docs/sdstall-s1/scripts
SESS=$1; TB=$2; TH=$3; FIRST=$4; MAXX=$5
QUIET_CAP=240
BASE=70cebd0b6baed2ece86a2d218843e02b6298789d
HEAD=e2919763fe9174fe0fe44e2782f4279895cf0434
O=/tmp/sdstall/$SESS
mkdir -p $O/watch
cd $R
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a $O/session.log; }

rm -f $O/STOP $O/DONE
.venv/bin/python -B $S/machine_sampler.py --out $O/samples.jsonl --lane-root $$ --stop $O/STOP &
SAMPLER=$!
log "CONTINUATION $SESS start; sampler pid $SAMPLER; driver pid $$; targets base=$TB head=$TH from arm $FIRST"

wait_quiet_now() {
  local t0=$(date +%s)
  while true; do
    L=$(sysctl -n vm.loadavg | awk '{print $2}')
    if (( L < 4.0 )); then log "  quiet: load1 $L"; return 0; fi
    if (( $(date +%s) - t0 >= QUIET_CAP )); then log "  quiet cap reached at load1 $L; running anyway"; return 1; fi
    sleep 5
  done
}

typeset -A OK; OK[base]=0; OK[head]=0
typeset -A TGT; TGT[base]=$TB; TGT[head]=$TH
typeset -A TRIED; TRIED[base]=0; TRIED[head]=0
N=$(( FIRST - 1 ))
while (( OK[base] < TGT[base] || OK[head] < TGT[head] )); do
  for REV in base head; do
    (( OK[$REV] >= TGT[$REV] )) && continue
    (( TRIED[$REV] >= MAXX )) && continue
    N=$((N+1)); TRIED[$REV]=$(( TRIED[$REV] + 1 ))
    [[ $REV == base ]] && SHA=$BASE || SHA=$HEAD
    [[ $REV == base ]] && TREE=/tmp/sdstall/base-70cebd0 || TREE=/tmp/sdstall/head-e291976
    LBL=$(printf "%s-a%02d-%s" $SESS $N $REV)
    SCR=$TREE/$SESS
    WRK=$SCR/timing-$SESS
    wait_quiet_now
    log "ARM $N rev=$REV sha=${SHA:0:7} label=$LBL"
    WATCH="[\"$R/.venv/bin/python\",\"-B\",\"$S/arm_watch.py\",\"--armdir\",\"{armdir}\",\"--label\",\"$LBL\",\"--out\",\"$O/watch\",\"--stack-budget-file\",\"$O/stack-budget-$REV\",\"--stack-budget\",\"10\"]"
    .venv/bin/python -B $S/closed_only.py --candidate $SHA --script scripts/showready/timing_script.json \
      --scratch $SCR --work $WRK --out $O/$LBL.json.gz --valid-target 1 --max-arms 1 --first-repeat $N \
      --watch-cmd "$WATCH" >> $O/$LBL.stdout 2>&1
    EX=$?
    V=$(.venv/bin/python -B - "$O/samples.jsonl" "$WRK/r$N-CLOSED-try1" <<'PYV'
import json,sys
from pathlib import Path
s,d=Path(sys.argv[1]),Path(sys.argv[2])
try:
    st=(d/'start').stat().st_mtime
    en=max(p.stat().st_mtime for p in d.rglob('*') if p.is_file())
    rows=[json.loads(l) for l in s.read_text().splitlines() if l.strip()]
    w=[r for r in rows if st<=r['t']<=en]
    print(0 if (w and not [r for r in w if r['load1']>5.0]) else 1)
except Exception:
    print(1)
PYV
)
    log "ARM $N exit $EX provisional validity $V"
    if (( EX == 0 && V == 0 )); then OK[$REV]=$(( OK[$REV] + 1 )); fi
    log "COUNT extra base=${OK[base]}/${TGT[base]} head=${OK[head]}/${TGT[head]} tried base=${TRIED[base]} head=${TRIED[head]}"
  done
  if (( TRIED[base] >= MAXX && TRIED[head] >= MAXX )); then log "MAX EXTRA reached"; break; fi
done
for REV in base head; do
  [[ $REV == base ]] && TREE=/tmp/sdstall/base-70cebd0 || TREE=/tmp/sdstall/head-e291976
  if [[ -d $TREE/$SESS ]]; then
    .venv/bin/python -B $S/arm_validity.py $TREE/$SESS $O/samples.jsonl > $O/validity-$REV.txt 2>&1
    log "FINAL validity $REV exit $? $(tail -1 $O/validity-$REV.txt)"
  fi
done
log "CONTINUATION $SESS end extra base=${OK[base]} head=${OK[head]}"
touch $O/STOP $O/DONE2
wait $SAMPLER 2>/dev/null
