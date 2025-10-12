#!/bin/bash
# Quick launcher for live dashboard

echo ""
echo "🚀 Launching Live Dashboard..."
echo "   Updates every 10 seconds"
echo "   Press Ctrl+C to exit"
echo ""
sleep 2

cd ~/ozzy-simple
./venv/bin/python scripts/live_dashboard.py
