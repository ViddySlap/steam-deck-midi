#!/bin/zsh
/tmp/sdlive-gate/laptop/run_phase.sh clean L18-edge-clean-try2.txt
/tmp/sdlive-gate/laptop/run_phase.sh sensitivity L19-python-sensitivity.txt -PythonClient
/tmp/sdlive-gate/laptop/run_phase.sh clean L20-python-clean.txt -PythonClient
date '+CHAIN_DONE %Y-%m-%dT%H:%M:%S' > /tmp/sdlive-gate/laptop/chain.done
