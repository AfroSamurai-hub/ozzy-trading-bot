#!/usr/bin/env python3
"""Check pattern label distribution in the vector DB."""

import sys
from pathlib import Path
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from intelligence.rolling_window_db import RollingWindowPatternDB

def check_labels():
    print("=" * 80)
    print("📚 PATTERN LABEL DISTRIBUTION CHECK")
    print("=" * 80)
    
    pattern_db = RollingWindowPatternDB()
    total = pattern_db.count()
    
    print(f"\nTotal patterns: {total}")
    
    if total == 0:
        print("⚠️  Database is empty!")
        return
    
    # Sample patterns to check labels
    sample_size = min(100, total)
    # Use 4-dimensional embedding (matching the existing patterns)
    dummy_embedding = [0.5, 0.5, 0.5, 0.5]
    
    try:
        results = pattern_db.query(embedding=dummy_embedding, k=sample_size)
        
        if results and 'metadatas' in results:
            labels = [m.get('label', 'PENDING') for m in results['metadatas']]
            label_counts = Counter(labels)
            
            print(f"\nLabel Distribution (sample of {len(labels)}):")
            for label, count in label_counts.most_common():
                pct = (count / len(labels)) * 100
                print(f"   {label}: {count} ({pct:.1f}%)")
            
            pending_count = label_counts.get('PENDING', 0)
            if pending_count == len(labels):
                print("\n⚠️  ALL SAMPLED PATTERNS ARE UNLABELED (PENDING)!")
                print("\n💡 TO FIX THIS:")
                print("   1. Start the labeler:")
                print("      python scripts/live_labeler.py")
                print("   2. Or use the helper script:")
                print("      bash scripts/start_labeler.sh")
                print("\n   The labeler will convert PENDING → WIN/LOSS/NEUTRAL")
                print("   based on actual price outcomes.")
            elif pending_count > 0:
                labeled = len(labels) - pending_count
                print(f"\n✅ {labeled} patterns labeled ({(labeled/len(labels)*100):.1f}%)")
                print(f"⏳ {pending_count} patterns still pending ({(pending_count/len(labels)*100):.1f}%)")
            else:
                print("\n✅ All sampled patterns are labeled!")
                
    except Exception as e:
        print(f"\n❌ Error checking labels: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    check_labels()
