#!/usr/bin/env python3
"""
🎯 OZZY - Master Control Script

The ONE command to rule them all. Everything seamlessly connected.

USAGE:
    ./ozzy.py status          # Complete status check (recommended)
    ./ozzy.py quick           # Quick glance
    ./ozzy.py test            # Test management
    ./ozzy.py portfolio       # Portfolio deep dive
    ./ozzy.py plan            # Project planning
    ./ozzy.py monitor         # Start live monitoring
    ./ozzy.py check           # Health check everything
    ./ozzy.py help            # Show all commands

NO MORE:
- "Is the test running?"
- "Let me check the portfolio..."
- "Where's that command again?"
- Opening multiple terminals

ONE COMMAND. COMPLETE VISIBILITY. 🚀
"""

import subprocess
import sys
import os
import json
import re
from datetime import datetime
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================

WORKSPACE = Path(__file__).parent
LOG_FILE = Path("/tmp/test_output.log")
PLANNER_DATA = WORKSPACE / "planner_data.json"
PORTFOLIO_STATE = WORKSPACE / "logs" / "portfolio_state.json"

# Colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
END = "\033[0m"

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def run_command(cmd, capture=True):
    """Run shell command and return output"""
    try:
        if capture:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=WORKSPACE)
            return result.stdout.strip()
        else:
            subprocess.run(cmd, shell=True, cwd=WORKSPACE)
            return None
    except Exception as e:
        return f"Error: {e}"

def get_test_status():
    """Check if test is running"""
    ps_output = run_command("ps aux | grep bulletproof_test | grep -v grep")
    if ps_output and "python" in ps_output:
        pid = ps_output.split()[1]
        return True, pid
    return False, None

def get_latest_decisions(count=5):
    """Get latest test decisions"""
    if not LOG_FILE.exists():
        return []
    
    decisions = []
    try:
        content = LOG_FILE.read_text()
        pattern = r'🎯 DECISION #(\d+)/\d+.*?Action: (\w+).*?Confidence: ([\d.]+)%'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for match in matches[-count:]:
            decisions.append({
                'number': int(match[0]),
                'action': match[1],
                'confidence': float(match[2])
            })
    except Exception:
        pass
    
    return decisions

def get_portfolio_summary():
    """Get portfolio summary from log"""
    if not LOG_FILE.exists():
        return None
    
    try:
        content = LOG_FILE.read_text()
        
        # Get latest capital
        capital_matches = list(re.finditer(r'Capital: R([\d,]+\.\d+)', content))
        if not capital_matches:
            return None
        
        current_capital = float(capital_matches[-1].group(1).replace(',', ''))
        
        # Count positions
        positions = len(set(re.findall(r'Position #(\d+) opened', content)))
        
        # Get decision count
        decision_count = len(re.findall(r'DECISION #(\d+)/', content))
        
        # Get signal distribution
        buy_count = len(re.findall(r'Action: BUY', content))
        sell_count = len(re.findall(r'Action: SELL', content))
        skip_count = len(re.findall(r'Action: SKIP', content))
        
        return {
            'capital': current_capital,
            'positions': positions,
            'decisions': decision_count,
            'signals': {'BUY': buy_count, 'SELL': sell_count, 'SKIP': skip_count}
        }
    except Exception:
        return None

def get_project_status():
    """Get project milestone status"""
    if not PLANNER_DATA.exists():
        return None
    
    try:
        with open(PLANNER_DATA, 'r') as f:
            data = json.load(f)
        return data
    except Exception:
        return None

def calculate_test_progress():
    """Calculate test progress"""
    if not LOG_FILE.exists():
        return None
    
    try:
        content = LOG_FILE.read_text()
        
        # Find total decisions
        total_match = re.search(r'DECISION #\d+/(\d+)', content)
        if not total_match:
            return None
        
        total = int(total_match.group(1))
        
        # Count completed decisions
        completed = len(re.findall(r'DECISION #(\d+)/', content))
        
        # Get start time
        start_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', content)
        start_time = None
        if start_match:
            start_time = datetime.strptime(start_match.group(1), '%Y-%m-%d %H:%M:%S')
        
        return {
            'total': total,
            'completed': completed,
            'percentage': (completed / total * 100) if total > 0 else 0,
            'start_time': start_time
        }
    except Exception:
        return None

# ============================================================================
# COMMAND HANDLERS
# ============================================================================

