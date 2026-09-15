#!/bin/zsh
cd /Users/viddyslap/Documents/project-workspaces/steam-deck-midi
CLIENT='["node","/Users/viddyslap/Documents/project-workspaces/steam-deck-midi/scripts/showready/timing_browser.cjs","{url}","{stop}","{receipt}","/Users/viddyslap/Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell","--single-process"]'
O=/tmp/sdauto-gate/bar3
echo "CLEAN2 START $(date +%T)" >> $O/status.txt
.venv/bin/python -B scripts/showready/timing_ab.py --rule m_bridge --candidate HEAD --script scripts/showready/timing_script.json --repeats 5 --scratch $O/mac-mbridge-clean2 --out $O/mac-mbridge-clean2.json.gz --sensitivity-result $O/mac-mbridge-sensitivity.json.gz --client-cmd "$CLIENT" > $O/clean2.stdout 2>&1
echo "CLEAN2 END exit $? $(date +%T)" >> $O/status.txt
touch $O/DONE2
