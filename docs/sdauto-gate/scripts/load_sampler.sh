#!/bin/zsh
# load1 + foreign_lines (MASTER 01:11 definition) + pgrep while True, every 5 s, until bar3 done file exists
while [[ ! -f /tmp/sdauto-gate/bar3/DONE ]]; do
  L=$(sysctl -n vm.loadavg | awk '{print $2}')
  F=$(ps -A -o command= | /usr/bin/awk '/codex exec/ {next} { split($0,a," "); c=a[1]; sub(".*/","",c); if (c=="zsh"||c=="bash"||c=="sh"||c=="node") { s=""; for (i=2;i<=length(a);i++) if (substr(a[i],1,1)!="-") { s=a[i]; break }; if (index(s,"/Users/viddyslap/Documents/project-workspaces/local-LLM-h14/engine/tests/")==1 || s ~ /run-all\.sh$/) n++ } } END {print n+0}')
  P=$(pgrep -f "while True: pass" | tr "\n" " "); [[ -n "$P" ]] && for q in ${=P}; do echo "$(date +%H:%M:%S) MATCH $(ps -p $q -o pid=,ppid=,etime=,command= 2>&1)" >> /tmp/sdauto-gate/bar3/load-matches.log; done
  echo "$(date +%H:%M:%S) load1=$L foreign_lines=$F pgrep=[$P]" >> /tmp/sdauto-gate/bar3/load.log
  sleep 5
done
