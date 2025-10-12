#!/bin/bash
# Parallel Turbo Mode Runner - Run multiple variants simultaneously
# Usage: ./run_parallel_turbo.sh [per-symbol] [rounds]

PER_SYMBOL=${1:-5}
ROUNDS=${2:-10}

echo "🚀 Starting PARALLEL TURBO MODE"
echo "   Per Symbol: $PER_SYMBOL"
echo "   Rounds: $ROUNDS"
echo "   Variants: All 5 running in parallel"
echo ""

# Check current stats first
echo "📊 Current Stats:"
./venv/bin/python quick_stats.py

echo ""
echo "⏱️  Starting parallel execution in 3 seconds..."
sleep 3

# Run each variant in background
echo "Starting Conservative..."
./venv/bin/python turbo_mode.py --per-symbol $PER_SYMBOL --rounds $ROUNDS --variants Conservative --short-bias --fast > logs/conservative.log 2>&1 &
PID1=$!

sleep 1
echo "Starting Aggressive..."
./venv/bin/python turbo_mode.py --per-symbol $PER_SYMBOL --rounds $ROUNDS --variants Aggressive --short-bias --fast > logs/aggressive.log 2>&1 &
PID2=$!

sleep 1
echo "Starting Balanced..."
./venv/bin/python turbo_mode.py --per-symbol $PER_SYMBOL --rounds $ROUNDS --variants Balanced --short-bias --fast > logs/balanced.log 2>&1 &
PID3=$!

sleep 1
echo "Starting Momentum..."
./venv/bin/python turbo_mode.py --per-symbol $PER_SYMBOL --rounds $ROUNDS --variants Momentum --short-bias --fast > logs/momentum.log 2>&1 &
PID4=$!

sleep 1
echo "Starting Contrarian..."
./venv/bin/python turbo_mode.py --per-symbol $PER_SYMBOL --rounds $ROUNDS --variants Contrarian --short-bias --fast > logs/contrarian.log 2>&1 &
PID5=$!

echo ""
echo "✅ All variants started!"
echo "   PIDs: $PID1 $PID2 $PID3 $PID4 $PID5"
echo ""
echo "📋 Monitor progress:"
echo "   watch -n 10 './venv/bin/python quick_stats.py'"
echo ""
echo "📄 View logs:"
echo "   tail -f logs/*.log"
echo ""
echo "⏳ Waiting for all processes to complete..."

# Wait for all background jobs
wait $PID1 $PID2 $PID3 $PID4 $PID5

echo ""
echo "🎉 All variants complete!"
echo ""
echo "📊 Final Stats:"
./venv/bin/python quick_stats.py

echo ""
echo "📈 Run analysis:"
echo "   ./venv/bin/python deep_analysis.py"
