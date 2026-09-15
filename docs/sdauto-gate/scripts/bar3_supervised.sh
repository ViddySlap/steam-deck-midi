#!/bin/zsh
# sdauto AG bar 3 under MASTER 13 15:21 (3): whole-machine sampler, quiet start (load1 < 4.0 for 60 s),
# post-run arm validity (load1 > 5.0 in any in-arm sample, or a non-lane process > 50% for > 10 s, voids the run),
# fresh full run on INVALID; 90 min without a valid run -> BLOCKED file. Sensitivity (R=3) first, then clean (R=5).
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
O=/tmp/sdauto-gate/bar3q
mkdir -p $O
S=docs/sdauto-gate/scripts
CLIENT='["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
log() { echo "$(date +%H:%M:%S) $*" >> $O/supervisor.log; }
.venv/bin/python -B $S/machine_sampler.py --out $O/samples.jsonl --lane-root $$ --stop $O/STOP &
DEADLINE=$(( $(date +%s) + 5400 ))
wait_quiet() {
  local since=0
  while true; do
    (( $(date +%s) > DEADLINE )) && return 1
    L=$(sysctl -n vm.loadavg | awk '{print $2}')
    if (( L < 4.0 )); then (( since == 0 )) && since=$(date +%s); (( $(date +%s) - since >= 60 )) && { log "quiet: load1 < 4.0 for 60 s (now $L)"; return 0; }
    else since=0; fi
    sleep 5
  done
}
attempt_run() {  # $1 label, rest: timing_ab args
  local label=$1; shift
  local n=0
  while true; do
    n=$((n+1))
    wait_quiet || { log "BLOCKED $label: no quiet start before the 90 min deadline"; touch $O/BLOCKED; return 1; }
    log "START $label try$n"
    .venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --scratch $O/$label-try$n --out $O/$label-try$n.json.gz --client-cmd "$CLIENT" "$@" > $O/$label-try$n.stdout 2>&1
    log "END $label try$n exit $?"
    .venv/bin/python -B $S/arm_validity.py $O/$label-try$n $O/samples.jsonl > $O/$label-try$n.validity.txt 2>&1
    local v=$?
    log "VALIDITY $label try$n exit $v $(tail -1 $O/$label-try$n.validity.txt)"
    if (( v == 0 )); then ln -sf $O/$label-try$n.json.gz $O/$label-VALID.json.gz; return 0; fi
    (( $(date +%s) > DEADLINE )) && { log "BLOCKED $label: deadline after an INVALID run"; touch $O/BLOCKED; return 1; }
  done
}
log "supervisor pid $$ deadline $(date -r $DEADLINE +%H:%M:%S)"
attempt_run sens --repeats 3 --control sensitivity && attempt_run clean --repeats 5 --sensitivity-result $O/sens-VALID.json.gz
log "DONE"
touch $O/STOP $O/DONE
