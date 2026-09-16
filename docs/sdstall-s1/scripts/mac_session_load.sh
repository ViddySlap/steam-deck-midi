#!/bin/zsh
# sdstall S1 THIRD session, DIAGNOSTIC-UNDER-LOAD (MASTER 13, 17:39).
#   mac_session_load.sh <arms-per-revision> <first-arm-number>
#
# PRECONDITION, checked here and recorded: a local-LLM workload must already be
# ACTIVE. This link NEVER starts one: it never loads, unloads, stops or
# reconfigures an LM Studio model or server, and `lms ps` is the only lms verb it
# runs. If nothing is active the script records that and exits 9 without running
# an arm.
#
# Differences from the counted sessions, all declared by MASTER 13 at 17:39:
#   - NO quiet gate. Arms are EXPECTED to be INVALID under the load cap and are
#     never counted toward any R >= 8 floor.
#   - Fine sampling ARMED FROM THE FIRST ARM (--fine-always), not at the 200 ms
#     trigger, so an lms STATUS and a vm_stat sample exist every 0.5 s throughout.
#   - >= 4 arms per revision, same ABAB interleave, BASE and HEAD.
# Its single question: does an M_bridge sample over 1,000 ms REAPPEAR under load,
# does it pass the 17:02 artefact test, and what does Recv-Q say at t3.
set -u
R=/Users/viddyslap/Documents/project-workspaces/steam-deck-midi
S=$R/docs/sdstall-s1/scripts
SESS=s3load
N_PER=$1; FIRST=$2
BASE=70cebd0b6baed2ece86a2d218843e02b6298789d
HEAD=e2919763fe9174fe0fe44e2782f4279895cf0434
O=/tmp/sdstall/$SESS
mkdir -p $O/watch
touch /tmp/sdstall/.metadata_never_index $O/.metadata_never_index
cd $R
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a $O/session.log; }

# PRECONDITION. READ-ONLY.
~/.lmstudio/bin/lms ps > $O/lms-precheck.txt 2>&1
LMS_ACTIVE=$(grep -c PROCESSINGPROMPT $O/lms-precheck.txt || true)
PROC_ACTIVE=$(ps -A -o pcpu=,command= | grep -iE "qwen-bench|local-LLM-" | grep -v grep | awk '$1 > 20.0' | wc -l | tr -d ' ')
log "PRECHECK lms PROCESSINGPROMPT rows=$LMS_ACTIVE local-LLM procs over 20pc=$PROC_ACTIVE"
cat $O/lms-precheck.txt | sed 's/^/  /' >> $O/session.log
if (( LMS_ACTIVE == 0 && PROC_ACTIVE == 0 )); then
  log "PRECONDITION NOT MET: no local-LLM workload is active. This link never starts one. Exiting without running an arm."
  touch $O/NOT-RUN
  exit 9
fi

.venv/bin/python -B $S/machine_sampler.py --out $O/samples.jsonl --lane-root $$ --stop $O/STOP &
SAMPLER=$!
log "SESSION $SESS start (DIAGNOSTIC-UNDER-LOAD); sampler pid $SAMPLER; driver pid $$"

for REV in base head; do
  [[ $REV == base ]] && SHA=$BASE || SHA=$HEAD
  [[ $REV == base ]] && TREE=/tmp/sdstall/base-70cebd0 || TREE=/tmp/sdstall/head-e291976
  .venv/bin/python -B $S/closed_only.py --candidate $SHA --script scripts/showready/timing_script.json \
    --scratch $TREE/$SESS --work $TREE/$SESS/timing-$SESS --out $O/prebuild-$REV.json.gz \
    --valid-target 1 --max-arms 0 >> $O/prebuild.log 2>&1
  log "PREBUILD $REV exit $?"
done

N=$(( FIRST - 1 ))
for i in $(seq 1 $N_PER); do
  for REV in base head; do
    N=$((N+1))
    [[ $REV == base ]] && SHA=$BASE || SHA=$HEAD
    [[ $REV == base ]] && TREE=/tmp/sdstall/base-70cebd0 || TREE=/tmp/sdstall/head-e291976
    LBL=$(printf "%s-a%02d-%s" $SESS $N $REV)
    log "ARM $N rev=$REV label=$LBL load1=$(sysctl -n vm.loadavg | awk '{print $2}')"
    WATCH="[\"$R/.venv/bin/python\",\"-B\",\"$S/arm_watch.py\",\"--armdir\",\"{armdir}\",\"--label\",\"$LBL\",\"--out\",\"$O/watch\",\"--stack-budget-file\",\"$O/stack-budget-$REV\",\"--stack-budget\",\"10\",\"--fine-always\"]"
    .venv/bin/python -B $S/closed_only.py --candidate $SHA --script scripts/showready/timing_script.json \
      --scratch $TREE/$SESS --work $TREE/$SESS/timing-$SESS --out $O/$LBL.json.gz \
      --valid-target 1 --max-arms 1 --first-repeat $N --watch-cmd "$WATCH" >> $O/$LBL.stdout 2>&1
    log "ARM $N exit $?"
  done
done
for REV in base head; do
  [[ $REV == base ]] && TREE=/tmp/sdstall/base-70cebd0 || TREE=/tmp/sdstall/head-e291976
  [[ -d $TREE/$SESS ]] && .venv/bin/python -B $S/arm_validity.py $TREE/$SESS $O/samples.jsonl > $O/validity-$REV.txt 2>&1
  log "FINAL validity $REV exit $? $(tail -1 $O/validity-$REV.txt)"
done
log "SESSION $SESS end"
touch $O/STOP $O/DONE3
wait $SAMPLER 2>/dev/null
