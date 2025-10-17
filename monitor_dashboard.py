#!/usr/bin/env python3
"""
🔥 OZZY LIVE MONITORING DASHBOARD

Real-time CLI dashboard for monitoring trading test progress.
Shows decisions, signals, confidence, portfolio, and system status.

USAGE:
    python3 monitor_dashboard.py
    python3 monitor_dashboard.py --log /tmp/test_output.log
"""

import os
import sys
import time
import re
from datetime import datetime
from pathlib import Path
import subprocess

# Configuration
LOG_FILE = "/tmp/test_output.log"
REFRESH_INTERVAL = 2  # seconds
PLANNER_FILE = Path(__file__).parent / "MASTER_PLANNER.py"


class Colors:
    """Terminal colors"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def clear_screen():
    """Clear terminal screen"""
    os.system('clear' if os.name == 'posix' else 'cls')


def get_terminal_size():
    """Get terminal dimensions"""
    try:
        rows, columns = os.popen('stty size', 'r').read().split()
        return int(rows), int(columns)
    except:
        return 40, 120


def parse_log_file(log_file):
    """Parse the test log file for key metrics"""
    
    if not os.path.exists(log_file):
        return {
            'test_running': False,
            'decisions': [],
            'total_decisions': 0,
            'completed_decisions': 0,
            'capital': 10000.0,
            'open_positions': 0,
            'start_time': None,
            'last_update': None
        }
    
    try:
        with open(log_file, 'r') as f:
            content = f.read()
    except:
        return {'test_running': False}
    
    data = {
        'test_running': True,
        'decisions': [],
        'total_decisions': 24,
        'completed_decisions': 0,
        'capital': 10000.0,
        'open_positions': 0,
        'start_time': None,
        'last_update': datetime.now()
    }
    
    # Extract start time
    start_match = re.search(r'Start Time: ([\d\-:\s.]+)', content)
    if start_match:
        try:
            data['start_time'] = datetime.strptime(start_match.group(1).split('.')[0], '%Y-%m-%d %H:%M:%S')
        except:
            pass
    
    # Extract expected decisions
    expected_match = re.search(r'Expected Decisions: (\d+)', content)
    if expected_match:
        data['total_decisions'] = int(expected_match.group(1))
    
    # Extract all decisions
    decision_pattern = r'🎯 DECISION #(\d+)/(\d+).*?Action: (\w+).*?Confidence: ([\d.]+)%.*?(?:Price: R([\d,.]+)|Entry price: ([\d.]+))'
    decisions = re.finditer(decision_pattern, content, re.DOTALL)
    
    for match in decisions:
        decision_num = int(match.group(1))
        action = match.group(3)
        confidence = float(match.group(4))
        price = match.group(5) or match.group(6) or "N/A"
        
        if isinstance(price, str) and price != "N/A":
            price = price.replace(',', '')
        
        data['decisions'].append({
            'number': decision_num,
            'action': action,
            'confidence': confidence,
            'price': price
        })
        data['completed_decisions'] = decision_num
    
    # Extract latest portfolio status
    capital_matches = list(re.finditer(r'Capital: R([\d,]+\.\d+)', content))
    if capital_matches:
        data['capital'] = float(capital_matches[-1].group(1).replace(',', ''))
    
    positions_matches = list(re.finditer(r'Open Positions: (\d+)', content))
    if positions_matches:
        data['open_positions'] = int(positions_matches[-1].group(1))
    
    return data


def get_process_status():
    """Check if test process is running"""
    try:
        result = subprocess.run(
            ['ps', 'aux'],
            capture_output=True,
            text=True
        )
        
        for line in result.stdout.split('\n'):
            if 'bulletproof_test.py' in line and 'grep' not in line:
                parts = line.split()
                return {
                    'running': True,
                    'pid': parts[1],
                    'cpu': parts[2],
                    'mem': parts[3],
                    'time': parts[9]
                }
        
        return {'running': False}
    except:
        return {'running': False}


def get_planner_status():
    """Get current phase and milestone from planner"""
    try:
        if not PLANNER_FILE.exists():
            return None
        
        result = subprocess.run(
            ['python3', str(PLANNER_FILE), 'status'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        output = result.stdout
        
        # Extract phase
        phase_match = re.search(r'CURRENT PHASE: (.+)', output)
        phase = phase_match.group(1) if phase_match else "Unknown"
        
        # Extract progress
        progress_match = re.search(r'Progress: (\d+)/(\d+) \((\d+)%\)', output)
        if progress_match:
            completed = int(progress_match.group(1))
            total = int(progress_match.group(2))
            percent = int(progress_match.group(3))
            progress = f"{completed}/{total} ({percent}%)"
        else:
            progress = "0/0 (0%)"
        
        return {
            'phase': phase,
            'progress': progress
        }
    except:
        return None


def format_time_elapsed(start_time):
    """Format elapsed time"""
    if not start_time:
        return "N/A"
    
    elapsed = datetime.now() - start_time
    hours = int(elapsed.total_seconds() // 3600)
    minutes = int((elapsed.total_seconds() % 3600) // 60)
    seconds = int(elapsed.total_seconds() % 60)
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def render_dashboard(data, process_status, planner_status):
    """Render the complete dashboard"""
    
    clear_screen()
    rows, cols = get_terminal_size()
    
    # Header
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*cols}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}🔥 OZZY LIVE MONITORING DASHBOARD{Colors.ENDC}".center(cols + 20))
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*cols}{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.ENDC}\n")
    
    # Process Status
    print(f"{Colors.BOLD}🖥️  PROCESS STATUS:{Colors.ENDC}")
    if process_status['running']:
        print(f"  {Colors.OKGREEN}✅ RUNNING{Colors.ENDC}")
        print(f"  PID: {process_status['pid']} | CPU: {process_status['cpu']}% | MEM: {process_status['mem']}% | Time: {process_status['time']}")
    else:
        print(f"  {Colors.FAIL}❌ NOT RUNNING{Colors.ENDC}")
    print()
    
    # Planner Status
    if planner_status:
        print(f"{Colors.BOLD}🎯 PROJECT STATUS:{Colors.ENDC}")
        print(f"  Phase: {planner_status['phase']}")
        print(f"  Progress: {planner_status['progress']}")
        print()
    
    # Test Progress
    if data['test_running']:
        completed = data['completed_decisions']
        total = data['total_decisions']
        percent = (completed / total * 100) if total > 0 else 0
        
        print(f"{Colors.BOLD}📊 TEST PROGRESS:{Colors.ENDC}")
        print(f"  Decisions: {completed}/{total} ({percent:.1f}%)")
        
        # Progress bar
        bar_width = min(50, cols - 20)
        filled = int(bar_width * completed / total) if total > 0 else 0
        bar = '█' * filled + '░' * (bar_width - filled)
        print(f"  [{bar}]")
        
        if data['start_time']:
            elapsed = format_time_elapsed(data['start_time'])
            print(f"  Elapsed: {elapsed}")
            
            # Estimate remaining time
            if completed > 0:
                avg_time_per_decision = (datetime.now() - data['start_time']).total_seconds() / completed
                remaining_seconds = avg_time_per_decision * (total - completed)
                remaining_hours = int(remaining_seconds // 3600)
                remaining_minutes = int((remaining_seconds % 3600) // 60)
                print(f"  Estimated Remaining: {remaining_hours:02d}:{remaining_minutes:02d}:00")
        print()
    
    # Portfolio Status
    print(f"{Colors.BOLD}💼 PORTFOLIO:{Colors.ENDC}")
    print(f"  Capital: {Colors.OKGREEN}R{data['capital']:,.2f}{Colors.ENDC}")
    print(f"  Open Positions: {data['open_positions']}")
    
    if data['capital'] != 10000.0:
        pnl = data['capital'] - 10000.0
        pnl_color = Colors.OKGREEN if pnl >= 0 else Colors.FAIL
        pnl_symbol = '+' if pnl >= 0 else ''
        print(f"  P&L: {pnl_color}{pnl_symbol}R{pnl:,.2f} ({pnl_symbol}{pnl/10000*100:.2f}%){Colors.ENDC}")
    print()
    
    # Recent Decisions
    if data['decisions']:
        print(f"{Colors.BOLD}📈 RECENT DECISIONS:{Colors.ENDC}")
        
        # Show last 10 decisions
        recent = data['decisions'][-10:]
        
        # Calculate signal distribution
        signal_counts = {'BUY': 0, 'SELL': 0, 'SKIP': 0, 'LONG': 0, 'SHORT': 0}
        confidence_sum = 0
        
        for d in data['decisions']:
            signal_counts[d['action']] = signal_counts.get(d['action'], 0) + 1
            confidence_sum += d['confidence']
        
        avg_confidence = confidence_sum / len(data['decisions']) if data['decisions'] else 0
        
        print(f"\n  Signal Distribution:")
        for action, count in signal_counts.items():
            if count > 0:
                percent = count / len(data['decisions']) * 100
                print(f"    {action}: {count} ({percent:.1f}%)")
        
        print(f"  Average Confidence: {avg_confidence:.1f}%")
        print()
        
        # Table header
        print(f"  {'#':<4} {'Action':<8} {'Confidence':<12} {'Price':<15}")
        print(f"  {'-'*4} {'-'*8} {'-'*12} {'-'*15}")
        
        for d in recent:
            action = d['action']
            
            # Color code actions
            if action in ['BUY', 'LONG']:
                action_colored = f"{Colors.OKGREEN}{action}{Colors.ENDC}"
            elif action in ['SELL', 'SHORT']:
                action_colored = f"{Colors.FAIL}{action}{Colors.ENDC}"
            else:
                action_colored = f"{Colors.WARNING}{action}{Colors.ENDC}"
            
            # Color code confidence
            conf = d['confidence']
            if conf >= 70:
                conf_colored = f"{Colors.OKGREEN}{conf:.1f}%{Colors.ENDC}"
            elif conf >= 50:
                conf_colored = f"{Colors.WARNING}{conf:.1f}%{Colors.ENDC}"
            else:
                conf_colored = f"{Colors.FAIL}{conf:.1f}%{Colors.ENDC}"
            
            price = f"R{d['price']}" if d['price'] != 'N/A' else 'N/A'
            
            print(f"  {d['number']:<4} {action_colored:<17} {conf_colored:<21} {price:<15}")
        
        print()
    
    # Footer
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*cols}{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Refreshing every {REFRESH_INTERVAL}s | Press Ctrl+C to exit{Colors.ENDC}".center(cols + 20))
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*cols}{Colors.ENDC}")


def main():
    """Main dashboard loop"""
    
    log_file = LOG_FILE
    
    # Check for command line args
    if len(sys.argv) > 2 and sys.argv[1] == '--log':
        log_file = sys.argv[2]
    
    print(f"{Colors.OKGREEN}Starting OZZY Monitoring Dashboard...{Colors.ENDC}")
    print(f"Watching: {log_file}")
    print(f"Refresh: {REFRESH_INTERVAL}s\n")
    time.sleep(2)
    
    try:
        while True:
            # Gather data
            data = parse_log_file(log_file)
            process_status = get_process_status()
            planner_status = get_planner_status()
            
            # Render
            render_dashboard(data, process_status, planner_status)
            
            # Wait
            time.sleep(REFRESH_INTERVAL)
            
    except KeyboardInterrupt:
        clear_screen()
        print(f"\n{Colors.OKGREEN}Dashboard stopped. Goodbye!{Colors.ENDC}\n")
        sys.exit(0)
    except Exception as e:
        clear_screen()
        print(f"\n{Colors.FAIL}Error: {e}{Colors.ENDC}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
