#!/bin/sh
trap 'echo stopping; exit 0' TERM
trap '' INT
echo "PYSTRAY_BACKEND=$PYSTRAY_BACKEND"
echo "BROWSER=$BROWSER"
echo "cwd=$PWD"
if read -r input; then echo stdin-open; else echo stdin-null; fi
i=1
while [ "$i" -le 5 ]; do
    echo "line-$i"
    i=$((i + 1))
done
echo stderr-line >&2
echo ready
while :; do sleep 0.02; done