def cmd_status():
    """Complete status check - THE MAIN COMMAND"""
    print(f"\n{BOLD}{CYAN}{'='*70}{END}")
    print(f"{BOLD}{CYAN}🎯 OZZY COMPLETE STATUS{END}")
    print(f"{BOLD}{CYAN}{'='*70}{END}\n")
    
    # 1. TEST STATUS
    print(f"{BOLD}{BLUE}🧪 TEST STATUS{END}")
    print(f"{'-'*70}")
    
    test_running, pid = get_test_status()
    if test_running:
        print(f"Status: {GREEN}✅ RUNNING{END} (PID: {pid})")
        
        progress = calculate_test_progress()
        if progress:
            bar_length = 40
            filled = int(progress['percentage'] / 100 * bar_length)
            bar = f"{GREEN}{'█' * filled}{END}{'░' * (bar_length - filled)}"
            print(f"Progress: {progress['completed']}/{progress['total']} decisions ({progress['percentage']:.1f}%)")
            print(f"{bar} {progress['percentage']:.1f}%")
            
            if progress['start_time']:
                elapsed = datetime.now() - progress['start_time']
                elapsed_mins = elapsed.total_seconds() / 60
                print(f"Runtime: {int(elapsed_mins)} minutes")
                
                # Estimate completion
                if progress['completed'] > 0:
                    avg_interval = elapsed_mins / progress['completed']
                    remaining = (progress['total'] - progress['completed']) * avg_interval
                    print(f"Estimated completion: {int(remaining)} minutes")
    else:
        print(f"Status: {RED}❌ NOT RUNNING{END}")
        print(f"Start test: {YELLOW}cd scripts && python bulletproof_test.py{END}")
    
    print()
    
    # 2. LATEST DECISIONS
    decisions = get_latest_decisions(5)
    if decisions:
        print(f"{BOLD}{BLUE}🎯 LATEST DECISIONS{END}")
        print(f"{'-'*70}")
        for d in decisions:
            action_color = GREEN if d['action'] == 'BUY' else (RED if d['action'] == 'SELL' else YELLOW)
            conf_color = GREEN if d['confidence'] >= 70 else (YELLOW if d['confidence'] >= 40 else RED)
            print(f"Decision #{d['number']}: {action_color}{d['action']}{END} @ {conf_color}{d['confidence']:.1f}%{END}")
        print()
    
    # 3. PORTFOLIO SUMMARY
    portfolio = get_portfolio_summary()
    if portfolio:
        print(f"{BOLD}{BLUE}💰 PORTFOLIO SUMMARY{END}")
        print(f"{'-'*70}")
        
        capital_color = GREEN if portfolio['capital'] >= 10000 else (YELLOW if portfolio['capital'] >= 9000 else RED)
        print(f"Capital: {capital_color}R{portfolio['capital']:,.2f}{END}")
        print(f"Open Positions: {portfolio['positions']}")
        
        signals = portfolio['signals']
        total_signals = signals['BUY'] + signals['SELL'] + signals['SKIP']
        if total_signals > 0:
            print(f"Signals: {GREEN}{signals['BUY']} BUY{END}, {RED}{signals['SELL']} SELL{END}, {YELLOW}{signals['SKIP']} SKIP{END}")
            trade_rate = (signals['BUY'] + signals['SELL']) / total_signals * 100
            print(f"Trade Rate: {trade_rate:.1f}%")
        print()
    
    # 4. PROJECT STATUS
    project = get_project_status()
    if project:
        print(f"{BOLD}{BLUE}📋 PROJECT STATUS{END}")
        print(f"{'-'*70}")
        print(f"Current Phase: {project.get('current_phase', 'Unknown')}")
        
        completed = len(project.get('milestones_completed', []))
        print(f"Milestones Completed: {GREEN}{completed}{END}")
        
        # Show latest milestone
        if project.get('milestones_completed'):
            latest = project['milestones_completed'][-1]
            print(f"Latest: {GREEN}✅ {latest}{END}")
        
        print()
    
    # 5. QUICK ACTIONS
    print(f"{BOLD}{BLUE}⚡ QUICK ACTIONS{END}")
    print(f"{'-'*70}")
    print(f"Full portfolio:  {CYAN}./ozzy.py portfolio{END}")
    print(f"Project details: {CYAN}./ozzy.py plan{END}")
    print(f"Live monitor:    {CYAN}./ozzy.py monitor{END}")
    print(f"Quick check:     {CYAN}./ozzy.py quick{END}")
    print()
    
    print(f"{BOLD}{CYAN}{'='*70}{END}\n")

