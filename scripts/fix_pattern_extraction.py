#!/usr/bin/env python3
"""
🔧 FIX PATTERN EXTRACTION - Re-extract patterns from stored reasoning

This script fixes the "unknown_pattern" issue by:
1. Loading all trades from ChromaDB
2. Re-extracting patterns from reasoning text
3. Updating the metadata

Run this ONCE to fix existing data, then the fixed track_trade_outcomes.py
will store reasoning correctly going forward.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    print("❌ ChromaDB not available")
    sys.exit(1)


def extract_pattern(reasoning: str) -> str:
    """Extract pattern name from reasoning text (same logic as tracker)"""
    if not reasoning:
        return 'unknown_pattern'
    
    # Common patterns to look for
    patterns = [
        ('whale_accumulation', ['whale accumulation', 'whale_accumulation']),
        ('inverse_head_shoulders', ['inverse head', 'inverse_head_shoulders']),
        ('bullish_engulfing', ['bullish engulfing', 'bullish_engulfing']),
        ('bearish_divergence', ['bearish divergence', 'bearish_divergence']),
        ('bullish_divergence', ['bullish divergence', 'bullish_divergence']),
        ('hammer', ['hammer']),
        ('morning_star', ['morning star', 'morning_star']),
        ('three_white_soldiers', ['three white soldiers', 'three_white_soldiers']),
        ('pennant', ['pennant']),
        ('flag', [' flag']),  # Space before to avoid "flagged"
        ('triangle', ['triangle']),
        ('wedge', ['wedge']),
        ('double_bottom', ['double bottom', 'double_bottom']),
        ('cup_handle', ['cup and handle', 'cup_handle']),
        ('mixed_signals', ['mixed signals', 'mixed_signals'])
    ]
    
    reasoning_lower = reasoning.lower()
    
    for pattern_name, keywords in patterns:
        for keyword in keywords:
            if keyword in reasoning_lower:
                return pattern_name
    
    return 'unknown_pattern'


def main():
    print("="*70)
    print("🔧 FIXING PATTERN EXTRACTION")
    print("="*70)
    
    # Load ChromaDB
    client = chromadb.PersistentClient(
        path="data/trade_labels",
        settings=Settings(anonymized_telemetry=False)
    )
    db = client.get_collection(name="trade_outcomes")
    
    total = db.count()
    print(f"\n📊 Found {total} trades to process")
    
    if total == 0:
        print("✅ No trades to fix")
        return
    
    # Get all trades (with documents = reasoning)
    results = db.get(include=['metadatas', 'documents'])
    
    fixed_count = 0
    unknown_count = 0
    
    print("\n🔍 Processing trades...")
    print("-"*70)
    
    for trade_id, metadata, document in zip(results['ids'], results['metadatas'], results['documents']):
        old_pattern = metadata.get('pattern', 'unknown_pattern')
        reasoning = document if document else metadata.get('reasoning', '')
        
        # Re-extract pattern
        new_pattern = extract_pattern(reasoning)
        
        if old_pattern != new_pattern:
            # Update metadata
            metadata['pattern'] = new_pattern
            metadata['reasoning'] = reasoning  # Also add reasoning to metadata
            
            db.update(
                ids=[trade_id],
                metadatas=[metadata]
            )
            
            print(f"✅ {trade_id}")
            print(f"   Old: '{old_pattern}' → New: '{new_pattern}'")
            print(f"   Reasoning: {reasoning[:100]}...")
            fixed_count += 1
        
        if new_pattern == 'unknown_pattern':
            unknown_count += 1
            if reasoning:
                print(f"⚠️  {trade_id}: Still unknown despite having reasoning:")
                print(f"   {reasoning[:150]}...")
    
    print("\n" + "="*70)
    print("📊 SUMMARY")
    print("="*70)
    print(f"Total trades: {total}")
    print(f"Fixed: {fixed_count}")
    print(f"Still unknown: {unknown_count}")
    
    if unknown_count > 0:
        print(f"\n⚠️  {unknown_count} trades still have 'unknown_pattern'")
        print("   This means:")
        print("   1. Reasoning text doesn't contain known pattern keywords, OR")
        print("   2. Pattern keywords need to be added to the extraction logic")
        print("\n   Run with --show-unknown to see reasoning text")
    
    print("\n✅ Pattern extraction fixed!")
    print(f"   Removed 'unknown_pattern' multiplier if it exists...")
    
    # Remove unknown_pattern from learning multipliers
    mult_file = Path("data/learning_multipliers.json")
    if mult_file.exists():
        import json
        with open(mult_file) as f:
            multipliers = json.load(f)
        
        if 'unknown_pattern' in multipliers:
            del multipliers['unknown_pattern']
            with open(mult_file, 'w') as f:
                json.dump(multipliers, f, indent=2)
            print(f"   ✅ Removed 'unknown_pattern' from multipliers")
        else:
            print(f"   ✅ No 'unknown_pattern' in multipliers")


if __name__ == '__main__':
    main()
