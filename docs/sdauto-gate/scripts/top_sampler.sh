#!/bin/zsh
while [[ ! -f /tmp/sdauto-gate/bar3/DONE2 ]]; do
  L=$(sysctl -n vm.loadavg | awk '{print $2}')
  echo "== $(date +%H:%M:%S) load1=$L" >> /tmp/sdauto-gate/bar3/top2.log
  ps -A -o pcpu=,pid=,command= -r | head -6 | cut -c1-160 >> /tmp/sdauto-gate/bar3/top2.log
  P=$(pgrep -f "while True: pass" | tr "\n" " ")
  F=$(ps -A -o command= | /usr/bin/awk '/codex exec/ {next} { split($0,a," "); c=a[1]; sub(".*/","",c); if (c=="zsh"||c=="bash"||c=="sh"||c=="node") { s=""; for (i=2;i<=length(a);i++) if (substr(a[i],1,1)!="-") { s=a[i]; break }; if (index(s,"/Users/viddyslap/Documents/project-workspaces/local-LLM-h14/engine/tests/")==1 || s ~ /run-all\.sh$/) n++ } } END {print n+0}')
  echo "   foreign_lines=$F pgrep=[$P]" >> /tmp/sdauto-gate/bar3/top2.log
  sleep 5
done
