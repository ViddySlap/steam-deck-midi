#!/bin/zsh
# sdstall S1 item a: one Mac session of interleaved BASE/HEAD CLOSED arms.
#   mac_session.sh <session-name> <valid-target> <max-arms-per-revision>
# Alternates BASE, HEAD, BASE, HEAD ... one arm per closed_only.py invocation, so
# the two revisions really interleave in time. Each REVISION gets ONE scratch and
# ONE extracted candidate tree, reused by all of its arms through --work: the
# pinned instrument builds one tree per run too, and extracting a fresh tree per
# arm made Spotlight (fseventsd + mds_stores) drive load1 from 2.2 to 13.5 and
# INVALIDATE every arm. arm_validity.py is then run ONCE per revision at the end
# over that revision's single timing-* directory.
# Stops when BOTH revisions have <valid-target> accepted arms, or max-arms each.
# Never voids the session on an INVALID arm: the raw files are kept and the arm
# is simply not counted (declared divergence from sdauto AG's void-the-run rule).
set -u
R=/Users/viddyslap/Documents/project-workspaces/steam-deck-midi
S=$R/docs/sdstall-s1/scripts
SESS=$1; TARGET=$2; MAXA=$3
BASE=70cebd0b6baed2ece86a2d218843e02b6298789d
HEAD=e2919763fe9174fe0fe44e2782f4279895cf0434
O=/tmp/sdstall/$SESS
mkdir -p $O/watch
touch /tmp/sdstall/.metadata_never_index $O/.metadata_never_index
cd $R
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a $O/session.log; }

.venv/bin/python -B $S/machine_sampler.py --out $O/samples.jsonl --lane-root $$ --stop $O/STOP &
SAMPLER=$!
log "SESSION $SESS start; sampler pid $SAMPLER; driver pid $$"

# Build BOTH candidate trees BEFORE the quiet gate, so any indexing burst from the
# extraction is over before the first arm is timed. --max-arms 0 runs no arm.
for REV in base head; do
  [[ $REV == base ]] && SHA=$BASE || SHA=$HEAD
  [[ $REV == base ]] && TREE=/tmp/sdstall/base-70cebd0 || TREE=/tmp/sdstall/head-e291976
  log "PREBUILD $REV tree at $TREE/$SESS/timing-$SESS"
  .venv/bin/python -B $S/closed_only.py --candidate $SHA --script scripts/showready/timing_script.json \
    --scratch $TREE/$SESS --work $TREE/$SESS/timing-$SESS --out $O/prebuild-$REV.json.gz \
    --valid-target 1 --max-arms 0 >> $O/prebuild.log 2>&1
  log "PREBUILD $REV exit $? files=$(find $TREE/$SESS/timing-$SESS/candidate -type f 2>/dev/null | wc -l | tr -d ' ')"
done

# Quiet start: load1 < 4.0 for 60 s, 90 min deadline (LOAD RULES / EXTENDED VALIDITY).
DEADLINE=$(( $(date +%s) + 5400 ))
SINCE=0
while true; do
  if (( $(date +%s) > DEADLINE )); then log "BLOCKED: no quiet start before the 90 min deadline"; touch $O/BLOCKED $O/STOP; exit 2; fi
  L=$(sysctl -n vm.loadavg | awk '{print $2}')
  if (( L < 4.0 )); then
    (( SINCE == 0 )) && SINCE=$(date +%s)
    (( $(date +%s) - SINCE >= 60 )) && { log "QUIET load1 < 4.0 for 60 s (now $L)"; break; }
  else SINCE=0; fi
  sleep 5
done

typeset -A OK; OK[base]=0; OK[head]=0
typeset -A TRIED; TRIED[base]=0; TRIED[head]=0
N=0
while (( OK[base] < TARGET || OK[head] < TARGET )); do
  for REV in base head; do
    (( OK[$REV] >= TARGET )) && continue
    (( TRIED[$REV] >= MAXA )) && continue
    N=$((N+1)); TRIED[$REV]=$(( TRIED[$REV] + 1 ))
    [[ $REV == base ]] && SHA=$BASE || SHA=$HEAD
    [[ $REV == base ]] && TREE=/tmp/sdstall/base-70cebd0 || TREE=/tmp/sdstall/head-e291976
    LBL=$(printf "%s-a%02d-%s" $SESS $N $REV)
    SCR=$TREE/$SESS
    WRK=$SCR/timing-$SESS
    log "ARM $N rev=$REV sha=${SHA:0:7} label=$LBL scratch=$SCR work=$WRK"
    WATCH="[\"$R/.venv/bin/python\",\"-B\",\"$S/arm_watch.py\",\"--armdir\",\"{armdir}\",\"--label\",\"$LBL\",\"--out\",\"$O/watch\",\"--stack-budget-file\",\"$O/stack-budget-$REV\",\"--stack-budget\",\"10\"]"
    .venv/bin/python -B $S/closed_only.py --candidate $SHA --script scripts/showready/timing_script.json \
      --scratch $SCR --work $WRK --out $O/$LBL.json.gz --valid-target 1 --max-arms 1 --first-repeat $N \
      --watch-cmd "$WATCH" >> $O/$LBL.stdout 2>&1
    EX=$?
    log "ARM $N exit $EX"
    # Per-arm provisional validity only, from the load1 samples already written.
    # The AUTHORITATIVE validity is arm_validity.py run once per revision at the
    # end of the session (below); heavy scans never run during an arm.
    V=$(.venv/bin/python -B - "$O/samples.jsonl" "$WRK/r$N-CLOSED-try1" <<'PYV'
import json,sys,os
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
    log "ARM $N provisional validity $V"
    if (( EX == 0 && V == 0 )); then OK[$REV]=$(( OK[$REV] + 1 )); fi
    log "COUNT base=${OK[base]}/$TARGET head=${OK[head]}/$TARGET tried base=${TRIED[base]} head=${TRIED[head]}"
  done
  if (( TRIED[base] >= MAXA && TRIED[head] >= MAXA )); then log "MAX ARMS reached"; break; fi
done
for REV in base head; do
  [[ $REV == base ]] && TREE=/tmp/sdstall/base-70cebd0 || TREE=/tmp/sdstall/head-e291976
  if [[ -d $TREE/$SESS ]]; then
    .venv/bin/python -B $S/arm_validity.py $TREE/$SESS $O/samples.jsonl > $O/validity-$REV.txt 2>&1
    log "FINAL validity $REV exit $? $(tail -1 $O/validity-$REV.txt)"
  fi
done
log "SESSION $SESS end base=${OK[base]} head=${OK[head]}"
touch $O/STOP $O/DONE
wait $SAMPLER 2>/dev/null
