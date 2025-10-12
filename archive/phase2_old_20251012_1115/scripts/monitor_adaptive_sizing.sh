#!/bin/bash
# scripts/monitor_adaptive_sizing.sh
# Quick view of adaptive sizing metrics and current tier sizes

cd /home/rick/ozzy-simple || exit 1

if ! python3 - <<'PY'
from adaptive_position_manager import DynamicAdaptivePositionManager
try:
    import config
    cap = float(getattr(config, 'STARTING_CAPITAL', 5000))
except Exception:
    cap = 5000.0
m = DynamicAdaptivePositionManager(starting_capital=cap)
wr = m.get_recent_performance()
pls = m.get_daily_pnl()
perf = m.get_performance_multiplier()
conf = m.get_confidence_multiplier()
print('')
print('📊 PERFORMANCE METRICS:')
print(f'   Recent WR (20 trades): {wr*100:.1f}%')
print(f'   Today P&L: R{pls:.2f}')
print(f'   Performance multiplier: {perf}x')
print(f'   Confidence multiplier: {conf}x')
print('')
print('💰 CURRENT ADAPTIVE POSITIONS:')
positions = m.get_all_position_sizes(current_capital=cap)
for tier, info in positions.items():
    print(f'   {tier}: R{info["position_size"]:.0f} ({info["position_pct"]:.1f}%)')
print('')
print('🛡️ SAFETY RAILS:')
print(f'   Min position: R{m.ABSOLUTE_MIN_POSITION}')
print(f'   Max position: R{m.ABSOLUTE_MAX_POSITION}')
print(f'   Daily loss limit: R{m.ABSOLUTE_DAILY_LOSS_LIMIT}')
print('')
PY
then
  echo "Python failed to run adaptive sizing preview."
  exit 1
fi
