#!/bin/zsh
# usage: mac_arm.sh <tree> <label> <stop: sigint|shutdown> [extra bridge args...]
# F2/F5 Mac arm for sdauto A3. Dry-run, engines/pulse/relay off, loopback non-default ports.
set -u
tree=$1; label=$2; stopmode=$3; shift 3
out=/tmp/sdauto-a3/arms/$label
mkdir -p $out
PY=/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/.venv/bin/python
ports=$($PY -c 'import socket
u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); u.bind(("127.0.0.1",0))
t=socket.socket(); t.bind(("127.0.0.1",0))
print(u.getsockname()[1], t.getsockname()[1])')
udp=${ports% *}; ui=${ports#* }
echo "label=$label tree=$tree stop=$stopmode udp=$udp ui=$ui extra=$* PYSTRAY_BACKEND=${PYSTRAY_BACKEND:-unset}"
echo "pgrep_while_true_before=[$(pgrep -f 'while True: pass')] load=$(sysctl -n vm.loadavg)"
crashref=$out/crashref; touch $crashref
cd $tree || exit 2
BROWSER=/usr/bin/true perl -e '$SIG{INT}="DEFAULT"; exec @ARGV' $PY -B -u -m windows.win_recv \
  --listen 127.0.0.1:$udp --map config/windows_midi_map.json \
  --midi-port "IAC Driver DECK_IN" --feedback-port "IAC Driver DECK_OUT" --pulse-port "IAC Driver PULSE_OUT" \
  --timeout 2.0 --ui-port $ui --dry-run --no-engines --no-pulse --no-osc-relay "$@" \
  > $out/bridge.log 2>&1 < /dev/null &
pid=$!
echo "pid=$pid started=$(date +%H:%M:%S)"
up=0
for i in {1..80}; do
  if curl -s -o /dev/null --max-time 1 http://127.0.0.1:$ui/; then up=1; break; fi
  perl -e 'select(undef,undef,undef,0.25)'
done
echo "http_up=$up after_polls=$i"
t0=$(ps -o time= -p $pid | tr -d ' '); e0=$($PY -c 'import time;print(time.time())')
samples=()
for i in {1..30}; do
  sleep 1
  samples+=$(ps -o %cpu= -p $pid | tr -d ' ')
done
t1=$(ps -o time= -p $pid | tr -d ' '); e1=$($PY -c 'import time;print(time.time())')
echo "cpu_samples_%cpu=${samples[*]}"
$PY - "$t0" "$t1" "$e0" "$e1" "${samples[@]}" <<'EOF'
import sys
def secs(t):
    parts = t.split(":")
    s = 0.0
    for p in parts:
        s = s * 60 + float(p)
    return s
t0, t1, e0, e1 = sys.argv[1:5]
vals = [float(v) for v in sys.argv[5:]]
d = secs(t1) - secs(t0); el = float(e1) - float(e0)
print(f"cputime_before={t0} cputime_after={t1} cpu_seconds={d:.2f} wall_seconds={el:.2f} cpu_pct_of_one_core={100*d/el:.1f}")
print(f"ps_pcpu_n={len(vals)} mean={sum(vals)/len(vals):.1f} min={min(vals)} max={max(vals)}")
EOF
ps -M -p $pid | head -20 > $out/threads.txt
echo "threads=$(($(wc -l < $out/threads.txt) - 1))"
if [[ $stopmode == shutdown ]]; then
  code=$(curl -s -o $out/shutdown.json -w '%{http_code}' -X POST --max-time 3 http://127.0.0.1:$ui/api/shutdown)
  echo "POST /api/shutdown http=$code body=$(cat $out/shutdown.json)"
else
  kill -INT $pid; echo "sent SIGINT at $(date +%H:%M:%S)"
fi
gone=0
for i in {1..20}; do
  if ! kill -0 $pid 2>/dev/null; then gone=1; break; fi
  perl -e 'select(undef,undef,undef,0.25)'
done
if (( gone )); then
  wait $pid; rc=$?
  echo "exited_within_5s=yes polls=$i wait_status=$rc"
else
  echo "exited_within_5s=no; sending SIGTERM"
  kill -TERM $pid
  for i in {1..20}; do kill -0 $pid 2>/dev/null || break; perl -e 'select(undef,undef,undef,0.25)'; done
  if kill -0 $pid 2>/dev/null; then echo "SIGTERM: alive after 5s, SIGKILL"; kill -KILL $pid; fi
  wait $pid; rc=$?
  echo "after_sigterm wait_status=$rc"
fi
kill -0 $pid 2>/dev/null && echo "PID_ALIVE=$pid" || echo "PID_GONE=$pid"
lsof -nP -iUDP:$udp -iTCP:$ui > /dev/null; echo "ports_bound_lsof_exit=$? (1=released)"
sleep 2
echo "new_crash_reports=[$(/usr/bin/find ~/Library/Logs/DiagnosticReports -newer $crashref -name 'Python*' 2>/dev/null | tr '\n' ' ')]"
echo "pgrep_while_true_after=[$(pgrep -f 'while True: pass')] load=$(sysctl -n vm.loadavg)"
echo "log_tail:"; tail -5 $out/bridge.log
