#!/bin/bash

echo "🔑 OpenAI API Key Setup"
echo "============================================================"
echo ""
echo "Please paste your OpenAI API key below."
echo "(It should start with 'sk-')"
echo ""
echo "You can find it at: https://platform.openai.com/api-keys"
echo ""

# Read API key from user
read -p "Paste your OpenAI API key here: " API_KEY

# Trim whitespace
API_KEY=$(echo "$API_KEY" | xargs)

# Check if empty
if [ -z "$API_KEY" ]; then
    echo ""
    echo "❌ No API key entered. Exiting."
    exit 1
fi

# Check if starts with sk-
if [[ ! "$API_KEY" =~ ^sk- ]]; then
    echo ""
    echo "⚠️  Warning: API key doesn't start with 'sk-'"
    read -p "Continue anyway? (y/n): " CONFIRM
    if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
        echo "❌ Cancelled."
        exit 1
    fi
fi

# Check if .env exists and has OPENAI_API_KEY
if [ -f .env ] && grep -q "^OPENAI_API_KEY=" .env; then
    echo ""
    echo "⚠️  OPENAI_API_KEY already exists in .env"
    read -p "Replace it? (y/n): " CONFIRM
    if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
        echo "❌ Cancelled."
        exit 1
    fi
    
    # Replace existing key (works on both macOS and Linux)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$API_KEY|" .env
    else
        sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$API_KEY|" .env
    fi
else
    # Add new key to .env
    if [ ! -f .env ]; then
        # Create new .env file
        echo "# OpenAI Configuration" > .env
        echo "OPENAI_API_KEY=$API_KEY" >> .env
    else
        # Append to existing .env
        echo "" >> .env
        echo "# OpenAI Configuration" >> .env
        echo "OPENAI_API_KEY=$API_KEY" >> .env
    fi
fi

# Mask the key for display
MASKED_KEY="${API_KEY:0:7}...${API_KEY: -4}"

echo ""
echo "============================================================"
echo "✅ OpenAI API key added successfully!"
echo "   Key: $MASKED_KEY"
echo ""
echo "📋 Your .env file now contains:"
echo "----------------------------------------"
cat .env | grep -v "^OPENAI_API_KEY=" | head -15
echo "OPENAI_API_KEY=$MASKED_KEY"
echo "----------------------------------------"
echo ""
echo "Next steps:"
echo "1. ✅ Slack notifications are configured"
echo "2. ✅ OpenAI API key is set"
echo "3. Start the bot:"
echo ""
echo "   cd ~/ozzy-simple"
echo "   source venv/bin/activate"
echo "   python scripts/test_live_stream.py --symbol BTCUSDT --duration 43200 --decision-interval 60"
echo ""
echo "============================================================"
