#!/bin/bash
# Single HIGH-SPEED turbo run to quickly generate trades
# Optimized for maximum data generation speed

echo "⚡ HIGH-SPEED TURBO MODE"
echo "========================"
echo ""

# Create logs dir if needed
mkdir -p logs

# Show current state
echo "📊 Before:"
./venv/bin/python quick_stats.py | grep -E "(Current:|LONGs:|SHORTs:)"

echo ""
echo "🚀 Running high-speed generation..."
echo "   Strategy: All variants"
echo "   Per Symbol: 8 trades"
echo "   Rounds: 5"
echo "   SHORT Bias: YES"
echo "   Fast Mode: YES"
echo ""

# Run aggressive data generation
./venv/bin/python turbo_mode.py \
    --per-symbol 8 \
    --rounds 5 \
    --short-bias \
    --fast

echo ""
echo "✅ Generation complete!"
echo ""
echo "📊 After:"
./venv/bin/python quick_stats.py

echo ""
echo "💡 TIP: Run again if you need more trades:"
echo "   ./quick_turbo.sh"
