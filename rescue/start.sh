#!/bin/bash
# OZZY Simple - Quick Start Script
# Run this to get started with the simplified system

echo "╔════════════════════════════════════════════════╗"
echo "║                                                ║"
echo "║         OZZY SIMPLE - QUICK START              ║"
echo "║                                                ║"
echo "╚════════════════════════════════════════════════╝"
echo ""

# Check if we're in the rescue directory
if [ ! -f "main_simple.py" ]; then
    echo "❌ Error: Run this from the rescue/ directory"
    echo "   cd /home/rick/ozzy-simple/rescue"
    exit 1
fi

# Step 1: Check Python
echo "📋 Step 1: Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.8+"
    exit 1
fi
echo "✅ Python found: $(python3 --version)"
echo ""

# Step 2: Setup virtual environment
echo "📋 Step 2: Setting up virtual environment..."
if [ ! -d "venv" ]; then
    echo "   Creating venv..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi
echo ""

# Step 3: Activate and install dependencies
echo "📋 Step 3: Installing dependencies..."
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "✅ Dependencies installed (4 packages)"
echo ""

# Step 4: Check .env file
echo "📋 Step 4: Checking API credentials..."
if [ ! -f ".env" ]; then
    echo "⚠️  WARNING: No .env file found!"
    echo ""
    echo "   Creating .env from template..."
    cp .env.example .env
    echo ""
    echo "🔧 ACTION REQUIRED:"
    echo "   1. Go to https://testnet.bybit.com"
    echo "   2. Create account and generate API keys"
    echo "   3. Edit .env file and add your credentials:"
    echo "      nano .env"
    echo ""
    echo "   Then run this script again."
    exit 1
fi

# Check if .env has actual keys
if grep -q "your_testnet_api_key_here" .env; then
    echo "⚠️  WARNING: .env file needs your API credentials!"
    echo ""
    echo "🔧 ACTION REQUIRED:"
    echo "   1. Go to https://testnet.bybit.com"
    echo "   2. Create account and generate API keys"
    echo "   3. Edit .env file:"
    echo "      nano .env"
    echo ""
    echo "   Then run this script again."
    exit 1
fi

echo "✅ .env file configured"
echo ""

# Step 5: Create logs directory
echo "📋 Step 5: Creating logs directory..."
mkdir -p logs
echo "✅ Logs directory ready"
echo ""

# Step 6: Run a quick test
echo "📋 Step 6: Testing connection..."
echo ""
echo "════════════════════════════════════════════════"
echo ""

# Run the bot
python main_simple.py

echo ""
echo "════════════════════════════════════════════════"
echo ""
echo "✅ OZZY Simple is ready!"
echo ""
echo "📚 Next steps:"
echo "   1. Let it run for 24 hours"
echo "   2. Check logs/trading.log for decisions"
echo "   3. Adjust thresholds if needed (config/config.py)"
echo ""
echo "🎯 Goal: 30+ decisions in 7 days, 5+ tradeable signals"
echo ""
echo "Press Ctrl+C to stop the bot"
