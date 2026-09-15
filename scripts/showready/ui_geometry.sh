#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$ROOT/.venv/bin/python" -B "$ROOT/scripts/showready/ui_geometry.py" "$@"
