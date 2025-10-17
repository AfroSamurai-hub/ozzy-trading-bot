#!/usr/bin/env python3
"""
💰 PORTFOLIO TRACKER - Quick Capital & Trade Status

Shows current capital, positions, and P&L at a glance.

USAGE:
    python3 track_portfolio.py
    python3 track_portfolio.py --detailed
"""

import sys
import re
from pathlib import Path
from datetime import datetime

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
BOLD = '\033[1m'
END = '\033[0m'

LOG_FILE = "/tmp/test_output.log"
STARTING_CAPITAL = 10000.0


def parse_log():
    """Extract capital and position info from log"""
    
    if not Path(LOG_FILE).exists():
        return None
    
    with open(LOG_FILE, 'r') as f:
        content = f.read()
    
    # Get latest capital
    capital_matches = list(re.finditer(r'Capital: R([\d,]+\.\d+)', content))
    current_capital = STARTING_CAPITAL
    if capital_matches:
        current_capital = float(capital_matches[-1].group(1).replace(',', ''))
    
    # Get open positions
    positions = []
    position_pattern = r'Position #(\d+) opened @ R([\d,.]+)'
    for match in re.finditer(position_pattern, content):
        pos_id = int(match.group(1))
        entry_price = float(match.group(2).replace(',', ''))
        
        # Find latest status for this position
        status_pattern = f'Position #{pos_id}: ([+-]?[\d.]+)%'
        status_matches = list(re.finditer(status_pattern, content))
        pnl_pct = 0.0
        if status_matches:
            pnl_pct = float(status_matches[-1].group(1))
        
        positions.append({
            'id': pos_id,
            'entry': entry_price,
            'pnl_pct': pnl_pct
        })
    
    # Count decisions
    decisions = len(re.findall(r'🎯 DECISION #\d+/\d+', content))
    
    # Count signals
    buy_count = len(re.findall(r'Action: BUY', content))
    sell_count = len(re.findall(r'Action: SELL', content))
    skip_count = len(re.findall(r'Action: SKIP', content))
    
    return {
        'current_capital': current_capital,
        'positions': positions,
        'decisions': decisions,
        'buy_count': buy_count,
        'sell_count': sell_count,
        'skip_count': skip_count
    }


def display_status(data, detailed=False):
    """Display portfolio status"""
    
    if not data:
        print(f"{RED}❌ No test data found. Is the test running?{END}")
        return
    
    # Header
    print(f"\n{BOLD}{BLUE}{'='*70}{END}")
    print(f"{BOLD}{BLUE}💰 PORTFOLIO STATUS{END}")
    print(f"{BOLD}{BLUE}{'='*70}{END}\n")
    
    # Capital
    current = data['current_capital']
    allocated = STARTING_CAPITAL - current
    pnl = current - STARTING_CAPITAL
    pnl_pct = (pnl / STARTING_CAPITAL) * 100
    
    print(f"{BOLD}📊 CAPITAL:{END}")
    print(f"  Starting:  {GREEN}R{STARTING_CAPITAL:,.2f}{END}")
    print(f"  Current:   {GREEN if current >= STARTING_CAPITAL else RED}R{current:,.2f}{END}")
    print(f"  Allocated: {YELLOW}R{allocated:,.2f}{END} ({allocated/STARTING_CAPITAL*100:.1f}%)")
    
    if pnl != 0:
        pnl_color = GREEN if pnl >= 0 else RED
        pnl_symbol = '+' if pnl >= 0 else ''
        print(f"  P&L:       {pnl_color}{pnl_symbol}R{pnl:,.2f} ({pnl_symbol}{pnl_pct:.2f}%){END}")
    
    print()
    
    # Positions
    print(f"{BOLD}📈 POSITIONS:{END}")
    if data['positions']:
        print(f"  Open: {len(data['positions'])}")
        
        if detailed:
            print()
            for pos in data['positions']:
                pnl_color = GREEN if pos['pnl_pct'] >= 0 else RED
                pnl_symbol = '+' if pos['pnl_pct'] >= 0 else ''
                print(f"  Position #{pos['id']}:")
                print(f"    Entry: R{pos['entry']:,.2f}")
                print(f"    P&L:   {pnl_color}{pnl_symbol}{pos['pnl_pct']:.2f}%{END}")
        else:
            avg_pnl = sum(p['pnl_pct'] for p in data['positions']) / len(data['positions'])
            pnl_color = GREEN if avg_pnl >= 0 else RED
            pnl_symbol = '+' if avg_pnl >= 0 else ''
            print(f"  Avg P&L: {pnl_color}{pnl_symbol}{avg_pnl:.2f}%{END}")
    else:
        print(f"  {YELLOW}No open positions{END}")
    
    print()
    
    # Signals
    print(f"{BOLD}🎯 TRADING ACTIVITY:{END}")
    print(f"  Decisions: {data['decisions']}")
    print(f"  Signals:   {GREEN}{data['buy_count']} BUY{END}, {RED}{data['sell_count']} SELL{END}, {YELLOW}{data['skip_count']} SKIP{END}")
    
    trade_signals = data['buy_count'] + data['sell_count']
    if data['decisions'] > 0:
        print(f"  Trade Rate: {trade_signals}/{data['decisions']} ({trade_signals/data['decisions']*100:.1f}%)")
    
    print()
    
    # Footer
    print(f"{BOLD}{BLUE}{'='*70}{END}")
    print(f"{BLUE}📍 Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{END}")
    print(f"{BLUE}{'='*70}{END}\n")


def main():
    """Main function"""
    
    detailed = '--detailed' in sys.argv or '-d' in sys.argv
    
    print(f"{BOLD}Loading portfolio data...{END}")
    data = parse_log()
    display_status(data, detailed)
    
    # Show commands
    print(f"{BOLD}💡 QUICK COMMANDS:{END}")
    print(f"  Full status:  {YELLOW}python3 track_portfolio.py --detailed{END}")
    print(f"  Live log:     {YELLOW}tail -f /tmp/test_output.log{END}")
    print(f"  Dashboard:    {YELLOW}python3 monitor_dashboard.py{END}")
    print()


if __name__ == "__main__":
    main()
