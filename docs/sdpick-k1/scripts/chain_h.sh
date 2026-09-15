#!/bin/zsh
perl -e 'alarm 2400; exec @ARGV' /tmp/sdpick-k1/step.sh H1-ab-windows-installed run sdpick-k1 /tmp/sdpick-k1/ab.ps1
date '+CHAIN_H_DONE %Y-%m-%dT%H:%M:%S' > /tmp/sdpick-k1/logs/chain_h.done
