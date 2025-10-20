#!/usr/bin/env python3
"""
Add realistic volume ratios to existing trades for testing.

This is a temporary script to test the volume analyzer logic.
Real volume calculation will be integrated during Paper Trading Week.
"""

import sys
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    print("❌ ChromaDB not available")
    sys.exit(1)


def add_realistic_volumes():
    """
    Add realistic volume ratios to test trades.
    
    Based on Mt.Gox research:
    - ~40% of trades have high volume (>1.5×)
    - ~60% have normal/low volume (≤1.5×)
    
    Strategy:
    - Give better outcomes high volume more often
    - Give worse outcomes low volume more often
    - This should show the Mt.Gox effect (+23 points)
    """
    
    client = chromadb.PersistentClient(
        path="data/trade_labels",
        settings=Settings(anonymized_telemetry=False)
    )
    db = client.get_collection(name="trade_outcomes")
    
    # Get all trades
    results = db.get(include=['embeddings', 'metadatas', 'documents'])
    
    if db.count() == 0:
        print("❌ No trades to update")
        return
    
    print(f"📊 Updating {db.count()} trades with realistic volume ratios...")
    print("-" * 70)
    
    # Update each trade
    for i, (doc_id, metadata, document) in enumerate(zip(results['ids'], results['metadatas'], results['documents'])):
        outcome = metadata['outcome']
        
        # Bias volume ratios based on outcome (to simulate Mt.Gox effect)
        if outcome in ['BIG_WIN', 'WIN']:
            # Winners: 70% chance of high volume
            if random.random() < 0.7:
                volume_ratio = round(random.uniform(1.6, 3.0), 2)
            else:
                volume_ratio = round(random.uniform(0.8, 1.4), 2)
        else:  # LOSS, BIG_LOSS, BREAKEVEN
            # Losers: 30% chance of high volume
            if random.random() < 0.3:
                volume_ratio = round(random.uniform(1.6, 3.0), 2)
            else:
                volume_ratio = round(random.uniform(0.8, 1.4), 2)
        
        # Update metadata
        metadata['volume_ratio'] = volume_ratio
        
        # Update in ChromaDB
        db.update(
            ids=[doc_id],
            metadatas=[metadata]
        )
        
        print(f"  Trade {i+1}: {outcome:12} → volume_ratio = {volume_ratio:.2f}×")
    
    print("\n✅ Volume ratios updated!")
    
    # Show updated statistics
    print("\n📊 UPDATED STATISTICS:")
    print("-" * 70)
    
    results = db.get(include=['metadatas'])
    high_volume = [m for m in results['metadatas'] if m.get('volume_ratio', 1.0) > 1.5]
    low_volume = [m for m in results['metadatas'] if m.get('volume_ratio', 1.0) <= 1.5]
    
    print(f"High Volume (>1.5×): {len(high_volume)} trades")
    print(f"Low Volume (≤1.5×): {len(low_volume)} trades")
    
    # Win rates
    if high_volume:
        hv_wins = len([m for m in high_volume if m['outcome'] in ['WIN', 'BIG_WIN']])
        hv_wr = hv_wins / len(high_volume)
        print(f"\nHigh Volume Win Rate: {hv_wr*100:.0f}% ({hv_wins}/{len(high_volume)})")
    
    if low_volume:
        lv_wins = len([m for m in low_volume if m['outcome'] in ['WIN', 'BIG_WIN']])
        lv_wr = lv_wins / len(low_volume)
        print(f"Low Volume Win Rate: {lv_wr*100:.0f}% ({lv_wins}/{len(low_volume)})")
    
    if high_volume and low_volume:
        delta = (hv_wr - lv_wr) * 100
        print(f"\nDelta: {delta:+.0f} percentage points")
        print(f"Expected (Mt.Gox): +23 percentage points")


if __name__ == '__main__':
    add_realistic_volumes()
