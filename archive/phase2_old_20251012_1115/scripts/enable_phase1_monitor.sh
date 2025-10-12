#!/bin/bash
# scripts/enable_phase1_monitor.sh
# Revert to Phase 1.5: monitor-only mode with adaptive preview only.
set -euo pipefail
cd /home/rick/ozzy-simple || exit 1

backup="config.bak.$(date +%Y%m%d_%H%M%S)"
cp config.py "$backup"
echo "Backed up config.py -> $backup"

# Monitor-only
sed -i "s/^\s*MONITOR_ONLY_MODE\s*=\s*False/MONITOR_ONLY_MODE = True/" config.py || true

# Keep adaptive on for preview; not used in execution while monitoring
if grep -q "^\s*ADAPTIVE_SIZING_ENABLED" config.py; then
  sed -i "s/^\s*ADAPTIVE_SIZING_ENABLED\s*=\s*False/ADAPTIVE_SIZING_ENABLED = True/" config.py || true
else
  echo "ADAPTIVE_SIZING_ENABLED = True" >> config.py
fi

# Restore default concurrent positions
sed -i "s/^\s*MAX_OPEN_POSITIONS\s*=.*/MAX_OPEN_POSITIONS = 3/" config.py || true
if ! grep -q "^\s*MAX_POSITIONS\s*=\s*MAX_OPEN_POSITIONS" config.py; then
  echo "MAX_POSITIONS = MAX_OPEN_POSITIONS" >> config.py
fi

echo "Phase 1.5 monitor-only enabled: MONITOR_ONLY_MODE=True, adaptive preview on, MAX_OPEN_POSITIONS=3"
