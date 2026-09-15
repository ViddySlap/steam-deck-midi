#!/bin/zsh
echo "date=$(date +%H:%M:%S) load=$(sysctl -n vm.loadavg) pgrep_while_true=[$(pgrep -f 'while True: pass')]"
ps -axo command= | /usr/bin/awk '
  /codex exec/ {next}
  { split($0, a, " "); c=a[1]; sub(".*/","",c);
    if (c=="zsh"||c=="bash"||c=="sh"||c=="node") {
      s=""; for (i=2;i<=length(a);i++) if (substr(a[i],1,1)!="-") { s=a[i]; break }
      if (index(s,"/Users/viddyslap/Documents/project-workspaces/local-LLM-h14/engine/tests/")==1 || s ~ /run-all\.sh$/) print "FOREIGN: " $0
    } }' > /tmp/sdauto-a3/foreign.txt
echo "foreign_lines=$(wc -l < /tmp/sdauto-a3/foreign.txt | tr -d ' ')"
cat /tmp/sdauto-a3/foreign.txt
