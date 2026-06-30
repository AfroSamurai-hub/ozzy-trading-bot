#!/usr/bin/env python3
"""
Build complete signal review database including REJECTED signals from logs.
This creates entries for rejected signals and matches them to outcomes.
"""

import json
import re
from datetime import datetime, timedelta

SIGNAL_REVIEWS_FILE = "/home/rick/ozzy-bot/signal_reviews.json"
WEBHOOK_LOG = "/home/rick/ozzy-bot/webhook.log"
TRADES_LOG = "/home/rick/ozzy-bot/trades.log"
PAPER_TRADES_FILE = "/home/rick/ozzy-bot/paper_trades.json"

def parse_all_rejections():
    """Extract all REJECTED events from both log files"""
    rejections = []
    
    for log_file in [WEBHOOK_LOG, TRADES_LOG]:
        try:
            with open(log_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # JSON format
                    if line.startswith('{'):
                        try:
                            data = json.loads(line)
                            if data.get('event') == 'REJECTED':
                                rejections.append({
                                    'ts': data.get('ts', ''),
                                    'symbol': data.get('symbol', ''),
                                    'signal': data.get('signal', ''),
                                    'reason': data.get('reason', ''),
                                    'source': log_file
                                })
                        except json.JSONDecodeError:
                            pass
                    
                    # Old format
                    elif 'REJECTED:' in line:
                        match = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] REJECTED: (.+)', line)
                        if match:
                            ts = match.group(1)
                            reason = match.group(2)
                            # Try to extract symbol from nearby lines or context
                            rejections.append({
                                'ts': ts,
                                'symbol': '',
                                'signal': '',
                                'reason': reason,
                                'source': log_file
                            })
        except FileNotFoundError:
            pass
    
    return rejections

def normalize_rejection_reason(reason):
    """Normalize to standard filter name"""
    reason_lower = reason.lower()
    
    if 'rsi' in reason_lower and ('exhaustion' in reason_lower or 'above' in reason_lower or 'below' in reason_lower):
        return 'rsi_exhaustion'
    elif 'outside trading hours' in reason_lower:
        return 'kill_zone'
    elif 'kill zone' in reason_lower:
        return 'kill_zone'
    elif 'supertrend' in reason_lower or 'live data conflict' in reason_lower:
        return 'supertrend_conflict'
    elif 'sl' in reason_lower and ('tight' in reason_lower or 'below minimum' in reason_lower or 'atr' in reason_lower):
        return 'sl_too_tight'
    elif 'max concurrent' in reason_lower or 'position' in reason_lower:
        return 'max_positions'
    elif 'cache' in reason_lower or 'timed out' in reason_lower:
        return 'system_error'
    elif '400' in reason_lower or 'bad request' in reason_lower:
        return 'system_error'
    else:
        return 'other'

def load_paper_trades():
    """Load paper trades to check outcomes"""
    try:
        with open(PAPER_TRADES_FILE, 'r') as f:
            data = json.load(f)
        return data.get('trades', [])
    except Exception:
        return []

def find_outcome_for_rejection(rejection, paper_trades):
    """Check if we have outcome data for a rejected signal"""
    rej_ts = rejection.get('ts', '')
    rej_symbol = rejection.get('symbol', '')
    
    if not rej_ts:
        return None
    
    try:
        rej_dt = datetime.fromisoformat(rej_ts.replace('Z', '+00:00'))
    except Exception:
        return None
    
    # Look for matching paper trade within 5 minutes
    for trade in paper_trades:
        trade_ts = trade.get('ts', '')
        trade_symbol = trade.get('symbol', '')
        
        if not trade_ts:
            continue
        
        try:
            trade_dt = datetime.fromisoformat(trade_ts.replace('Z', '+00:00'))
        except Exception:
            continue
        
        diff = abs((rej_dt - trade_dt).total_seconds())
        
        # Within 5 minutes and same symbol
        if diff <= 300 and rej_symbol == trade_symbol:
            return {
                'outcome': trade.get('status'),
                'exit_ts': trade.get('exit_ts'),
                'exit_price': trade.get('exit_price'),
                'pnl_points': trade.get('pnl_points')
            }
    
    return None

