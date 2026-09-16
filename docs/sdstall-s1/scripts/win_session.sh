#!/bin/zsh
# sdstall S1 item d: the laptop CLOSED-arm BASE/HEAD interleave, DIAGNOSTIC.
# ONE session of R >= 8 VALID arms per revision (MASTER 13, 16:44 (1): the
# two-session replication rule binds the MAC only; Windows answers one question,
# whether HEAD stalls on the show machine at all).
#   win_session.sh <target> <max-arms-per-revision>
# Order: guard snapshot -> build and rail the payload -> setup -> arms ->
#        fetch results -> teardown report -> guard compare.
# Every laptop HARD RULE applies. Nothing is installed; nothing is pulled from
# GitHub on the laptop; the clone is read-only; the tray, loopMIDI, Resolume and
# the orphan checkout are never touched.
set -u
R=/Users/viddyslap/Documents/project-workspaces/steam-deck-midi
S=$R/docs/sdstall-s1/scripts
TAG=sdstall-s1
WORK='C:\Users\Ben\AppData\Local\Temp\sdwin\sdstall-s1'
O=/tmp/sdstall/win
TARGET=$1; MAXA=$2
mkdir -p $O
cd $R
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a $O/win.log; }
rail() { bash scripts/showready/win_rail.sh "$@"; }

log "WIN SESSION start target=$TARGET maxarms=$MAXA"
log "MAC load1 at start: $(sysctl -n vm.loadavg)"

# THE GUARD, before the first laptop act.
rail run $TAG scripts/showready/win_guard.ps1 -Mode snapshot -Out "$WORK\\before.json" > $O/guard-before.txt 2>&1
log "GUARD snapshot exit $? $(tail -2 $O/guard-before.txt | tr '\n' ' ')"

# Payload: two `git archive` zips plus the fixture kit (the clone has no
# .showready directory at all, measured), plus the wrapper.
git archive --format=zip 70cebd0b6baed2ece86a2d218843e02b6298789d > $O/base.zip
git archive --format=zip e2919763fe9174fe0fe44e2782f4279895cf0434 > $O/head.zip
# The laptop clone has NO .showready directory (measured), so the fixture kit is
# railed over too. Zip from INSIDE .showready/fixtures so `mac/` and
# `windows-installed/` sit at the zip root and land directly under $Work\fixtures.
rm -f $O/fixtures.zip
(cd $R/.showready/fixtures && zip -q -r -X $O/fixtures.zip mac windows-installed) || { log "ZIP fixtures FAILED"; exit 2; }
[[ -s $O/fixtures.zip ]] || { log "fixtures.zip is empty or missing"; exit 2; }
cp $S/closed_only.py $O/closed_only.py
BASE_SHA=$(shasum -a 256 $O/base.zip | cut -d' ' -f1)
HEAD_SHA=$(shasum -a 256 $O/head.zip | cut -d' ' -f1)
FIX_SHA=$(shasum -a 256 $O/fixtures.zip | cut -d' ' -f1)
WRAP_SHA=$(shasum -a 256 $O/closed_only.py | cut -d' ' -f1)
log "MAC SHA256 base.zip $BASE_SHA ($(stat -f%z $O/base.zip) bytes)"
log "MAC SHA256 head.zip $HEAD_SHA ($(stat -f%z $O/head.zip) bytes)"
log "MAC SHA256 fixtures.zip $FIX_SHA ($(stat -f%z $O/fixtures.zip) bytes)"
log "MAC SHA256 closed_only.py $WRAP_SHA"

for f in base.zip head.zip fixtures.zip closed_only.py; do
  rail put $TAG $O/$f && log "PUT $f ok" || { log "PUT $f FAILED"; exit 3; }
done

rail run $TAG $S/win_setup.ps1 -Work "$WORK" -BaseSha256 "$BASE_SHA" -HeadSha256 "$HEAD_SHA" -FixturesSha256 "$FIX_SHA" > $O/setup.txt 2>&1
SE=$?
log "SETUP exit $SE"
cat $O/setup.txt | sed 's/^/  /' >> $O/win.log
if (( SE != 0 )); then log "SETUP FAILED - stopping before any arm"; exit 4; fi

log "MAC load1 before arms: $(sysctl -n vm.loadavg)"
rail run $TAG $S/win_arms.ps1 -Work "$WORK" -Target "$TARGET" -MaxArms "$MAXA" > $O/arms.txt 2>&1
AE=$?
log "ARMS exit $AE"
log "MAC load1 after arms: $(sysctl -n vm.loadavg)"
tail -5 $O/arms.txt | sed 's/^/  /' >> $O/win.log

# Fetch every result file the laptop wrote.
rail run $TAG $S/win_list_results.ps1 -Work "$WORK" > $O/results-list.txt 2>&1
log "RESULTS LIST exit $?"
grep '^RESULT ' $O/results-list.txt | awk '{print $2}' | while read -r name; do
  rail get "$WORK\\$name" "$O/$name" && log "GET $name ok" || log "GET $name FAILED"
done

rail run $TAG $S/win_teardown.ps1 -Work "$WORK" > $O/teardown.txt 2>&1
log "TEARDOWN exit $?"
cat $O/teardown.txt | sed 's/^/  /' >> $O/win.log

rail run $TAG scripts/showready/win_guard.ps1 -Mode compare -Baseline "$WORK\\before.json" -Out "$WORK\\after.json" > $O/guard-after.txt 2>&1
log "GUARD compare exit $? $(tail -3 $O/guard-after.txt | tr '\n' ' ')"
touch $O/DONE
log "WIN SESSION end"
