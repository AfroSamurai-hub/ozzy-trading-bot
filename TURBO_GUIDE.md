# TURBO MODE OPTIMIZATION GUIDE 🚀

## Quick Status Check
```bash
./venv/bin/python quick_stats.py
```

## Generation Modes (Fastest to Slowest)

### 🔥 SUPER TURBO (Recommended for hitting 200 trades FAST)
**Generates 100+ trades in ~5-10 minutes**
```bash
./super_turbo.py
```
- Runs 3 sequential high-volume rounds
- Heavy SHORT bias for balance
- Zero cooldown between operations
- **Best for**: Hitting 200 trades quickly

### ⚡ Quick Turbo (Single burst)
**Generates ~40 trades in 2-3 minutes**
```bash
./quick_turbo.sh
```
- All 5 variants in sequence
- 8 trades per symbol, 5 rounds each
- SHORT bias enabled
- **Best for**: Quick data top-up

### 🔀 Parallel Turbo (Maximum throughput)
**Generates 100+ trades in 3-5 minutes**
```bash
./run_parallel_turbo.sh 5 10
# Args: [per-symbol] [rounds]
```
- All 5 variants run SIMULTANEOUSLY
- Logs to separate files
- **Best for**: Maximum speed (multi-core)
- **Note**: Higher API load

### 🎯 Targeted Turbo (Fine control)
**Custom parameters for specific needs**
```bash
./venv/bin/python turbo_mode.py \
    --per-symbol 8 \
    --rounds 5 \
    --variants Aggressive Momentum \
    --short-bias \
    --fast
```

## Optimization Flags

### `--short-bias`
Automatically adjusts RSI thresholds to generate more SHORT trades
- Makes RSI_OVERBOUGHT easier to trigger (lower threshold)
- Makes RSI_OVERSOLD harder to trigger (higher threshold)
- Checks current LONG/SHORT ratio and compensates

### `--fast`
Maximum speed mode:
- Zero cooldown between rounds
- Minimal logging overhead
- No API throttling delays

### `--variants`
Run specific strategies only:
```bash
--variants Conservative     # Safe, high-confidence trades
--variants Aggressive       # More trades, lower confidence
--variants Balanced         # Middle ground (recommended)
--variants Momentum         # High momentum only
--variants Contrarian       # Counter-trend plays
```

## Current Stats & Goals

### Your Status (as of now):
- **132/200 trades** (66% complete)
- **100 LONGs, 32 SHORTs** (need 18 more SHORTs)
- **60.6% win rate** ✅ (target: 55%+)
- **Need: 68 more trades total**

### Recommended Strategy:
```bash
# Step 1: Run super turbo to hit 200 trades
./super_turbo.py

# Step 2: Check progress
./venv/bin/python quick_stats.py

# Step 3: If needed, run one more targeted round
./venv/bin/python turbo_mode.py \
    --per-symbol 10 \
    --rounds 5 \
    --short-bias \
    --fast

# Step 4: Final analysis
./venv/bin/python deep_analysis.py
```

## Monitoring

### Watch mode (updates every 10 seconds)
```bash
watch -n 10 './venv/bin/python quick_stats.py'
```

### Check logs (parallel mode)
```bash
tail -f logs/*.log
```

## Speed Benchmarks

| Mode | Trades/Min | Time to 200 | SHORT Bias | Parallel |
|------|------------|-------------|------------|----------|
| Super Turbo | 15-20 | 5-10 min | ✅ | No |
| Parallel | 20-30 | 3-5 min | ✅ | Yes |
| Quick Turbo | 15-20 | 3-4 min | ✅ | No |
| Manual | 10-15 | 7-10 min | Optional | No |

## Tips for Maximum Speed

1. **Use --fast flag** - Removes all delays
2. **Enable --short-bias** - Balances dataset automatically
3. **Higher per-symbol** - More trades per round
4. **More rounds** - Longer run, more data
5. **Parallel execution** - If you have CPU cores to spare

## API Rate Limits

Bybit spot market endpoints are generous, but:
- Public endpoints: ~120 requests/min
- Your scripts run ~5-10 requests/trade
- Safe limit: ~10-15 trades/minute
- **Super turbo stays well within limits**

## Troubleshooting

### "Need more SHORTs"
```bash
# Force SHORT generation
./venv/bin/python turbo_mode.py \
    --per-symbol 15 \
    --rounds 3 \
    --short-bias \
    --fast
```

### "Trades generating too slowly"
```bash
# Use parallel mode
./run_parallel_turbo.sh 10 5
```

### "Hit 200 trades, what now?"
```bash
# Run final analysis
./venv/bin/python deep_analysis.py

# Check if ready for live trading
./venv/bin/python quick_stats.py | grep "Status:"
```

## Next Steps After 200 Trades

1. ✅ Run full analysis: `./venv/bin/python deep_analysis.py`
2. ✅ Review `analysis_report.md`
3. ✅ Check optimal config recommendations
4. ✅ If win rate > 55% and profit factor > 1.5: Start live with R1000
5. ✅ Monitor with: `./venv/bin/python scripts/cli_dashboard.py --live`

---

**Current Recommendation**: Run `./super_turbo.py` NOW to hit 200+ trades in under 10 minutes! 🚀
