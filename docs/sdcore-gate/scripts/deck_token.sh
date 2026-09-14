#!/bin/zsh
# sdcore gate: Deck control API off-loopback token refusal. Throwaway token, temp settings only.
RR=/Users/viddyslap/Documents/project-workspaces/steam-deck-midi
S=/tmp/sdcore-gate/deck/settings.json
LAN=$(ipconfig getifaddr en0)
TOK=sdcore-gate-throwaway-token
cd $RR
start() {
  nohup perl -e '$SIG{INT}="DEFAULT"; exec @ARGV' python3 -B -m deck.control_api --settings $S "$@" > /tmp/sdcore-gate/deck/api-token.log 2>&1 < /dev/null &
  pid=$!
}
waitdown() { for i in $(seq 1 20); do kill -0 $pid 2>/dev/null || return 0; perl -e 'select(undef,undef,undef,0.25)'; done; return 1; }

echo "## 1. off-loopback bind with NO token must refuse startup"
start --api-bind 0.0.0.0 --api-port 7725
waitdown && { wait $pid; echo "exited, exit code $?"; } || { echo "STILL RUNNING (finding)"; kill -TERM $pid; }
cat /tmp/sdcore-gate/deck/api-token.log
lsof -nP -iTCP:7725 >/dev/null; echo "7725 bound? lsof exit=$? (1=not bound)"

echo "## 2. persist a token over loopback"
start
for i in $(seq 1 40); do curl -s -o /dev/null --max-time 1 http://127.0.0.1:7724/api/status && break; perl -e 'select(undef,undef,undef,0.25)'; done
curl -s -X PUT -H 'content-type: application/json' --data "{\"api_token\":\"$TOK\"}" -o /dev/null -w "PUT api_token -> HTTP %{http_code}\n" http://127.0.0.1:7724/api/settings
echo "GET settings token fields: $(curl -s http://127.0.0.1:7724/api/settings | python3 -c 'import sys,json; d=json.load(sys.stdin); print({k:v for k,v in d.items() if "token" in k})')"
curl -s -X POST -o /dev/null -w "shutdown -> HTTP %{http_code}\n" http://127.0.0.1:7724/api/shutdown; waitdown && echo "loopback api exited"

echo "## 3. off-loopback bind with token: every request needs X-Deck-Token (via LAN address $LAN)"
start --api-bind 0.0.0.0 --api-port 7725
for i in $(seq 1 40); do curl -s -o /dev/null --max-time 1 http://$LAN:7725/api/status && break; perl -e 'select(undef,undef,undef,0.25)'; done
before=$(shasum -a 256 $S | cut -c1-16)
curl -s -o /dev/null -w "LAN GET /api/status no token -> HTTP %{http_code}\n" http://$LAN:7725/api/status
curl -s -o /dev/null -w "LAN GET /api/status wrong token -> HTTP %{http_code}\n" -H 'X-Deck-Token: wrong' http://$LAN:7725/api/status
curl -s -X POST -H 'content-type: application/json' --data '{"name":"intruder","host":"10.0.0.9"}' -w " <- LAN POST /api/targets/add no token -> HTTP %{http_code}\n" http://$LAN:7725/api/targets/add
curl -s -X POST -o /dev/null -w "LAN POST /api/shutdown no token -> HTTP %{http_code}\n" http://$LAN:7725/api/shutdown
curl -s -o /dev/null -w "LOOPBACK GET /api/status no token on 0.0.0.0 bind -> HTTP %{http_code}\n" http://127.0.0.1:7725/api/status
after=$(shasum -a 256 $S | cut -c1-16)
echo "settings sha before/after refused writes: $before / $after"
kill -0 $pid 2>/dev/null && echo "api still alive after refused shutdown: yes"
curl -s -H "X-Deck-Token: $TOK" -w "  <- LAN GET /api/status right token -> HTTP %{http_code}\n" http://$LAN:7725/api/status | cut -c1-120
curl -s -X POST -H "X-Deck-Token: $TOK" -o /dev/null -w "LAN POST /api/shutdown right token -> HTTP %{http_code}\n" http://$LAN:7725/api/shutdown
waitdown && echo "LAN api exited after authenticated shutdown" || { echo "STILL ALIVE"; kill -TERM $pid; }
lsof -nP -iTCP:7725 -iTCP:7724 >/dev/null; echo "7724/7725 bound? lsof exit=$? (1=released)"
