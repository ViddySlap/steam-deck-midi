#!/bin/zsh
S=/tmp/sdpick-k1/step.sh
A() { perl -e 'alarm shift; exec @ARGV' "$@"; }
A 1500 $S F1-flake-head run sdpick-k1 /tmp/sdpick-k1/flake_gate.ps1 -Which head
A 1500 $S F2-flake-base run sdpick-k1 /tmp/sdpick-k1/flake_gate.ps1 -Which base
A 900 $S F3-suite1 run sdpick-k1 /tmp/sdpick-k1/suite.ps1 -Label k1-suite1
A 900 $S F4-suite2 run sdpick-k1 /tmp/sdpick-k1/suite.ps1 -Label k1-suite2
A 600 $S G1-browserfix-red run sdpick-k1 /tmp/sdpick-k1/browserfix_red.ps1
date '+CHAIN_F_DONE %Y-%m-%dT%H:%M:%S' > /tmp/sdpick-k1/logs/chain_f.done
