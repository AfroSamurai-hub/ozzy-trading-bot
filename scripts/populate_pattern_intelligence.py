#!/usr/bin/env python3
"""
🧠 Populate Pattern Intelligence with Simulated Trade Data

This script generates realistic trade outcomes for patterns in the database
to test the AI's ability to calibrate confidence based on pattern effectiveness.

Strategy:
1. Get patterns from ChromaDB (2,314 patterns available)
2. Assign realistic win rates based on pattern type:
   - Strong patterns (bullish_divergence, golden_cross): 65-75% win rate
   - Medium patterns (volume_surge, ema_crossover): 55-65% win rate
   - Weak patterns (consolidation, mixed_signals): 45-55% win rate
3. Simulate 5-20 trades per pattern (varying sample sizes)
4. Generate realistic P&L based on TP/SL: +3.5% wins, -1.5% losses
5. Save to pattern_stats.json
"""

import os
import sys
import random
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from intelligence.pattern_intelligence import get_intelligence
from intelligence.rolling_window_db import RollingWindowPatternDB

# Pattern type categories with expected performance
PATTERN_PERFORMANCE = {
    # Strong bullish patterns (65-75% win rate)
    'bullish_divergence': (0.65, 0.75),
    'golden_cross': (0.65, 0.72),
    'bullish_engulfing': (0.62, 0.72),
    'hammer': (0.60, 0.70),
    
    # Medium patterns (55-65% win rate)
    'volume_surge': (0.55, 0.65),
    'ema_crossover': (0.55, 0.63),
    'price_momentum': (0.53, 0.63),
    'support_bounce': (0.55, 0.65),
    
    # Weak/neutral patterns (45-55% win rate)
    'consolidation': (0.45, 0.55),
    'mixed_signals': (0.48, 0.55),
    'range_bound': (0.45, 0.52),
    'sideways': (0.47, 0.53),
    
    # Default for unknown patterns
    'default': (0.50, 0.60),
}

def get_pattern_win_rate_range(pattern_type: str) -> tuple:
    """Get expected win rate range for a pattern type"""
    pattern_type_lower = pattern_type.lower()
    
    # Check exact match first
    if pattern_type_lower in PATTERN_PERFORMANCE:
        return PATTERN_PERFORMANCE[pattern_type_lower]
    
    # Check partial matches
    for key, win_range in PATTERN_PERFORMANCE.items():
        if key in pattern_type_lower or pattern_type_lower in key:
            return win_range
    
    # Default range
    return PATTERN_PERFORMANCE['default']

def simulate_trades_for_pattern(pattern_id: str, pattern_type: str, num_trades: int = None) -> list:
    """
    Simulate trade outcomes for a pattern with market context.
    
    🎓 PhD-LEVEL: Now includes regime, session, and volatility context!
    
    Args:
        pattern_id: Pattern identifier
        pattern_type: Type of pattern (determines win rate)
        num_trades: Number of trades to simulate (random 5-20 if not specified)
    
    Returns:
        List of trade outcomes with context
    """
    if num_trades is None:
        # Vary sample sizes: some patterns have more history than others
        num_trades = random.randint(5, 20)
    
    # Get expected win rate range for this pattern type
    win_rate_min, win_rate_max = get_pattern_win_rate_range(pattern_type)
    target_win_rate = random.uniform(win_rate_min, win_rate_max)
    
    # Calculate number of wins/losses
    num_wins = round(num_trades * target_win_rate)
    num_losses = num_trades - num_wins
    
    # Market contexts to simulate
    regimes = ['bull_market', 'bear_market', 'sideways', 'volatile']
    sessions = ['asian_early', 'asian_late', 'european', 'us', 'overlap']
    volatilities = ['low_vol', 'medium_vol', 'high_vol']
    
    # Generate trade outcomes
    outcomes = []
    
    # Wins: +3.5% average (some variation)
    for _ in range(num_wins):
        pnl_pct = random.uniform(2.5, 4.5)  # Vary around +3.5%
        held_time = random.randint(1800, 7200)  # 30min - 2 hours
        
        # 🎓 Add realistic market context
        # Some patterns work better in certain contexts
        regime = random.choice(regimes)
        session = random.choice(sessions)
        volatility = random.choice(volatilities)
        
        # Boost win rate in favorable contexts
        if pattern_type in ['bullish_divergence', 'golden_cross'] and regime == 'bull_market':
            pnl_pct *= 1.1  # Patterns work better in right regime
        elif pattern_type in ['consolidation', 'mixed_signals'] and volatility == 'low_vol':
            pnl_pct *= 1.05
        
        outcomes.append({
            'win': True,
            'pnl_pct': pnl_pct,
            'held_time': held_time,
            'market_regime': regime,
            'trading_session': session,
            'volatility': volatility
        })
    
    # Losses: -1.5% average (some hit SL, some manual exit)
    for _ in range(num_losses):
        pnl_pct = random.uniform(-2.0, -1.0)  # Vary around -1.5%
        held_time = random.randint(900, 3600)  # 15min - 1 hour (cut losses faster)
        
        # 🎓 Add market context (losses tend to happen in unfavorable contexts)
        regime = random.choice(regimes)
        session = random.choice(sessions)
        volatility = random.choice(volatilities)
        
        # Patterns fail more in wrong contexts
        if pattern_type in ['bullish_divergence', 'golden_cross'] and regime == 'bear_market':
            regime = 'bear_market'  # Force unfavorable context
        
        outcomes.append({
            'win': False,
            'pnl_pct': pnl_pct,
            'held_time': held_time,
            'market_regime': regime,
            'trading_session': session,
            'volatility': volatility
        })
    
    # Shuffle so wins/losses are random order
    random.shuffle(outcomes)
    
    return outcomes

