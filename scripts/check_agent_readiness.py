#!/usr/bin/env python3
"""Check what the self-aware agent reports about its intelligence systems."""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

import asyncio
from agent.trader import TradingAgent
from intelligence.rolling_window_db import RollingWindowPatternDB
from mcp.trading_server import TradingMCPServer

async def check_readiness():
    """Check agent's self-reported readiness."""
    print("=" * 80)
    print("🔍 AGENT SELF-AWARENESS CHECK")
    print("=" * 80)
    
    # Initialize pattern DB and MCP server
    pattern_db = RollingWindowPatternDB()
    mcp_server = TradingMCPServer(pattern_db)
    
    # Initialize agent (will self-check during __init__)
    print("\n🤖 Initializing agent...\n")
    agent = TradingAgent(mcp_server, model="gpt-4o-mini")
    
    # Get readiness report
    readiness = agent.check_readiness()
    
    print("\n" + "=" * 80)
    print("📊 INTELLIGENCE SYSTEMS STATUS")
    print("=" * 80)
    
    systems = {
        "Pattern Intelligence": readiness['pattern_intelligence'],
        "Confidence Calculator": readiness['confidence_calculator'],
        "Pattern Manager": readiness['pattern_manager'],
        "Entry Spacing Manager": readiness['spacing_manager'],
    }
    
    for system, status in systems.items():
        icon = "✅" if status else "❌"
        print(f"{icon} {system}: {'READY' if status else 'MISSING'}")
    
    print("\n" + "=" * 80)
    print("🎯 OVERALL STATUS")
    print("=" * 80)
    print(f"Systems Ready: {readiness['systems_ready']}/4")
    print(f"Ready to Trade: {'✅ YES' if readiness['ready_to_trade'] else '❌ NO'}")
    print(f"Optimal Performance: {'✅ YES' if readiness['optimal'] else '⚠️  NO'}")
    
    if not readiness['optimal']:
        print("\n⚠️  AGENT NEEDS:")
        if not readiness['pattern_intelligence']:
            print("   - Pattern Intelligence (for historical win rates)")
        if not readiness['confidence_calculator']:
            print("   - Confidence Calculator (for dynamic confidence)")
        if not readiness['pattern_manager']:
            print("   - Pattern Manager (for pattern diversity)")
        if not readiness['spacing_manager']:
            print("   - Entry Spacing Manager (for entry timing)")
    else:
        print("\n🚀 All systems operational! Agent is FULLY SELF-AWARE!")
    
    # Check Pattern DB status
    print("\n" + "=" * 80)
    print("📚 PATTERN DATABASE STATUS")
    print("=" * 80)
    print(f"Total patterns: {pattern_db.count()}")
    
    # Check for labeled patterns
    try:
        sample = pattern_db.query(embedding=[0.0]*768, top_k=100)
        if sample and 'metadatas' in sample:
            labels = [m.get('label', 'PENDING') for m in sample['metadatas'][0]]
            from collections import Counter
            label_counts = Counter(labels)
            print("\nLabel Distribution (sample of 100):")
            for label, count in label_counts.most_common():
                print(f"   {label}: {count}")
            
            if label_counts.get('PENDING', 0) == len(labels):
                print("\n⚠️  ALL PATTERNS ARE UNLABELED!")
                print("   → Start the labeler: python scripts/live_labeler.py")
    except Exception as e:
        print(f"\n⚠️  Could not check pattern labels: {e}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    asyncio.run(check_readiness())
