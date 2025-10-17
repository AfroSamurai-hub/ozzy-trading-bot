#!/usr/bin/env python3
"""
🧠 OZZY SYSTEM CONTEXT ENGINE

**PURPOSE:**
Make the system SELF-AWARE so it can resume from ANY point - even after 5 years.

**THE GOAL:**
Build a profitable trading bot that makes R5k-10k/week so you can QUIT YOUR 9-TO-5.

**HOW IT WORKS:**
1. Reads EVERYTHING (test logs, portfolio, planner, code state)
2. Understands WHERE WE ARE (current milestone, progress, blockers)
3. Knows WHAT'S NEXT (immediate actions, dependencies, priorities)
4. Provides CONTEXT (why we're here, what we've built, what matters)

**USAGE:**
    python3 SYSTEM_CONTEXT.py                    # Full context report
    python3 SYSTEM_CONTEXT.py --next             # What to do next
    python3 SYSTEM_CONTEXT.py --resume           # Resume from any state
    python3 SYSTEM_CONTEXT.py --health           # System health check
    python3 SYSTEM_CONTEXT.py --progress         # Progress to goal

This is the BRAIN. Everything else is the BODY.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ============================================================================
# SYSTEM CONSTANTS - THE NORTH STAR
# ============================================================================

ULTIMATE_GOAL = "Make R5,000-10,000/week profit → QUIT THE 9-TO-5"
CURRENT_PHASE = "Phase 1: Foundation - Get Profitable FAST"
SUCCESS_METRIC = "R5,000/week minimum profit"
TIME_BUDGET = "30 days to profitability"

# File locations
ROOT_DIR = Path(__file__).parent
PLANNER_FILE = ROOT_DIR / "MASTER_PLANNER.py"
PLANNER_DATA = ROOT_DIR / "planner_data.json"
TEST_LOG = Path("/tmp/test_output.log")
TEST_PID_FILE = Path("/tmp/test_pid.txt")

# ============================================================================
# SYSTEM STATE DETECTION
# ============================================================================

class SystemState:
    """Detect and understand current system state"""
    
    def __init__(self):
        self.timestamp = datetime.now()
        self.test_state = self._detect_test_state()
        self.portfolio_state = self._detect_portfolio_state()
        self.planner_state = self._detect_planner_state()
        self.code_state = self._detect_code_state()
        self.health_state = self._detect_health_state()
    
    def _detect_test_state(self) -> Dict:
        """Detect if test is running and its progress"""
        state = {
            "running": False,
            "pid": None,
            "progress": 0,
            "decisions": {"total": 0, "completed": 0},
            "runtime_minutes": 0,
            "crashes": 0,
            "last_decision": None
        }
        
        # Check if test is running
        try:
            ps_cmd = "ps aux | grep bulletproof_test | grep -v grep"
            result = subprocess.run(ps_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout:
                state["running"] = True
                pid = result.stdout.split()[1]
                state["pid"] = pid
        except Exception as e:
            pass
        
        # Parse test log if exists
        if TEST_LOG.exists():
            try:
                with open(TEST_LOG, 'r') as f:
                    log_content = f.read()
                
                # Extract decisions
                import re
                decisions = re.findall(r'DECISION #(\d+)', log_content)
                if decisions:
                    state["decisions"]["completed"] = len(decisions)
                    state["last_decision"] = int(decisions[-1])
                
                # Extract total from test start
                total_match = re.search(r'Total decisions: (\d+)', log_content)
                if total_match:
                    state["decisions"]["total"] = int(total_match.group(1))
                
                # Calculate progress
                if state["decisions"]["total"] > 0:
                    state["progress"] = (state["decisions"]["completed"] / 
                                       state["decisions"]["total"]) * 100
                
                # Extract runtime
                start_match = re.search(r'Test started at: ([\d\-: ]+)', log_content)
                if start_match:
                    start_time = datetime.strptime(start_match.group(1), 
                                                  "%Y-%m-%d %H:%M:%S")
                    runtime = (datetime.now() - start_time).total_seconds() / 60
                    state["runtime_minutes"] = int(runtime)
                
            except Exception as e:
                pass
        
        return state
    
    def _detect_portfolio_state(self) -> Dict:
        """Detect portfolio state from test log"""
        state = {
            "capital_available": 10000,
            "capital_allocated": 0,
            "positions": [],
            "trades": {"buy": 0, "sell": 0, "skip": 0},
            "pnl": 0.0
        }
        
        if not TEST_LOG.exists():
            return state
        
        try:
            with open(TEST_LOG, 'r') as f:
                log_content = f.read()
            
            import re
            
            # Count actions
            state["trades"]["buy"] = len(re.findall(r'Action: BUY', log_content))
            state["trades"]["sell"] = len(re.findall(r'Action: SELL', log_content))
            state["trades"]["skip"] = len(re.findall(r'Action: SKIP', log_content))
            
            # Find latest capital
            capital_matches = re.findall(r'Capital: R([\d,\.]+)', log_content)
            if capital_matches:
                latest = capital_matches[-1].replace(',', '')
                state["capital_available"] = float(latest)
            
            # Extract positions (simplified - could parse more detail)
            position_matches = re.findall(r'Position #(\d+)', log_content)
            state["positions"] = list(set(position_matches))
            
        except Exception as e:
            pass
        
        return state
    
    def _detect_planner_state(self) -> Dict:
        """Detect planner state from planner_data.json"""
        state = {
            "phase": "phase_1",
            "milestones_total": 9,
            "milestones_complete": 0,
            "current_milestone": None,
            "blockers": [],
            "days_active": 0
        }
        
        if not PLANNER_DATA.exists():
            return state
        
        try:
            with open(PLANNER_DATA, 'r') as f:
                data = json.load(f)
            
            state["phase"] = data.get("current_phase", "phase_1")
            
            # Count completed milestones
            completed = data.get("completed_milestones", {})
            state["milestones_complete"] = len(completed)
            
            # Find current milestone (first incomplete)
            # This would need to parse MASTER_PLANNER.py for full accuracy
            # For now, estimate based on completed count
            if state["milestones_complete"] == 2:
                state["current_milestone"] = "1.2"  # Stability Test
            
            # Calculate days active
            start_date_str = data.get("start_date")
            if start_date_str:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                state["days_active"] = (datetime.now() - start_date).days
            
        except Exception as e:
            pass
        
        return state
    
    def _detect_code_state(self) -> Dict:
        """Detect code infrastructure state"""
        state = {
            "master_control": False,
            "planner": False,
            "monitoring": False,
            "tracking": False,
            "sops": [],
            "core_agent": False
        }
        
        # Check for key files
        state["master_control"] = (ROOT_DIR / "ozzy.py").exists()
        state["planner"] = PLANNER_FILE.exists()
        state["monitoring"] = (ROOT_DIR / "monitor_dashboard.py").exists()
        state["tracking"] = (ROOT_DIR / "track_portfolio.py").exists()
        state["core_agent"] = (ROOT_DIR / "agent" / "trader.py").exists()
        
        # List SOPs
        sop_dir = ROOT_DIR / "docs" / "sops"
        if sop_dir.exists():
            state["sops"] = [f.name for f in sop_dir.glob("SOP-*.md")]
        
        return state
    
    def _detect_health_state(self) -> Dict:
        """Detect system health"""
        state = {
            "status": "UNKNOWN",
            "issues": [],
            "warnings": []
        }
        
        # Check critical files
        if not (ROOT_DIR / "agent" / "trader.py").exists():
            state["issues"].append("Core trading agent missing")
        
        if not PLANNER_FILE.exists():
            state["issues"].append("Master planner missing")
        
        # Check test state
        if self.test_state["running"]:
            if self.test_state["crashes"] > 0:
                state["warnings"].append(f"Test has crashed {self.test_state['crashes']} times")
        
        # Overall status
        if len(state["issues"]) == 0:
            state["status"] = "HEALTHY"
        elif len(state["issues"]) < 3:
            state["status"] = "DEGRADED"
        else:
            state["status"] = "CRITICAL"
        
        return state

# ============================================================================
# CONTEXT INTELLIGENCE
# ============================================================================

class ContextEngine:
    """Understand what to do next based on current state"""
    
    def __init__(self, state: SystemState):
        self.state = state
    
    def get_context_report(self) -> str:
        """Generate comprehensive context report"""
        report = []
        report.append("=" * 70)
        report.append("🧠 OZZY SYSTEM CONTEXT REPORT")
        report.append("=" * 70)
        report.append(f"\n📅 Generated: {self.state.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # THE GOAL
        report.append("🎯 THE ULTIMATE GOAL")
        report.append("-" * 70)
        report.append(f"   {ULTIMATE_GOAL}")
        report.append(f"   Current Phase: {CURRENT_PHASE}")
        report.append(f"   Success Metric: {SUCCESS_METRIC}")
        report.append(f"   Time Budget: {TIME_BUDGET}\n")
        
        # WHERE WE ARE
        report.append("📍 WHERE WE ARE NOW")
        report.append("-" * 70)
        report.append(f"   Days Active: {self.state.planner_state['days_active']}")
        report.append(f"   Milestones: {self.state.planner_state['milestones_complete']}/{self.state.planner_state['milestones_total']} " +
                     f"({(self.state.planner_state['milestones_complete']/self.state.planner_state['milestones_total']*100):.0f}%)")
        report.append(f"   Current Milestone: {self.state.planner_state.get('current_milestone', 'Unknown')}\n")
        
        # TEST STATUS
        if self.state.test_state["running"]:
            report.append("🧪 ACTIVE TEST")
            report.append("-" * 70)
            report.append(f"   Status: RUNNING (PID {self.state.test_state['pid']})")
            report.append(f"   Progress: {self.state.test_state['decisions']['completed']}/{self.state.test_state['decisions']['total']} " +
                         f"({self.state.test_state['progress']:.1f}%)")
            report.append(f"   Runtime: {self.state.test_state['runtime_minutes']} minutes")
            report.append(f"   Crashes: {self.state.test_state['crashes']}\n")
        else:
            report.append("🧪 NO ACTIVE TEST\n")
        
        # PORTFOLIO
        report.append("💰 PORTFOLIO STATUS")
        report.append("-" * 70)
        report.append(f"   Capital: R{self.state.portfolio_state['capital_available']:,.2f}")
        report.append(f"   Positions: {len(self.state.portfolio_state['positions'])}")
        report.append(f"   Trades: {self.state.portfolio_state['trades']['buy']} BUY, " +
                     f"{self.state.portfolio_state['trades']['sell']} SELL, " +
                     f"{self.state.portfolio_state['trades']['skip']} SKIP\n")
        
        # INFRASTRUCTURE
        report.append("🏗️  INFRASTRUCTURE")
        report.append("-" * 70)
        report.append(f"   Master Control: {'✅' if self.state.code_state['master_control'] else '❌'}")
        report.append(f"   Planner: {'✅' if self.state.code_state['planner'] else '❌'}")
        report.append(f"   Monitoring: {'✅' if self.state.code_state['monitoring'] else '❌'}")
        report.append(f"   Core Agent: {'✅' if self.state.code_state['core_agent'] else '❌'}")
        report.append(f"   SOPs: {len(self.state.code_state['sops'])} documents\n")
        
        # HEALTH
        report.append("🏥 SYSTEM HEALTH")
        report.append("-" * 70)
        report.append(f"   Status: {self.state.health_state['status']}")
        
        if self.state.health_state['issues']:
            report.append("   Issues:")
            for issue in self.state.health_state['issues']:
                report.append(f"      ❌ {issue}")
        
        if self.state.health_state['warnings']:
            report.append("   Warnings:")
            for warning in self.state.health_state['warnings']:
                report.append(f"      ⚠️  {warning}")
        
        if not self.state.health_state['issues'] and not self.state.health_state['warnings']:
            report.append("   ✅ All systems operational")
        
        report.append("\n" + "=" * 70)
        
        return "\n".join(report)
    
    def get_next_actions(self) -> str:
        """Determine what to do next"""
        actions = []
        actions.append("=" * 70)
        actions.append("🎯 WHAT TO DO NEXT")
        actions.append("=" * 70)
        actions.append("")
        
        # Determine state and actions
        if self.state.health_state['status'] == 'CRITICAL':
            actions.append("⚠️  CRITICAL: System has issues - fix these first!")
            for issue in self.state.health_state['issues']:
                actions.append(f"   ❌ {issue}")
            actions.append("")
            actions.append("🔧 IMMEDIATE ACTION:")
            actions.append("   1. Review TROUBLESHOOTING.md")
            actions.append("   2. Check system architecture")
            actions.append("   3. Restore missing components")
        
        elif self.state.test_state["running"]:
            # Test is running - monitor it
            remaining = (self.state.test_state['decisions']['total'] - 
                        self.state.test_state['decisions']['completed'])
            
            actions.append("✅ Test is RUNNING - Continue monitoring")
            actions.append("")
            actions.append("📊 CURRENT STATUS:")
            actions.append(f"   Progress: {self.state.test_state['progress']:.1f}%")
            actions.append(f"   Remaining: {remaining} decisions")
            actions.append(f"   Runtime: {self.state.test_state['runtime_minutes']} minutes")
            actions.append("")
            actions.append("🎬 IMMEDIATE ACTIONS:")
            actions.append("   1. Monitor with: ./ozzy.py status")
            actions.append("   2. Check every hour for issues")
            actions.append("   3. Watch for completion")
            actions.append("")
            actions.append("🎉 WHEN TEST COMPLETES:")
            actions.append("   1. Review results")
            actions.append("   2. Validate success criteria")
            actions.append("   3. python3 MASTER_PLANNER.py complete 1.2")
            actions.append("   4. Start next milestone")
        
        elif self.state.planner_state['milestones_complete'] == 2:
            # Milestones 1.1 and 1.1.5 done, 1.2 not started
            actions.append("🚀 READY TO START: Milestone 1.2 - Stability Test")
            actions.append("")
            actions.append("📋 WHAT THIS IS:")
            actions.append("   Run 24-decision stability test (6 hours)")
            actions.append("   Validate system runs without crashes")
            actions.append("   Collect signal distribution data")
            actions.append("")
            actions.append("🎬 HOW TO START:")
            actions.append("   1. cd ~/ozzy-simple/scripts")
            actions.append("   2. python bulletproof_test.py --duration 21600 --interval 900 --capital 10000")
            actions.append("   3. Monitor with: ./ozzy.py status")
            actions.append("")
            actions.append("📖 REFERENCE:")
            actions.append("   SOP-002-Testing-Protocol.md")
        
        else:
            # Generic - check planner
            actions.append("📋 CHECK THE PLAN")
            actions.append("")
            actions.append("🎬 IMMEDIATE ACTIONS:")
            actions.append("   1. python3 MASTER_PLANNER.py status")
            actions.append("   2. python3 MASTER_PLANNER.py next")
            actions.append("   3. Review current milestone tasks")
        
        actions.append("")
        actions.append("=" * 70)
        
        return "\n".join(actions)
    
    def get_resume_guide(self) -> str:
        """Guide for resuming after long break (even 5 years!)"""
        guide = []
        guide.append("=" * 70)
        guide.append("🔄 RESUME FROM ANY POINT - EVEN AFTER 5 YEARS!")
        guide.append("=" * 70)
        guide.append("")
        guide.append("👋 WELCOME BACK!")
        guide.append("")
        guide.append("You're building a trading bot to make R5k-10k/week")
        guide.append("and QUIT YOUR 9-TO-5. Let's remember where we are...")
        guide.append("")
        
        # Quick context
        guide.append("📍 QUICK CONTEXT:")
        guide.append("-" * 70)
        guide.append(f"   Days Since Start: {self.state.planner_state['days_active']}")
        guide.append(f"   Progress: {self.state.planner_state['milestones_complete']}/{self.state.planner_state['milestones_total']} milestones")
        guide.append(f"   Current Phase: {self.state.planner_state['phase']}")
        guide.append("")
        
        # What we built
        guide.append("🏗️  WHAT YOU BUILT:")
        guide.append("-" * 70)
        
        if self.state.code_state['master_control']:
            guide.append("   ✅ Master Control Script (ozzy.py) - ONE command for everything")
        if self.state.code_state['planner']:
            guide.append("   ✅ Master Planner - Your project manager")
        if self.state.code_state['core_agent']:
            guide.append("   ✅ Core Trading Agent - The brain")
        if self.state.code_state['monitoring']:
            guide.append("   ✅ Monitoring Dashboard - Real-time visibility")
        if self.state.code_state['sops']:
            guide.append(f"   ✅ {len(self.state.code_state['sops'])} SOPs - Your procedures")
        
        guide.append("")
        
        # Where you left off
        guide.append("🎯 WHERE YOU LEFT OFF:")
        guide.append("-" * 70)
        
        if self.state.test_state["running"]:
            guide.append("   ⚠️  You had a test RUNNING!")
            guide.append(f"   Progress: {self.state.test_state['progress']:.1f}%")
            guide.append(f"   It might still be running or crashed.")
            guide.append("")
            guide.append("   Check with: ./ozzy.py status")
        else:
            guide.append("   No active test running")
            guide.append(f"   Last milestone: {self.state.planner_state['milestones_complete']} completed")
            guide.append("")
        
        guide.append("")
        
        # How to resume
        guide.append("🚀 HOW TO RESUME:")
        guide.append("-" * 70)
        guide.append("   STEP 1: Check status")
        guide.append("      ./ozzy.py status")
        guide.append("")
        guide.append("   STEP 2: Review the plan")
        guide.append("      python3 MASTER_PLANNER.py status")
        guide.append("")
        guide.append("   STEP 3: See what's next")
        guide.append("      python3 SYSTEM_CONTEXT.py --next")
        guide.append("")
        guide.append("   STEP 4: Read the SOP for current milestone")
        guide.append("      ls docs/sops/")
        guide.append("")
        guide.append("   STEP 5: Execute next action")
        guide.append("      (Based on what --next told you)")
        guide.append("")
        
        # Documentation
        guide.append("📚 KEY DOCUMENTATION:")
        guide.append("-" * 70)
        guide.append("   START HERE:")
        guide.append("      - MASTER_PLANNER.py - The Law (your project manager)")
        guide.append("      - OZZY-CONTROL-GUIDE.md - How to use ozzy.py")
        guide.append("")
        guide.append("   PROCEDURES:")
        for sop in self.state.code_state['sops']:
            guide.append(f"      - docs/sops/{sop}")
        guide.append("")
        guide.append("   ARCHITECTURE:")
        guide.append("      - ARCHITECTURE.md - System design")
        guide.append("      - TROUBLESHOOTING.md - Fix common issues")
        guide.append("")
        
        guide.append("=" * 70)
        guide.append("")
        guide.append("💪 YOU GOT THIS!")
        guide.append("")
        guide.append("The system is designed to be self-explanatory.")
        guide.append("Just run the commands above and you'll be back on track.")
        guide.append("")
        guide.append("Remember: The goal is R5k/week → QUIT THE 9-TO-5!")
        guide.append("")
        guide.append("=" * 70)
        
        return "\n".join(guide)
    
    def get_progress_to_goal(self) -> str:
        """Show progress toward ultimate goal"""
        progress = []
        progress.append("=" * 70)
        progress.append("📈 PROGRESS TO QUITTING YOUR 9-TO-5")
        progress.append("=" * 70)
        progress.append("")
        
        # Phase 1 progress
        phase1_pct = (self.state.planner_state['milestones_complete'] / 
                     self.state.planner_state['milestones_total']) * 100
        
        progress.append("🎯 PHASE 1: FOUNDATION")
        progress.append("-" * 70)
        progress.append(f"   Goal: Get profitable (R5k/week)")
        progress.append(f"   Progress: {self.state.planner_state['milestones_complete']}/{self.state.planner_state['milestones_total']} milestones ({phase1_pct:.0f}%)")
        progress.append(f"   Days Active: {self.state.planner_state['days_active']}/30")
        progress.append("")
        
        # Visual progress bar
        bar_length = 50
        filled = int((phase1_pct / 100) * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        progress.append(f"   [{bar}] {phase1_pct:.0f}%")
        progress.append("")
        
        # Milestones breakdown
        progress.append("   MILESTONES:")
        milestones = [
            ("1.1", "Fix 0% Confidence", True),
            ("1.1.5", "Development Infrastructure", True),
            ("1.2", "24-Hour Stability Test", self.state.test_state["running"]),
            ("1.3", "Paper Trading Week", False),
            ("1.4", "Performance Analysis", False),
            ("1.5", "Go Live - First Trade", False),
            ("1.6", "First Profitable Week", False),
            ("1.7", "Scale to R10k", False),
            ("1.8", "Hit R5k/Week Target", False)
        ]
        
        for id, name, status in milestones:
            if status is True:
                icon = "✅"
            elif status is False:
                icon = "⏸️ "
            else:
                icon = "⏳"
            progress.append(f"      {icon} {id}: {name}")
        
        progress.append("")
        
        # What's left
        remaining = 9 - self.state.planner_state['milestones_complete']
        progress.append(f"🎯 WHAT'S LEFT: {remaining} milestones to profitability")
        progress.append("")
        
        # Estimate to goal
        if self.state.planner_state['days_active'] > 0 and self.state.planner_state['milestones_complete'] > 0:
            days_per_milestone = self.state.planner_state['days_active'] / self.state.planner_state['milestones_complete']
            estimated_days = remaining * days_per_milestone
            progress.append(f"📅 ESTIMATED: ~{estimated_days:.0f} days to R5k/week")
            progress.append(f"   (Based on current pace: {days_per_milestone:.1f} days/milestone)")
        else:
            progress.append("📅 ESTIMATED: Complete within 30 days (on track!)")
        
        progress.append("")
        progress.append("=" * 70)
        progress.append("")
        progress.append("💰 REMEMBER:")
        progress.append("   Each milestone = closer to R5k/week")
        progress.append("   R5k/week = FREEDOM from the 9-to-5")
        progress.append("   Stay focused. Stay disciplined. Stay profitable.")
        progress.append("")
        progress.append("=" * 70)
        
        return "\n".join(progress)

# ============================================================================
# MAIN CLI
# ============================================================================

def main():
    """Main CLI interface"""
    
    # Detect current state
    print("🧠 Analyzing system state...")
    state = SystemState()
    engine = ContextEngine(state)
    
    # Parse command
    if len(sys.argv) < 2:
        # Default: Full context report
        print("\n" + engine.get_context_report())
        print("\n💡 TIP: Run with --next to see what to do next")
        print("        Run with --resume to resume after a break")
        print("        Run with --health for system health check")
        print("        Run with --progress for progress to goal\n")
        return
    
    command = sys.argv[1].lower()
    
    if command == "--next" or command == "next":
        print("\n" + engine.get_next_actions())
    
    elif command == "--resume" or command == "resume":
        print("\n" + engine.get_resume_guide())
    
    elif command == "--health" or command == "health":
        print("\n" + engine.get_context_report())
        print("\n🏥 HEALTH CHECK COMPLETE\n")
    
    elif command == "--progress" or command == "progress":
        print("\n" + engine.get_progress_to_goal())
    
    elif command == "--help" or command == "help":
        print(__doc__)
    
    else:
        print(f"❌ Unknown command: {command}")
        print("\nAvailable commands:")
        print("  python3 SYSTEM_CONTEXT.py           # Full context report")
        print("  python3 SYSTEM_CONTEXT.py --next    # What to do next")
        print("  python3 SYSTEM_CONTEXT.py --resume  # Resume after break")
        print("  python3 SYSTEM_CONTEXT.py --health  # System health check")
        print("  python3 SYSTEM_CONTEXT.py --progress # Progress to goal")
        print("  python3 SYSTEM_CONTEXT.py --help    # Show help")

if __name__ == "__main__":
    main()