def main():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                                                            ║")
    print("║     🧠 POPULATING PATTERN INTELLIGENCE WITH DATA 🧠      ║")
    print("║                                                            ║")
    print("╚════════════════════════════════════════════════════════════╝\n")
    
    # Initialize pattern database
    print("1️⃣ Loading pattern database...")
    db = RollingWindowPatternDB()
    
    # Get all pattern IDs from ChromaDB
    collection_data = db.collection.get()
    all_pattern_ids = collection_data['ids']
    all_metadatas = collection_data['metadatas']
    
    print(f"   ✅ Found {len(all_pattern_ids)} patterns in database\n")
    
    # Initialize pattern intelligence
    print("2️⃣ Initializing pattern intelligence...")
    intelligence = get_intelligence()
    print(f"   ✅ Pattern intelligence ready\n")
    
    # Get existing stats to avoid duplicating work
    existing_stats = intelligence.stats_cache  # Access stats cache
    patterns_with_data = len([s for s in existing_stats.values() if s.times_traded > 0])
    print(f"3️⃣ Current state:")
    print(f"   - Patterns with stats: {len(existing_stats)}")
    print(f"   - Patterns with trade data: {patterns_with_data}\n")
    
    # Decide how many patterns to populate (don't do all 2,314 at once!)
    target_patterns = min(100, len(all_pattern_ids))
    print(f"4️⃣ Simulating trades for {target_patterns} patterns...")
    print(f"   (You can run this script multiple times to add more)\n")
    
    # Sample patterns to populate (create tuple of (id, metadata))
    pattern_indices = random.sample(range(len(all_pattern_ids)), target_patterns)
    patterns_to_populate = [(all_pattern_ids[i], all_metadatas[i]) for i in pattern_indices]
    
    populated_count = 0
    total_trades = 0
    
    for i, (pattern_id, metadata) in enumerate(patterns_to_populate, 1):
        pattern_type = metadata.get('pattern_type', 'unknown')
        
        # Skip if already has data
        if pattern_id in existing_stats and existing_stats[pattern_id].times_traded > 0:
            continue
        
        # Simulate trades
        num_trades = random.randint(5, 20)
        outcomes = simulate_trades_for_pattern(pattern_id, pattern_type, num_trades)
        
        # Update intelligence with each trade outcome
        for outcome in outcomes:
            intelligence.update_pattern_outcome(pattern_id, outcome)
        
        populated_count += 1
        total_trades += num_trades
        
        # Progress indicator every 10 patterns
        if i % 10 == 0:
            stats = intelligence.get_pattern_stats(pattern_id)
            print(f"   [{i:3d}/{target_patterns}] {pattern_type:20s} | "
                  f"{stats.win_rate:5.1%} win rate ({stats.wins}W/{stats.losses}L) | "
                  f"Expectancy: {stats.expectancy:+.2f}%")
    
    print(f"\n5️⃣ Saving results...")
    intelligence._save_stats()
    
    # Get final stats
    final_stats = intelligence.stats_cache
    patterns_with_trades = len([s for s in final_stats.values() if s.times_traded > 0])
    
    print(f"\n╔════════════════════════════════════════════════════════════╗")
    print(f"║                                                            ║")
    print(f"║              ✅ PATTERN INTELLIGENCE POPULATED! ✅        ║")
    print(f"║                                                            ║")
    print(f"╚════════════════════════════════════════════════════════════╝")
    print(f"\n📊 Final Statistics:")
    print(f"   - Patterns populated: {populated_count}")
    print(f"   - Total simulated trades: {total_trades}")
    print(f"   - Patterns with data: {patterns_with_trades}")
    print(f"   - Data saved to: data/pattern_stats.json\n")
    
    # Show top 5 patterns
    print("🏆 Top 5 performing patterns:")
    top_patterns = intelligence.get_top_patterns(n=5, min_trades=5)
    for i, p in enumerate(top_patterns, 1):
        print(f"   {i}. {p['pattern_type']:20s} | "
              f"Win Rate: {p['win_rate']:5.1%} ({p['wins']:2d}W/{p['losses']:2d}L) | "
              f"Expectancy: {p['expectancy']:+.2f}% | "
              f"Confidence: {p['confidence_score']:.2f}")
    
    print("\n💡 Next steps:")
    print("   1. Run: python scripts/test_self_aware_agent.py")
    print("   2. Check AI confidence (should be 60-85% range now)")
    print("   3. Verify AI cites specific win rates in reasoning")
    print("   4. Run this script again to add more pattern data!\n")

if __name__ == "__main__":
    main()
