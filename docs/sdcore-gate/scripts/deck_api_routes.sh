#!/bin/zsh
# sdcore gate: exercise every Deck control API route with curl against a standalone server.
RR=/Users/viddyslap/Documents/project-workspaces/steam-deck-midi
S=/tmp/sdcore-gate/deck/settings.json
B=http://127.0.0.1:7724
cd $RR
nohup perl -e '$SIG{INT}="DEFAULT"; exec @ARGV' python3 -B -m deck.control_api --settings $S > /tmp/sdcore-gate/deck/api.log 2>&1 < /dev/null &
pid=$!
echo "control_api pid=$pid"
for i in $(seq 1 40); do curl -s -o /dev/null --max-time 1 $B/api/status && break; perl -e 'select(undef,undef,undef,0.25)'; done
typeset -A seen
call() {
  local method=$1 route=$2 body=$3
  local out code
  if [[ -n $body ]]; then
    out=$(curl -s -X $method -H 'content-type: application/json' --data "$body" -w '\n%{http_code}' $B$route)
  else
    out=$(curl -s -X $method -w '\n%{http_code}' $B$route)
  fi
  code=${out##*$'\n'}
  print -r -- "$method $route ${body:+body=$body }-> HTTP $code: ${${out%$'\n'*}[1,300]}"
  seen["$method $route"]=$code
}
call GET /api/status
call GET /api/targets
call POST /api/targets/add '{"name":"macbook","host":"127.0.0.1","port":45123}'
call POST /api/targets/add '{"name":"windows","host":"127.0.0.1","port":45124}'
call POST /api/targets/add '{"name":"bad","host":"not a host!","port":1}'
call POST /api/targets '{"presets":[{"name":"macbook","host":"127.0.0.1","port":45123},{"name":"windows","host":"127.0.0.1","port":45124},{"name":"grandma","host":"grandma.local"}]}'
call POST /api/targets/rename '{"old":"grandma","new":"grandma2"}'
call POST /api/targets/active '{"names":["windows","macbook"]}'
call POST /api/targets/active '{"names":["nope"]}'
echo "on disk after activate: $(python3 -c "import json; d=json.load(open('$S')); print(d['active_targets'], [p['name'] for p in d['presets']])")"
call POST /api/targets/delete '{"name":"grandma2"}'
call GET /api/bindings
call POST /api/bindings/reload
call GET /api/settings
call PUT /api/settings '{"profile_name":"gate-profile"}'
echo "on disk profile_name: $(python3 -c "import json; print(json.load(open('$S'))['profile_name'])")"
call GET /api/actions
call GET /api/learn
call POST /api/learn/start '{"action":"BTN_A"}'
perl -e 'select(undef,undef,undef,0.5)'
call GET /api/learn
call POST /api/learn/confirm
call POST /api/learn/skip
call POST /api/learn/cancel
call POST /api/sender/start
perl -e 'select(undef,undef,undef,1.0)'
call GET /api/status
call POST /api/sender/stop
call POST /api/sender/restart
perl -e 'select(undef,undef,undef,1.0)'
call GET /api/status
call POST /api/sender/stop
call POST /api/shutdown
for i in $(seq 1 20); do kill -0 $pid 2>/dev/null || break; perl -e 'select(undef,undef,undef,0.25)'; done
kill -0 $pid 2>/dev/null && echo "control_api STILL ALIVE after /api/shutdown" || echo "control_api exited after /api/shutdown"
lsof -nP -iTCP:7724 >/dev/null; echo "7724 bound after shutdown? lsof exit=$? (1=released)"
echo "ROUTES EXERCISED: ${#seen}"
for k in ${(ok)seen}; do echo "  $k -> ${seen[$k]}"; done