def cmd_quick():
    """Quick status glance"""
    print(f"\n{BOLD}{MAGENTA}⚡ QUICK STATUS{END}\n")
    
    # Test
    test_running, pid = get_test_status()
    test_icon = f"{GREEN}✅{END}" if test_running else f"{RED}❌{END}"
    print(f"{test_icon} Test: {'Running' if test_running else 'Stopped'}")
    
    # Progress
    progress = calculate_test_progress()
    if progress:
        print(f"   {progress['completed']}/{progress['total']} decisions ({progress['percentage']:.1f}%)")
    
    # Portfolio
    portfolio = get_portfolio_summary()
    if portfolio:
        capital_icon = f"{GREEN}💰{END}" if portfolio['capital'] >= 10000 else f"{YELLOW}💰{END}"
        print(f"{capital_icon} Capital: R{portfolio['capital']:,.2f}")
        print(f"   Positions: {portfolio['positions']} | Decisions: {portfolio['decisions']}")
    
    # Milestones
    project = get_project_status()
    if project:
        completed = len(project.get('milestones_completed', []))
        print(f"{GREEN}🎯{END} Milestones: {completed} completed")
    
    print()

def cmd_test():
    """Test management"""
    print(f"\n{BOLD}{BLUE}🧪 TEST MANAGEMENT{END}\n")
    
    test_running, pid = get_test_status()
    
    if test_running:
        print(f"Status: {GREEN}✅ RUNNING{END} (PID: {pid})\n")
        
        progress = calculate_test_progress()
        if progress:
            print(f"Progress: {progress['completed']}/{progress['total']} ({progress['percentage']:.1f}%)")
            
            if progress['start_time']:
                elapsed = datetime.now() - progress['start_time']
                print(f"Runtime: {elapsed}")
                
                # Next decision timing
                interval_mins = 15  # 15-minute intervals
                if progress['completed'] > 0:
                    next_decision_mins = interval_mins - (elapsed.total_seconds() / 60 % interval_mins)
                    print(f"Next decision: ~{int(next_decision_mins)} minutes")
        
        print(f"\n{YELLOW}Actions:{END}")
        print(f"  View log:  tail -f /tmp/test_output.log")
        print(f"  Stop test: kill {pid}")
        
    else:
        print(f"Status: {RED}❌ NOT RUNNING{END}\n")
        print(f"{YELLOW}Start test:{END}")
        print(f"  cd scripts && python bulletproof_test.py --duration 21600 --interval 900")
    
    print()

def cmd_portfolio():
    """Portfolio deep dive"""
    print(f"\n{BOLD}{GREEN}💰 PORTFOLIO ANALYSIS{END}\n")
    
    # Run the dedicated portfolio tracker
    run_command("python3 track_portfolio.py --detailed", capture=False)
    
    print()

def cmd_plan():
    """Project planning"""
    print(f"\n{BOLD}{CYAN}📋 PROJECT PLANNING{END}\n")
    
    # Show status
    run_command("python3 MASTER_PLANNER.py status", capture=False)
    
    print(f"\n{YELLOW}Next actions:{END}")
    print(f"  See next:     python3 MASTER_PLANNER.py next")
    print(f"  Complete:     python3 MASTER_PLANNER.py complete <id>")
    print(f"  Check idea:   python3 MASTER_PLANNER.py caniburn '<idea>'")
    print(f"  Motivation:   python3 MASTER_PLANNER.py motivate")
    print()

def cmd_monitor():
    """Start live monitoring"""
    print(f"\n{BOLD}{BLUE}📊 Starting live monitoring dashboard...{END}\n")
    print(f"{YELLOW}Press Ctrl+C to exit{END}\n")
    
    # Check if test is running
    test_running, _ = get_test_status()
    if not test_running:
        print(f"{RED}⚠️  Warning: Test is not running!{END}")
        print(f"Start test first: cd scripts && python bulletproof_test.py\n")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            return
    
    # Run the dashboard
    run_command("python3 monitor_dashboard.py", capture=False)

