#!/usr/bin/env python3
"""
🎯 OZZY MASTER PROJECT PLANNER - THE LAW

This file is THE SOURCE OF TRUTH for the entire OZZY project.
- Run it to see where you are
- Run it to see what's next
- Run it to prevent scope creep
- Run it before ANY new feature work

USAGE:
    python3 MASTER_PLANNER.py status    # See current status
    python3 MASTER_PLANNER.py next      # See next actions
    python3 MASTER_PLANNER.py complete <milestone_id>  # Mark milestone complete
    python3 MASTER_PLANNER.py reset     # Start over (WARNING!)

THE RULE: If it's not in this file, DON'T BUILD IT.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# ============================================================================
# PROJECT CONFIGURATION
# ============================================================================

PROJECT_NAME = "OZZY Trading Bot"
PROJECT_GOAL = "R5,000-10,000/week profitable automated crypto trading"
CURRENT_CAPITAL = 10000  # Update this as you scale
TARGET_WEEKLY_PROFIT = 5000  # R5k/week minimum

# File locations
PLANNER_DATA_FILE = Path(__file__).parent / "planner_data.json"
SOP_DIRECTORY = Path(__file__).parent / "docs" / "sops"

# ============================================================================
# THE MASTER PLAN - THIS IS THE LAW
# ============================================================================

MASTER_PLAN = {
    "phase_1": {
        "name": "FOUNDATION - Get Profitable FAST",
        "goal": "Simple bot making R5k/week",
        "duration": "30 days",
        "budget": "R0 (free tools only)",
        "success_criteria": [
            "System runs 24/7 without crashes",
            "Win rate >50%",
            "Weekly profit >R5,000",
            "Drawdown <15%"
        ],
        "milestones": {
            "1.1": {
                "name": "Fix 0% Confidence Bug",
                "priority": "CRITICAL",
                "estimated_time": "2-3 days",
                "tasks": [
                    "Implement inject_fresh_market_data()",
                    "Update trader.py with _market_cache",
                    "Test with 3 decisions (quick test)",
                    "Verify confidence >40%",
                    "Document the fix"
                ],
                "sop_reference": "SOP-001-Data-Injection.md",
                "blocking": True,  # Nothing else can proceed until this is done
                "completed": False,
                "completed_date": None
            },
            "1.2": {
                "name": "24-Hour Stability Test",
                "priority": "HIGH",
                "estimated_time": "1 day",
                "tasks": [
                    "Run bulletproof_test.py for 24 decisions",
                    "Monitor for crashes/errors",
                    "Verify signal distribution (LONG/SHORT/SKIP)",
                    "Check confidence ranges",
                    "Generate test report"
                ],
                "sop_reference": "SOP-002-Testing-Protocol.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["1.1"]
            },
            "1.3": {
                "name": "Paper Trading Week",
                "priority": "HIGH",
                "estimated_time": "7 days",
                "tasks": [
                    "Run bot 24/7 for 7 days",
                    "Collect 50+ trading decisions",
                    "Track hypothetical P&L",
                    "Calculate win rate",
                    "Identify any issues"
                ],
                "sop_reference": "SOP-003-Paper-Trading.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["1.2"]
            },
            "1.4": {
                "name": "Performance Analysis",
                "priority": "MEDIUM",
                "estimated_time": "4 hours",
                "tasks": [
                    "Analyze 7-day results",
                    "Calculate metrics (Sharpe, win rate, etc)",
                    "Identify best/worst performing setups",
                    "Document findings",
                    "Make go/no-go decision for live trading"
                ],
                "sop_reference": "SOP-004-Performance-Analysis.md",
                "blocking": True,
                "completed": False,
                "completed_date": None,
                "depends_on": ["1.3"]
            },
            "1.5": {
                "name": "Go Live - First Trade",
                "priority": "CRITICAL",
                "estimated_time": "1 day",
                "tasks": [
                    "Deposit R5,000 to Bybit",
                    "Verify API keys (live, not testnet)",
                    "Set PAPER_TRADING = False",
                    "Execute first live trade",
                    "Monitor closely",
                    "Document experience"
                ],
                "sop_reference": "SOP-005-Live-Trading-Checklist.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["1.4"]
            },
            "1.6": {
                "name": "First Profitable Week",
                "priority": "HIGH",
                "estimated_time": "7 days",
                "tasks": [
                    "Run live for full 7 days",
                    "Complete minimum 10 trades",
                    "Track actual P&L",
                    "Verify risk management working",
                    "Achieve net positive profit"
                ],
                "sop_reference": "SOP-006-Live-Monitoring.md",
                "blocking": True,
                "completed": False,
                "completed_date": None,
                "depends_on": ["1.5"]
            },
            "1.7": {
                "name": "Scale to R10k",
                "priority": "MEDIUM",
                "estimated_time": "1 day",
                "tasks": [
                    "Add R5,000 more capital",
                    "Update STARTING_CAPITAL config",
                    "Verify position sizing adjusts",
                    "Monitor first few trades",
                    "Document capital scaling procedure"
                ],
                "sop_reference": "SOP-007-Capital-Scaling.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["1.6"]
            },
            "1.8": {
                "name": "Hit R5k/Week Target",
                "priority": "HIGH",
                "estimated_time": "7-14 days",
                "tasks": [
                    "Run at R10k capital for 2 weeks",
                    "Achieve R5,000+ profit in one week",
                    "Maintain <10% drawdown",
                    "Document profitable strategies",
                    "Phase 1 COMPLETE celebration! 🎉"
                ],
                "sop_reference": "SOP-008-Profit-Targets.md",
                "blocking": True,
                "completed": False,
                "completed_date": None,
                "depends_on": ["1.7"]
            }
        }
    },
    
    "phase_2": {
        "name": "INTELLIGENCE - Add AI Insights",
        "goal": "10-15% performance boost with AI",
        "duration": "30 days",
        "budget": "R0 (Kimi AI free tier)",
        "success_criteria": [
            "Kimi integration working",
            "Daily AI summaries generated",
            "Strategy optimization suggestions",
            "Win rate improves 5-10%"
        ],
        "depends_on_phase": "phase_1",
        "milestones": {
            "2.1": {
                "name": "Kimi AI Integration",
                "priority": "MEDIUM",
                "estimated_time": "1 day",
                "tasks": [
                    "Get Kimi API key (free)",
                    "Implement kimi_integration.py",
                    "Test basic queries",
                    "Add to project structure",
                    "Document API usage"
                ],
                "sop_reference": "SOP-009-Kimi-Integration.md",
                "blocking": False,
                "completed": False,
                "completed_date": None
            },
            "2.2": {
                "name": "Daily AI Summaries",
                "priority": "LOW",
                "estimated_time": "2 hours",
                "tasks": [
                    "Add end_of_day_summary() function",
                    "Generate AI performance analysis",
                    "Send to Telegram/email",
                    "Review and iterate",
                    "Make it daily automatic"
                ],
                "sop_reference": "SOP-010-AI-Summaries.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["2.1"]
            },
            "2.3": {
                "name": "News Sentiment Analysis",
                "priority": "MEDIUM",
                "estimated_time": "1 day",
                "tasks": [
                    "Integrate news API",
                    "Get Kimi to analyze sentiment",
                    "Filter trades based on major news",
                    "Test during high-impact events",
                    "Document news handling"
                ],
                "sop_reference": "SOP-011-News-Sentiment.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["2.1"]
            },
            "2.4": {
                "name": "Strategy Optimization",
                "priority": "MEDIUM",
                "estimated_time": "1 week",
                "tasks": [
                    "AI analyzes 30-day performance",
                    "Suggests parameter improvements",
                    "Test suggestions in paper trading",
                    "Implement proven optimizations",
                    "Document improvements"
                ],
                "sop_reference": "SOP-012-Strategy-Optimization.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["2.2"]
            },
            "2.5": {
                "name": "Performance Boost Validation",
                "priority": "HIGH",
                "estimated_time": "2 weeks",
                "tasks": [
                    "Run with AI enhancements for 2 weeks",
                    "Compare to baseline (Phase 1)",
                    "Measure win rate improvement",
                    "Calculate ROI of AI integration",
                    "Phase 2 COMPLETE if 5%+ boost!"
                ],
                "sop_reference": "SOP-013-AI-Performance-Validation.md",
                "blocking": True,
                "completed": False,
                "completed_date": None,
                "depends_on": ["2.4"]
            }
        }
    },
    
    "phase_3": {
        "name": "AGENT COUNCIL - Multi-Agent System",
        "goal": "20-30% performance with agent coordination",
        "duration": "90 days",
        "budget": "R0-1000/month (optional premium AI)",
        "success_criteria": [
            "All 4 agents operational",
            "Jarvis orchestration working",
            "Win rate >65%",
            "Weekly profit >R10,000"
        ],
        "depends_on_phase": "phase_2",
        "milestones": {
            "3.1": {
                "name": "Data Collection for Training",
                "priority": "HIGH",
                "estimated_time": "30 days",
                "tasks": [
                    "Collect 200+ real trades",
                    "Store all technical indicators",
                    "Track market conditions",
                    "Label outcomes (win/loss)",
                    "Prepare training dataset"
                ],
                "sop_reference": "SOP-014-ML-Data-Collection.md",
                "blocking": True,
                "completed": False,
                "completed_date": None
            },
            "3.2": {
                "name": "Build Recon Agent",
                "priority": "HIGH",
                "estimated_time": "2 weeks",
                "tasks": [
                    "Design Recon Agent architecture",
                    "Implement pattern recognition",
                    "Train on historical data",
                    "Test signal quality",
                    "Deploy and monitor"
                ],
                "sop_reference": "SOP-015-Recon-Agent.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["3.1"]
            },
            "3.3": {
                "name": "Build Risk Agent",
                "priority": "HIGH",
                "estimated_time": "2 weeks",
                "tasks": [
                    "Design Risk Agent architecture",
                    "Implement risk scoring",
                    "Train on P&L data",
                    "Test risk predictions",
                    "Deploy and monitor"
                ],
                "sop_reference": "SOP-016-Risk-Agent.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["3.1"]
            },
            "3.4": {
                "name": "Build Execution Agent",
                "priority": "MEDIUM",
                "estimated_time": "2 weeks",
                "tasks": [
                    "Design Execution Agent architecture",
                    "Implement timing optimization",
                    "Train on execution quality",
                    "Test slippage reduction",
                    "Deploy and monitor"
                ],
                "sop_reference": "SOP-017-Execution-Agent.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["3.1"]
            },
            "3.5": {
                "name": "Build Learning Agent",
                "priority": "MEDIUM",
                "estimated_time": "2 weeks",
                "tasks": [
                    "Design Learning Agent architecture",
                    "Implement pattern memory",
                    "Train on all past trades",
                    "Test pattern matching",
                    "Deploy and monitor"
                ],
                "sop_reference": "SOP-018-Learning-Agent.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["3.1"]
            },
            "3.6": {
                "name": "Build Jarvis Orchestrator",
                "priority": "HIGH",
                "estimated_time": "1 week",
                "tasks": [
                    "Design Jarvis architecture",
                    "Implement weighted voting",
                    "Add veto logic",
                    "Test agent coordination",
                    "Deploy full council"
                ],
                "sop_reference": "SOP-019-Jarvis-Orchestrator.md",
                "blocking": True,
                "completed": False,
                "completed_date": None,
                "depends_on": ["3.2", "3.3", "3.4", "3.5"]
            },
            "3.7": {
                "name": "Council Performance Testing",
                "priority": "HIGH",
                "estimated_time": "2 weeks",
                "tasks": [
                    "Paper trade with full council",
                    "Compare to baseline",
                    "Measure performance improvement",
                    "Tune agent weights",
                    "Document results"
                ],
                "sop_reference": "SOP-020-Council-Testing.md",
                "blocking": False,
                "completed": False,
                "completed_date": None,
                "depends_on": ["3.6"]
            },
            "3.8": {
                "name": "Go Live with Agent Council",
                "priority": "CRITICAL",
                "estimated_time": "1 month",
                "tasks": [
                    "Deploy council to live trading",
                    "Monitor for 30 days",
                    "Verify >65% win rate",
                    "Achieve R10k+/week",
                    "Phase 3 COMPLETE - CELEBRATE! 🚀"
                ],
                "sop_reference": "SOP-021-Council-Live.md",
                "blocking": True,
                "completed": False,
                "completed_date": None,
                "depends_on": ["3.7"]
            }
        }
    },
    
    "phase_4": {
        "name": "SCALING - Multi-Strategy, Multi-Asset",
        "goal": "R20-50k/week with diversification",
        "duration": "60 days",
        "budget": "R5000/month (infrastructure)",
        "success_criteria": [
            "10+ assets traded",
            "3+ strategies running",
            "Weekly profit >R20,000",
            "Sharpe ratio >2.0"
        ],
        "depends_on_phase": "phase_3",
        "milestones": {
            "4.1": {
                "name": "Add More Assets",
                "priority": "MEDIUM",
                "estimated_time": "2 weeks",
                "tasks": [
                    "Add ETH, BNB, SOL, XRP",
                    "Test each asset separately",
                    "Optimize parameters per asset",
                    "Deploy all assets",
                    "Monitor correlation"
                ],
                "sop_reference": "SOP-022-Multi-Asset.md",
                "blocking": False,
                "completed": False,
                "completed_date": None
            },
            "4.2": {
                "name": "Multiple Strategies",
                "priority": "HIGH",
                "estimated_time": "3 weeks",
                "tasks": [
                    "Implement mean reversion strategy",
                    "Implement breakout strategy",
                    "Implement scalping strategy",
                    "Test each independently",
                    "Deploy portfolio of strategies"
                ],
                "sop_reference": "SOP-023-Multi-Strategy.md",
                "blocking": False,
                "completed": False,
                "completed_date": None
            },
            "4.3": {
                "name": "Infrastructure Scaling",
                "priority": "HIGH",
                "estimated_time": "1 week",
                "tasks": [
                    "Deploy to VPS (AWS/DigitalOcean)",
                    "Set up monitoring (Grafana)",
                    "Configure alerts",
                    "Add redundancy",
                    "Document deployment"
                ],
                "sop_reference": "SOP-024-Infrastructure.md",
                "blocking": False,
                "completed": False,
                "completed_date": None
            },
            "4.4": {
                "name": "Capital Scaling",
                "priority": "HIGH",
                "estimated_time": "Ongoing",
                "tasks": [
                    "Scale to R50k capital",
                    "Scale to R100k capital",
                    "Scale to R250k capital",
                    "Each step: 2 weeks monitoring",
                    "Phase 4 COMPLETE at R50k/week!"
                ],
                "sop_reference": "SOP-025-Capital-Scaling.md",
                "blocking": True,
                "completed": False,
                "completed_date": None,
                "depends_on": ["4.1", "4.2", "4.3"]
            }
        }
    }
}

# ============================================================================
# ANTI-SCOPE-CREEP RULES
# ============================================================================

FORBIDDEN_UNTIL_PHASE_COMPLETE = {
    "phase_1": [
        "❌ NO machine learning",
        "❌ NO agent council",
        "❌ NO additional assets beyond BTC/ETH",
        "❌ NO complex strategies",
        "❌ NO infrastructure work",
        "❌ NO optimization before profitability",
        "❌ NO 'nice to have' features"
    ],
    "phase_2": [
        "❌ NO agent council (not yet!)",
        "❌ NO multiple strategies",
        "❌ NO infrastructure scaling",
        "❌ NO capital scaling beyond R10k"
    ],
    "phase_3": [
        "❌ NO multi-exchange trading",
        "❌ NO options/futures (stick to spot)",
        "❌ NO capital >R50k until council proven"
    ],
    "phase_4": [
        "❌ NO exotic assets",
        "❌ NO leverage >2x",
        "❌ NO experimental strategies"
    ]
}

# ============================================================================
# PLANNER FUNCTIONS
# ============================================================================

def load_planner_data():
    """Load current progress from file"""
    if PLANNER_DATA_FILE.exists():
        with open(PLANNER_DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        "current_phase": "phase_1",
        "start_date": datetime.now().isoformat(),
        "last_updated": datetime.now().isoformat(),
        "milestones_completed": [],
        "notes": []
    }

def save_planner_data(data):
    """Save progress to file"""
    data["last_updated"] = datetime.now().isoformat()
    with open(PLANNER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"✅ Progress saved to {PLANNER_DATA_FILE}")

def get_current_phase():
    """Get current phase from saved data"""
    data = load_planner_data()
    return data["current_phase"]

def get_phase_info(phase_id):
    """Get phase information"""
    return MASTER_PLAN.get(phase_id, {})

def get_milestone_info(phase_id, milestone_id):
    """Get milestone information"""
    phase = MASTER_PLAN.get(phase_id, {})
    return phase.get("milestones", {}).get(milestone_id, {})

def check_dependencies_met(phase_id, milestone_id):
    """Check if milestone dependencies are met"""
    data = load_planner_data()
    milestone = get_milestone_info(phase_id, milestone_id)
    
    if "depends_on" not in milestone:
        return True, []
    
    depends_on = milestone["depends_on"]
    completed = data.get("milestones_completed", [])
    
    missing = []
    for dep_id in depends_on:
        full_dep_id = f"{phase_id}.{dep_id}"
        if full_dep_id not in completed:
            missing.append(dep_id)
    
    return len(missing) == 0, missing

def show_status():
    """Show current project status"""
    data = load_planner_data()
    current_phase_id = data["current_phase"]
    phase = get_phase_info(current_phase_id)
    
    print("\n" + "="*70)
    print(f"🎯 OZZY PROJECT STATUS")
    print("="*70)
    
    # Project info
    print(f"\n📊 Project: {PROJECT_NAME}")
    print(f"🎯 Goal: {PROJECT_GOAL}")
    print(f"💰 Current Capital: R{CURRENT_CAPITAL:,}")
    print(f"📅 Started: {data['start_date'][:10]}")
    
    days_active = (datetime.now() - datetime.fromisoformat(data['start_date'])).days
    print(f"⏱️  Days Active: {days_active}")
    
    # Current phase
    print(f"\n{'='*70}")
    print(f"📍 CURRENT PHASE: {phase['name']}")
    print(f"{'='*70}")
    print(f"🎯 Goal: {phase['goal']}")
    print(f"⏱️  Duration: {phase['duration']}")
    print(f"💵 Budget: {phase['budget']}")
    
    # Success criteria
    print(f"\n✅ Success Criteria:")
    for i, criterion in enumerate(phase['success_criteria'], 1):
        print(f"   {i}. {criterion}")
    
    # Milestones
    print(f"\n{'='*70}")
    print(f"📋 MILESTONES:")
    print(f"{'='*70}")
    
    completed_milestones = [m for m in data.get("milestones_completed", []) 
                           if m.startswith(current_phase_id)]
    total_milestones = len(phase['milestones'])
    progress = (len(completed_milestones) / total_milestones * 100) if total_milestones > 0 else 0
    
    print(f"\nProgress: {len(completed_milestones)}/{total_milestones} ({progress:.0f}%)")
    print(f"{'█' * int(progress/2)}{' ' * (50-int(progress/2))} {progress:.0f}%\n")
    
    for milestone_id, milestone in phase['milestones'].items():
        full_id = f"{current_phase_id}.{milestone_id}"
        is_completed = full_id in data.get("milestones_completed", [])
        
        status = "✅" if is_completed else "⏳"
        priority_emoji = {"CRITICAL": "🔥", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
        priority_icon = priority_emoji.get(milestone['priority'], "⚪")
        
        print(f"{status} {priority_icon} {milestone_id}: {milestone['name']}")
        print(f"   Priority: {milestone['priority']} | Est: {milestone['estimated_time']}")
        
        if is_completed:
            # Find completion date
            for note in data.get("notes", []):
                if note.get("milestone") == full_id and "completed" in note.get("text", "").lower():
                    print(f"   Completed: {note['date'][:10]}")
                    break
        else:
            # Check dependencies
            deps_met, missing = check_dependencies_met(current_phase_id, milestone_id)
            if not deps_met:
                print(f"   ⚠️  Blocked by: {', '.join(missing)}")
        
        if milestone.get('blocking'):
            print(f"   🚫 BLOCKING - Must complete before next milestones")
        
        print()
    
    # Anti-scope-creep rules
    print(f"{'='*70}")
    print(f"🚫 FORBIDDEN IN THIS PHASE:")
    print(f"{'='*70}")
    for rule in FORBIDDEN_UNTIL_PHASE_COMPLETE.get(current_phase_id, []):
        print(f"   {rule}")
    
    print(f"\n{'='*70}\n")

def show_next_actions():
    """Show what should be done next"""
    data = load_planner_data()
    current_phase_id = data["current_phase"]
    phase = get_phase_info(current_phase_id)
    
    print("\n" + "="*70)
    print(f"🎯 NEXT ACTIONS")
    print("="*70)
    
    # Find next incomplete milestone
    completed = data.get("milestones_completed", [])
    
    next_milestones = []
    for milestone_id, milestone in phase['milestones'].items():
        full_id = f"{current_phase_id}.{milestone_id}"
        
        if full_id not in completed:
            # Check if dependencies are met
            deps_met, missing = check_dependencies_met(current_phase_id, milestone_id)
            
            if deps_met:
                next_milestones.append((milestone_id, milestone))
    
    if not next_milestones:
        print("\n🎉 ALL MILESTONES IN THIS PHASE COMPLETE!")
        print(f"\n👉 Ready to move to next phase!")
        print(f"   Run: python3 MASTER_PLANNER.py advance_phase")
        return
    
    # Sort by priority
    priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    next_milestones.sort(key=lambda x: priority_order.get(x[1]['priority'], 4))
    
    # Show top 3 next actions
    print(f"\n📍 YOU SHOULD BE WORKING ON:\n")
    
    for i, (milestone_id, milestone) in enumerate(next_milestones[:3], 1):
        priority_emoji = {"CRITICAL": "🔥", "HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
        icon = priority_emoji.get(milestone['priority'], "⚪")
        
        print(f"{i}. {icon} {milestone['name']}")
        print(f"   ID: {current_phase_id}.{milestone_id}")
        print(f"   Priority: {milestone['priority']}")
        print(f"   Estimated Time: {milestone['estimated_time']}")
        print(f"   SOP: {milestone.get('sop_reference', 'None')}")
        
        print(f"\n   Tasks:")
        for j, task in enumerate(milestone['tasks'], 1):
            print(f"      {j}. {task}")
        
        print()
    
    # Show what NOT to work on
    print(f"{'='*70}")
    print(f"🚫 DO NOT WORK ON (Scope Creep Prevention):")
    print(f"{'='*70}")
    
    future_milestones = [m for m_id, m in phase['milestones'].items() 
                        if f"{current_phase_id}.{m_id}" not in completed 
                        and (m_id, m) not in next_milestones]
    
    if future_milestones:
        print("\nThese are future milestones - don't start them yet:")
        for milestone_id, milestone in phase['milestones'].items():
            full_id = f"{current_phase_id}.{milestone_id}"
            if full_id not in completed:
                deps_met, missing = check_dependencies_met(current_phase_id, milestone_id)
                if not deps_met:
                    print(f"   ❌ {milestone['name']} (blocked by: {', '.join(missing)})")
    
    print()

def complete_milestone(milestone_id):
    """Mark a milestone as complete"""
    data = load_planner_data()
    current_phase_id = data["current_phase"]
    full_id = f"{current_phase_id}.{milestone_id}"
    
    # Check if milestone exists
    milestone = get_milestone_info(current_phase_id, milestone_id)
    if not milestone:
        print(f"❌ Milestone {milestone_id} not found in {current_phase_id}")
        return
    
    # Check if already completed
    if full_id in data.get("milestones_completed", []):
        print(f"✅ Milestone {milestone_id} already marked complete!")
        return
    
    # Check dependencies
    deps_met, missing = check_dependencies_met(current_phase_id, milestone_id)
    if not deps_met:
        print(f"⚠️  Cannot complete {milestone_id} - missing dependencies:")
        for dep in missing:
            print(f"   ❌ {dep}")
        print(f"\nComplete these first, then try again.")
        return
    
    # Mark complete
    if "milestones_completed" not in data:
        data["milestones_completed"] = []
    data["milestones_completed"].append(full_id)
    
    # Add note
    if "notes" not in data:
        data["notes"] = []
    data["notes"].append({
        "date": datetime.now().isoformat(),
        "milestone": full_id,
        "text": f"Completed: {milestone['name']}"
    })
    
    save_planner_data(data)
    
    print(f"\n🎉 MILESTONE COMPLETED: {milestone['name']}")
    print(f"   Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Check if phase is complete
    phase = get_phase_info(current_phase_id)
    phase_milestones = [f"{current_phase_id}.{m_id}" for m_id in phase['milestones'].keys()]
    completed_in_phase = [m for m in data["milestones_completed"] if m in phase_milestones]
    
    if len(completed_in_phase) == len(phase_milestones):
        print(f"\n{'='*70}")
        print(f"🏆 PHASE COMPLETE: {phase['name']}")
        print(f"{'='*70}")
        print(f"\n🎉 Congratulations! You've completed {phase['name']}!")
        print(f"\n👉 Run: python3 MASTER_PLANNER.py advance_phase")
    else:
        print(f"\n👉 Next: python3 MASTER_PLANNER.py next")

def main():
    """Main CLI interface"""
    import sys
    
    if len(sys.argv) < 2:
        print("\n🎯 OZZY MASTER PLANNER")
        print("\nUsage:")
        print("  python3 MASTER_PLANNER.py status           # Show current status")
        print("  python3 MASTER_PLANNER.py next             # Show next actions")
        print("  python3 MASTER_PLANNER.py complete <ID>    # Mark milestone complete")
        print("  python3 MASTER_PLANNER.py help             # Show this help")
        print()
        return
    
    command = sys.argv[1].lower()
    
    if command == "status":
        show_status()
    elif command == "next":
        show_next_actions()
    elif command == "complete":
        if len(sys.argv) < 3:
            print("❌ Error: Provide milestone ID")
            print("   Example: python3 MASTER_PLANNER.py complete 1.1")
            return
        milestone_id = sys.argv[2]
        complete_milestone(milestone_id)
    elif command == "help":
        print(__doc__)
    else:
        print(f"❌ Unknown command: {command}")
        print("   Run: python3 MASTER_PLANNER.py help")

if __name__ == "__main__":
    main()
