#!/bin/bash
# Quick Fix for Cloudflare WARP Connection Drops

echo "======================================================================="
echo "🔧 CLOUDFLARE WARP FIX"
echo "======================================================================="
echo ""
echo "Detected: Cloudflare WARP is active and may be causing disconnects"
echo ""
echo "Choose a fix:"
echo ""
echo "1) Disconnect WARP (keeps it installed)"
echo "2) Switch WARP to proxy mode (less intrusive)"
echo "3) Disable WARP service completely"
echo "4) Just show WARP status"
echo "5) Exit (no changes)"
echo ""
read -p "Enter choice [1-5]: " choice

case $choice in
    1)
        echo ""
        echo "Disconnecting WARP..."
        warp-cli disconnect
        echo ""
        echo "✅ WARP disconnected"
        echo "Testing connection..."
        sleep 2
        ping -c 5 8.8.8.8
        ;;
    2)
        echo ""
        echo "Switching WARP to proxy mode..."
        warp-cli set-mode proxy
        warp-cli disconnect
        warp-cli connect
        echo ""
        echo "✅ WARP set to proxy mode"
        echo "Testing connection..."
        sleep 2
        ping -c 5 8.8.8.8
        ;;
    3)
        echo ""
        echo "Disabling WARP service..."
        warp-cli disconnect
        sudo systemctl stop warp-svc
        sudo systemctl disable warp-svc
        echo ""
        echo "✅ WARP service disabled"
        echo "Testing connection..."
        sleep 2
        ping -c 5 8.8.8.8
        ;;
    4)
        echo ""
        echo "WARP Status:"
        warp-cli status
        echo ""
        echo "WARP Settings:"
        warp-cli settings
        ;;
    5)
        echo ""
        echo "No changes made."
        exit 0
        ;;
    *)
        echo ""
        echo "❌ Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "======================================================================="
echo "📊 CONNECTION TEST RESULTS"
echo "======================================================================="
echo ""

echo -n "Cloudflare DNS (1.1.1.1): "
if ping -c 3 -W 2 1.1.1.1 >/dev/null 2>&1; then
    echo "✅ Working"
else
    echo "❌ Still having issues"
fi

echo -n "Google DNS (8.8.8.8): "
if ping -c 3 -W 2 8.8.8.8 >/dev/null 2>&1; then
    echo "✅ Working"
else
    echo "❌ Still having issues"
fi

echo ""
echo "To re-enable WARP later:"
echo "   warp-cli connect"
echo ""
echo "To monitor connection stability:"
echo "   watch -n 1 'ping -c 1 1.1.1.1 || echo DROP'"
echo ""