def cmd_check():
    """Health check everything"""
    print(f"\n{BOLD}{CYAN}🏥 HEALTH CHECK{END}\n")
    
    checks = []
    
    # 1. Test process
    test_running, pid = get_test_status()
    checks.append(("Test Process", test_running, f"PID {pid}" if pid else "Not running"))
    
    # 2. Log file
    log_exists = LOG_FILE.exists()
    log_size = LOG_FILE.stat().st_size if log_exists else 0
    checks.append(("Log File", log_exists, f"{log_size / 1024:.1f} KB" if log_exists else "Missing"))
    
    # 3. Planner data
    planner_exists = PLANNER_DATA.exists()
    checks.append(("Planner Data", planner_exists, "Present" if planner_exists else "Missing"))
    
    # 4. Portfolio state
    portfolio_exists = PORTFOLIO_STATE.exists()
    checks.append(("Portfolio State", portfolio_exists, "Present" if portfolio_exists else "Missing"))
    
    # 5. Scripts
    scripts_exist = (WORKSPACE / "scripts" / "bulletproof_test.py").exists()
    checks.append(("Test Script", scripts_exist, "Present" if scripts_exist else "Missing"))
    
    # 6. Monitor dashboard
    monitor_exists = (WORKSPACE / "monitor_dashboard.py").exists()
    checks.append(("Monitor Dashboard", monitor_exists, "Present" if monitor_exists else "Missing"))
    
    # 7. Portfolio tracker
    tracker_exists = (WORKSPACE / "track_portfolio.py").exists()
    checks.append(("Portfolio Tracker", tracker_exists, "Present" if tracker_exists else "Missing"))
    
    # Print results
    for name, status, info in checks:
        icon = f"{GREEN}✅{END}" if status else f"{RED}❌{END}"
        print(f"{icon} {name:20s} {info}")
    
    # Summary
    passed = sum(1 for _, status, _ in checks if status)
    total = len(checks)
    
    print(f"\n{BOLD}Summary: {passed}/{total} checks passed{END}")
    
    if passed == total:
        print(f"{GREEN}🎉 All systems operational!{END}\n")
    else:
        print(f"{YELLOW}⚠️  Some issues detected{END}\n")

def cmd_help():
    """Show help"""
    print(__doc__)
    
    print(f"\n{BOLD}{CYAN}AVAILABLE COMMANDS:{END}\n")
    
    commands = [
        ("status", "Complete status check (RECOMMENDED)", "🎯"),
        ("quick", "Quick status glance", "⚡"),
        ("test", "Test management & progress", "🧪"),
        ("portfolio", "Portfolio deep dive", "💰"),
        ("plan", "Project planning & milestones", "📋"),
        ("monitor", "Start live monitoring dashboard", "📊"),
        ("check", "Health check all components", "🏥"),
        ("help", "Show this help", "❓"),
    ]
    
    for cmd, desc, icon in commands:
        print(f"  {icon} {CYAN}{cmd:12s}{END} - {desc}")
    
    print(f"\n{BOLD}{YELLOW}EXAMPLES:{END}")
    print(f"  ./ozzy.py status          # See everything")
    print(f"  ./ozzy.py quick           # Quick glance")
    print(f"  ./ozzy.py portfolio       # Detailed portfolio")
    print(f"  ./ozzy.py monitor         # Live dashboard")
    
    print(f"\n{BOLD}{GREEN}TIP:{END} Run './ozzy.py status' every hour to stay updated!\n")

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point"""
    
    # Make script executable if not already
    script_path = Path(__file__)
    if not os.access(script_path, os.X_OK):
        os.chmod(script_path, 0o755)
    
    if len(sys.argv) < 2:
        print(f"\n{YELLOW}Usage: ./ozzy.py <command>{END}")
        print(f"Run './ozzy.py help' for available commands\n")
        print(f"{BOLD}Quick start: ./ozzy.py status{END}\n")
        return
    
    command = sys.argv[1].lower()
    
    commands = {
        'status': cmd_status,
        'quick': cmd_quick,
        'test': cmd_test,
        'portfolio': cmd_portfolio,
        'plan': cmd_plan,
        'monitor': cmd_monitor,
        'check': cmd_check,
        'help': cmd_help,
    }
    
    if command in commands:
        commands[command]()
    else:
        print(f"\n{RED}Unknown command: {command}{END}")
        print(f"Run './ozzy.py help' for available commands\n")

if __name__ == "__main__":
    main()
