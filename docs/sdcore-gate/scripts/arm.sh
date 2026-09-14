#!/bin/zsh
# usage: arm.sh <tree> <label> [extra args...]
tree=$1; label=$2; shift 2
out=/tmp/sdcore-gate/arm-$label
cd $tree || exit 2
BROWSER=/usr/bin/true nohup perl -e '$SIG{INT}="DEFAULT"; exec @ARGV' /Users/viddyslap/Documents/project-workspaces/steam-deck-midi/.venv/bin/python -B -u -m windows.win_recv --listen 0.0.0.0:45123 --map config/windows_midi_map.json --midi-port "IAC Driver DECK_IN" --feedback-port "IAC Driver DECK_OUT" --pulse-port "IAC Driver PULSE_OUT" --timeout 2.0 --ui-port 7723 "$@" > $out.log 2>&1 < /dev/null &
pid=$!
echo "label=$label pid=$pid tree=$tree extra=$*"
for i in $(seq 1 40); do curl -s -o /dev/null --max-time 1 http://127.0.0.1:7723/ && break; perl -e 'select(undef,undef,undef,0.25)'; done
echo "http up after ~$((i/4))s"
perl -e 'select(undef,undef,undef,10)'
ps -o pid,etime,time,%cpu -p $pid
kill -INT $pid; t=0
for i in $(seq 1 24); do kill -0 $pid 2>/dev/null || break; perl -e 'select(undef,undef,undef,0.25)'; done
if kill -0 $pid 2>/dev/null; then echo "SIGINT: still alive after 6s"; kill -TERM $pid; perl -e 'select(undef,undef,undef,3)'; kill -0 $pid 2>/dev/null && { echo "SIGTERM: alive, SIGKILL"; kill -KILL $pid; } || echo "SIGTERM: exited"; else echo "SIGINT: exited within 6s"; fi
perl -e 'select(undef,undef,undef,0.5)'
lsof -nP -iUDP:45123 -iTCP:7723 >/dev/null; echo "ports bound after stop? lsof exit=$? (1=released)"
echo "log tail:"; tail -4 $out.log
