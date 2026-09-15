#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
CLIENT='["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
O=/tmp/sdauto-gate/bar3
echo "SENS START $(date +%T)" >> $O/status.txt
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 3 --control sensitivity --scratch $O/mac-mbridge-sensitivity --out $O/mac-mbridge-sensitivity.json.gz --client-cmd "$CLIENT" > $O/sensitivity.stdout 2>&1
echo "SENS END exit $? $(date +%T)" >> $O/status.txt
echo "CLEAN START $(date +%T)" >> $O/status.txt
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 5 --scratch $O/mac-mbridge-clean --out $O/mac-mbridge-clean.json.gz --sensitivity-result $O/mac-mbridge-sensitivity.json.gz --client-cmd "$CLIENT" > $O/clean.stdout 2>&1
echo "CLEAN END exit $? $(date +%T)" >> $O/status.txt
touch $O/DONE
