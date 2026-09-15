#!/bin/zsh
# usage: browser_live.sh <label> [extra]
set -u
label=$1; shift
PY=/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/.venv/bin/python
rec=/tmp/sdauto-a3/browser-$label.rec; rm -f $rec
cd /tmp/sdauto-a3/head/tree
REC_FILE=$rec BROWSER="/tmp/sdauto-a3/rec_browser.sh %s" perl -e '$SIG{INT}="DEFAULT"; exec @ARGV' $PY -B -u -m windows.win_recv --listen 127.0.0.1:56811 --map config/windows_midi_map.json --midi-port "IAC Driver DECK_IN" --timeout 2.0 --ui-port 58811 --dry-run --no-engines --no-pulse --no-osc-relay "$@" > /tmp/sdauto-a3/browser-$label.log 2>&1 < /dev/null &
pid=$!
sleep 5
kill -INT $pid; for i in {1..20}; do kill -0 $pid 2>/dev/null || break; sleep 0.25; done
wait $pid; echo "label=$label extra=$* pid=$pid wait_status=$? alive=$(kill -0 $pid 2>/dev/null && echo yes || echo no)"
if [[ -f $rec ]]; then echo "browser_invocations=$(wc -l < $rec | tr -d ' ') [$(cat $rec)]"; else echo "browser_invocations=0 (no record file)"; fi
