#!/bin/bash
# Network Diagnostic Tool - Check Cloudflare and Internet Connection

echo "======================================================================="
echo "🔍 NETWORK DIAGNOSTIC TOOL"
echo "======================================================================="
echo ""
echo "Checking your internet and Cloudflare connection..."
echo ""

# 1. Basic connectivity
echo "1️⃣ BASIC CONNECTIVITY"
echo "-------------------"
echo -n "Can reach Google DNS (8.8.8.8): "
if ping -c 2 -W 2 8.8.8.8 >/dev/null 2>&1; then
    echo "✅ YES"
else
    echo "❌ NO - Basic internet down!"
fi

echo -n "Can reach Cloudflare DNS (1.1.1.1): "
if ping -c 2 -W 2 1.1.1.1 >/dev/null 2>&1; then
    echo "✅ YES"
else
    echo "❌ NO - Cloudflare unreachable!"
fi

echo ""

# 2. DNS Resolution
echo "2️⃣ DNS RESOLUTION"
echo "-------------------"
echo -n "Can resolve cloudflare.com: "
if nslookup cloudflare.com >/dev/null 2>&1; then
    echo "✅ YES"
else
    echo "❌ NO - DNS issues!"
fi

echo -n "Can resolve google.com: "
if nslookup google.com >/dev/null 2>&1; then
    echo "✅ YES"
else
    echo "❌ NO - DNS issues!"
fi

echo ""

# 3. Current DNS servers
echo "3️⃣ CURRENT DNS CONFIGURATION"
echo "-------------------"
echo "Your DNS servers:"
cat /etc/resolv.conf | grep nameserver
echo ""

# 4. Network interfaces
echo "4️⃣ NETWORK INTERFACES"
echo "-------------------"
ip addr show | grep -E "^[0-9]+:|inet " | head -20
echo ""

# 5. Active connections
echo "5️⃣ ACTIVE CONNECTIONS"
echo "-------------------"
echo "Established connections:"
netstat -tn 2>/dev/null | grep ESTABLISHED | wc -l
echo ""

# 6. Packet loss test
echo "6️⃣ PACKET LOSS TEST"
echo "-------------------"
echo "Testing Cloudflare (1.1.1.1):"
ping -c 10 -i 0.2 1.1.1.1 2>&1 | tail -2
echo ""

echo "Testing Google (8.8.8.8):"
ping -c 10 -i 0.2 8.8.8.8 2>&1 | tail -2
echo ""

# 7. Route check
echo "7️⃣ ROUTE TO CLOUDFLARE"
echo "-------------------"
echo "Traceroute to 1.1.1.1 (first 5 hops):"
traceroute -m 5 -w 1 1.1.1.1 2>&1 | head -10
echo ""

# 8. Check if using Cloudflare WARP
echo "8️⃣ CLOUDFLARE WARP STATUS"
echo "-------------------"
if command -v warp-cli &> /dev/null; then
    echo "Cloudflare WARP installed"
    warp-cli status 2>&1 || echo "WARP not responding"
else
    echo "Cloudflare WARP not installed"
fi
echo ""

# 9. Check for connection drops
echo "9️⃣ MONITORING FOR DROPS (10 seconds)"
echo "-------------------"
echo "Watching for disconnections..."
for i in {1..10}; do
    if ! ping -c 1 -W 1 1.1.1.1 >/dev/null 2>&1; then
        echo "⚠️  Drop detected at second $i"
    else
        echo -n "✅ "
    fi
    sleep 1
done
echo ""
echo ""

# 10. Recommendations
echo "======================================================================="
echo "🔧 RECOMMENDATIONS"
echo "======================================================================="
echo ""

# Check if packet loss detected
if ping -c 10 -W 2 1.1.1.1 2>&1 | grep -q "100% packet loss"; then
    echo "❌ CRITICAL: Total packet loss to Cloudflare!"
    echo ""
    echo "Try these fixes:"
    echo "1. systemctl restart NetworkManager"
    echo "2. nmcli connection down <connection-name> && nmcli connection up <connection-name>"
    echo "3. sudo systemctl restart systemd-resolved"
    echo ""
elif ping -c 10 -W 2 1.1.1.1 2>&1 | grep -qE "[1-9][0-9]?% packet loss"; then
    echo "⚠️  WARNING: Packet loss detected!"
    echo ""
    echo "Common causes:"
    echo "- WiFi interference"
    echo "- ISP issues"
    echo "- Router problems"
    echo ""
    echo "Try:"
    echo "1. Restart router"
    echo "2. Check WiFi signal strength"
    echo "3. Switch to wired connection"
    echo ""
else
    echo "✅ Connection looks stable"
    echo ""
    echo "If you're still experiencing disconnects:"
    echo "1. Check browser extensions (especially VPN/proxy)"
    echo "2. Check firewall settings"
    echo "3. Monitor with: watch -n 1 'ping -c 1 1.1.1.1'"
    echo ""
fi

echo "======================================================================="
echo "📝 QUICK FIXES TO TRY"
echo "======================================================================="
echo ""
echo "Fix 1: Restart Network Manager"
echo "   sudo systemctl restart NetworkManager"
echo ""
echo "Fix 2: Flush DNS cache"
echo "   sudo systemd-resolve --flush-caches"
echo ""
echo "Fix 3: Reset DNS to Cloudflare"
echo "   echo 'nameserver 1.1.1.1' | sudo tee /etc/resolv.conf"
echo "   echo 'nameserver 1.0.0.1' | sudo tee -a /etc/resolv.conf"
echo ""
echo "Fix 4: Disable IPv6 (if causing issues)"
echo "   sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1"
echo ""
echo "Fix 5: Check if WARP is causing issues"
echo "   warp-cli disconnect"
echo ""
echo "Fix 6: Continuous monitoring (watch for drops)"
echo "   watch -n 1 'ping -c 1 1.1.1.1 || echo DROPPED'"
echo ""
echo "======================================================================="