def main():
    print("="*80)
    print("BUILDING COMPLETE SIGNAL REVIEW DATABASE")
    print("="*80)
    print()
    
    # Load existing approved reviews
    with open(SIGNAL_REVIEWS_FILE, 'r') as f:
        data = json.load(f)
    
    existing_reviews = data.get('reviews', [])
    print(f"Existing approved reviews: {len(existing_reviews)}")
    
    # Load all rejections from logs
    rejections = parse_all_rejections()
    print(f"Rejected signals from logs: {len(rejections)}")
    
    # Load paper trades for outcome matching
    paper_trades = load_paper_trades()
    print(f"Paper trades for outcome matching: {len(paper_trades)}")
    print()
    
    # Build rejected signal reviews
    rejected_reviews = []
    
    for rej in rejections:
        # Skip if missing critical data
        if not rej.get('ts') or not rej.get('symbol'):
            continue
        
        # Normalize reason
        filter_name = normalize_rejection_reason(rej['reason'])
        
        # Try to find outcome
        outcome_data = find_outcome_for_rejection(rej, paper_trades)
        
        review = {
            'id': f"{rej['ts']}:rejected:{rej['symbol']}:{rej.get('signal', 'UNKNOWN')}",
            'ts': rej['ts'],
            'decision': 'rejected',
            'symbol': rej['symbol'],
            'signal': rej.get('signal', ''),
            'rejection_reason': filter_name,
            'rejection_detail': rej['reason'],
            'outcome': outcome_data.get('outcome') if outcome_data else None,
            'outcome_status': 'resolved' if outcome_data else 'pending',
            'exit_ts': outcome_data.get('exit_ts') if outcome_data else None,
            'exit_price': outcome_data.get('exit_price') if outcome_data else None,
            'pnl_points': outcome_data.get('pnl_points') if outcome_data else None,
            'source': 'log_extraction'
        }
        
        rejected_reviews.append(review)
    
    print(f"Created rejected reviews: {len(rejected_reviews)}")
    
    # Merge with existing reviews
    all_reviews = existing_reviews + rejected_reviews
    
    # Remove duplicates (same ts + symbol + decision)
    seen = set()
    unique_reviews = []
    for review in all_reviews:
        key = (review.get('ts'), review.get('symbol'), review.get('decision'))
        if key not in seen:
            seen.add(key)
            unique_reviews.append(review)
    
    print(f"Total unique reviews: {len(unique_reviews)}")
    print()
    
    # Update data
    data['reviews'] = unique_reviews
    
    # Save
    with open(SIGNAL_REVIEWS_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print("✓ Saved updated signal reviews")
    print()
    
    # Generate filter performance table
    print("="*80)
    print("FILTER PERFORMANCE TABLE")
    print("="*80)
    print()
    
    filter_stats = {}
    resolved_count = 0
    
    for review in unique_reviews:
        if review.get('outcome_status') != 'resolved':
            continue
        
        if review.get('decision') != 'rejected':
            continue  # Only count rejected signals for filter performance
        
        resolved_count += 1
        reason = review.get('rejection_reason', 'other')
        outcome = review.get('outcome')
        
        # Calculate R multiple
        if outcome == 'win':
            r_multiple = 2.5  # Assume standard RR
        elif outcome == 'loss':
            r_multiple = -1.0
        else:
            r_multiple = 0
        
        if reason not in filter_stats:
            filter_stats[reason] = {
                'signals': 0,
                'winners_blocked': 0,
                'losers_blocked': 0,
                'net_r': 0.0
            }
        
        filter_stats[reason]['signals'] += 1
        
        if outcome == 'win':
            filter_stats[reason]['winners_blocked'] += 1
            filter_stats[reason]['net_r'] += r_multiple
        elif outcome == 'loss':
            filter_stats[reason]['losers_blocked'] += 1
            filter_stats[reason]['net_r'] += r_multiple
    
    print(f"Resolved rejected signals: {resolved_count}")
    print()
    
    if filter_stats:
        # Sort by absolute net R impact
        sorted_filters = sorted(filter_stats.items(), key=lambda x: abs(x[1]['net_r']), reverse=True)
        
        print(f"{'Filter':<25} {'Signals':>8} {'Winners':>10} {'Losers':>10} {'Net R':>10} {'Status'}")
        print("-"*80)
        
        for filter_name, stats in sorted_filters:
            signals = stats['signals']
            winners = stats['winners_blocked']
            losers = stats['losers_blocked']
            net_r = stats['net_r']
            
            if net_r > 5:
                status = "🔴 REVIEW"
            elif net_r > 0:
                status = "⚠️  Loosen"
            elif net_r < -3:
                status = "✅ Tighten"
            else:
                status = "✅ Working"
            
            print(f"{filter_name:<25} {signals:>8} {winners:>10} {losers:>10} {net_r:>+10.2f} {status}")
    else:
        print("No resolved rejected signals with outcomes found")
    
    print("="*80)
    print()
    
    # Decision audit
    print("="*80)
    print("DECISION AUDIT")
    print("="*80)
    print()
    
    # RSI decision
    rsi_stats = filter_stats.get('rsi_exhaustion', {'signals': 0, 'winners_blocked': 0, 'net_r': 0})
    print("1. RSI Loosening (78→80, 22→20)")
    print(f"   Signals blocked: {rsi_stats['signals']}")
    print(f"   Winners blocked: {rsi_stats['winners_blocked']}")
    print(f"   Net R impact: {rsi_stats['net_r']:+.2f}")
    if rsi_stats['net_r'] > 3:
        print("   ✅ DECISION JUSTIFIED")
    elif rsi_stats['winners_blocked'] >= 2:
        print("   ✅ DECISION JUSTIFIED (multiple winners)")
    elif rsi_stats['signals'] == 0:
        print("   ❌ NO DATA: No RSI rejections found in logs")
    else:
        print("   ⚠️  MARGINAL: Limited data")
    print()
    
    # Kill zone decision
    kz_stats = filter_stats.get('kill_zone', {'signals': 0, 'winners_blocked': 0, 'net_r': 0})
    print("2. Kill Zone Bypass (EUR/GBP/JPY)")
    print(f"   Signals blocked: {kz_stats['signals']}")
    print(f"   Winners blocked: {kz_stats['winners_blocked']}")
    print(f"   Net R impact: {kz_stats['net_r']:+.2f}")
    if kz_stats['net_r'] > 3:
        print("   ✅ DECISION JUSTIFIED")
    elif kz_stats['winners_blocked'] >= 2:
        print("   ✅ DECISION JUSTIFIED (multiple winners)")
    elif kz_stats['signals'] == 0:
        print("   ❌ NO DATA: No kill zone rejections found")
    else:
        print("   ⚠️  MARGINAL: Limited data")
    print()
    
    # BTCUSD decision
    print("3. BTCUSD Paper Mode")
    btc_rejections = [r for r in rejected_reviews if 'BTC' in r.get('symbol', '')]
    btc_resolved = [r for r in btc_rejections if r.get('outcome_status') == 'resolved']
    btc_wins = len([r for r in btc_resolved if r.get('outcome') == 'win'])
    btc_losses = len([r for r in btc_resolved if r.get('outcome') == 'loss'])
    
    print(f"   BTC rejections found: {len(btc_rejections)}")
    print(f"   With outcomes: {len(btc_resolved)}")
    print(f"   Would-be wins: {btc_wins}")
    print(f"   Would-be losses: {btc_losses}")
    
    if btc_resolved:
        wr = btc_wins / len(btc_resolved) * 100
        print(f"   Would-be win rate: {wr:.1f}%")
        if wr < 40:
            print("   ✅ PAPER MODE JUSTIFIED: Low win rate")
        else:
            print("   ⚠️  RE-EVALUATE: Win rate acceptable")
    else:
        print("   ❌ NO OUTCOME DATA for BTC rejections")
    
    print()
    print("="*80)

if __name__ == "__main__":
    main()
