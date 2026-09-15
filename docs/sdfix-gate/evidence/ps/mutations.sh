#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
S=docs/sdfix-gate/scripts; CH='/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell'
HEADSHA=19cd48e0dd6e8d36126812c5e687504928e4fcbd; M=/tmp/sdfix-gate/mut; mkdir -p $M
port=18860
for m in ${=MUTS:-m1 m2 m3}; do
  port=$((port+1)); T=$M/tree-$m
  .venv/bin/python -B $S/bridge.py start --tree $T --rev $HEADSHA --ui-port $port --listen-port $((port+30000)) --mutation $m > $M/$m-bridge-start.txt 2>&1; echo "$m bridge-start exit=$?"
  (cd $T && git -C /Users/viddyslap/Documents/project-workspaces/steam-deck-midi diff --no-index --stat /dev/null /dev/null >/dev/null 2>&1; for f in controller_view.js controller_view.css; do shasum -a 256 windows/static/controller/$f; done) > $M/$m-mutated-sha.txt
  node tests/ui_controller_geometry.cjs http://127.0.0.1:$port "$CH" --out $M/$m-u1 > $M/$m-u1.log 2>&1; echo "$m U1-check exit=$? $(grep SUMMARY $M/$m-u1.log)"
  grep -E "^FAIL" $M/$m-u1.log | cut -c1-160 | head -12
  node $S/geom_gate.cjs http://127.0.0.1:$port $M/$m-gate 1440x900 --closed-only --label $m > $M/$m-gate.log 2>&1; echo "$m gate-geom exit=$?"; cut -c1-300 $M/$m-gate.log
  .venv/bin/python -B $S/bridge.py stop --tree $T > $M/$m-bridge-stop1.txt 2>&1; echo "$m stop exit=$? $(cat $M/$m-bridge-stop1.txt)"
  git archive $HEADSHA windows/static/controller | tar -x -C $T
  ok=1; for f in controller_view.js controller_view.css controller_map.json steam_deck.svg; do a=$(git cat-file -p $HEADSHA:windows/static/controller/$f | shasum -a 256 | cut -c1-64); b=$(shasum -a 256 $T/windows/static/controller/$f | cut -c1-64); [ "$a" = "$b" ] || ok=0; done; echo "$m restored-bytes-equal-HEAD=$ok"
  .venv/bin/python -B $S/bridge.py start --tree $T --rev $HEADSHA --ui-port $port --listen-port $((port+30000)) --reuse > $M/$m-bridge-restart.txt 2>&1; echo "$m bridge-restart exit=$?"
  node tests/ui_controller_geometry.cjs http://127.0.0.1:$port "$CH" --out $M/$m-restored-u1 > $M/$m-restored-u1.log 2>&1; echo "$m restored U1-check exit=$? $(grep SUMMARY $M/$m-restored-u1.log)"
  node $S/geom_gate.cjs http://127.0.0.1:$port $M/$m-restored-gate 1440x900 --closed-only --label $m-restored > $M/$m-restored-gate.log 2>&1; echo "$m restored gate-geom exit=$? $(tail -1 $M/$m-restored-gate.log)"
  .venv/bin/python -B $S/bridge.py stop --tree $T > $M/$m-bridge-stop2.txt 2>&1; echo "$m stop2 exit=$? $(cat $M/$m-bridge-stop2.txt)"
done
