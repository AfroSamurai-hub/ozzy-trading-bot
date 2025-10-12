#!/bin/bash
# scripts/enable_phase2_adaptive.sh
# Flip to Phase 2: enable live trading with Adaptive Sizing and conservative guardrails.
set -euo pipefail
cd /home/rick/ozzy-simple || exit 1

backup="config.bak.$(date +%Y%m%d_%H%M%S)"
cp config.py "$backup"
echo "Backed up config.py -> $backup"

# Enable live trading loop (disable monitor-only)
sed -i "s/^\s*MONITOR_ONLY_MODE\s*=\s*True/MONITOR_ONLY_MODE = False/" config.py || true

# Keep adaptive sizing on
if grep -q "^\s*ADAPTIVE_SIZING_ENABLED" config.py; then
  sed -i "s/^\s*ADAPTIVE_SIZING_ENABLED\s*=\s*False/ADAPTIVE_SIZING_ENABLED = True/" config.py || true
else
  echo "ADAPTIVE_SIZING_ENABLED = True" >> config.py
fi

# Conservative initial cap on concurrent positions
sed -i "s/^\s*MAX_OPEN_POSITIONS\s*=.*/MAX_OPEN_POSITIONS = 1/" config.py || true
# Ensure alias stays intact
if ! grep -q "^\s*MAX_POSITIONS\s*=\s*MAX_OPEN_POSITIONS" config.py; then
  echo "MAX_POSITIONS = MAX_OPEN_POSITIONS" >> config.py
fi

echo "Phase 2 enabled: MONITOR_ONLY_MODE=False, ADAPTIVE_SIZING_ENABLED=True, MAX_OPEN_POSITIONS=1"
echo "Tip: If you want paper trading instead of live orders, set PAPER_TRADING = True in config.py before starting."
