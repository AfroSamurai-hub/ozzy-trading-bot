#!/usr/bin/env bash
# Simple helper to start the live labeler in the background and redirect logs
set -euo pipefail
PYTHON=${PYTHON:-python}
LOG_DIR="$(dirname "$0")/../logs"
mkdir -p "$LOG_DIR"
nohup "$PYTHON" "$(dirname "$0")/live_labeler.py" > "$LOG_DIR/labeler.out" 2>&1 &
echo "Labeler started -> logs/labeler.out"