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
# DISCIPLINE & MOTIVATION SYSTEM
# ============================================================================

import random

MOTIVATIONAL_QUOTES = [
    "🔥 Focus wins. Distractions lose.",
    "💪 Every billionaire started with discipline.",
    "🎯 Your future self will thank you for staying on track.",
    "⚡ Speed beats perfection. Ship it!",
    "🚀 The plan works if you work the plan.",
    "💰 Profitable traders follow systems, not feelings.",
    "🧠 Complexity is the enemy of execution.",
    "⏰ Time spent planning prevents wasted development.",
    "🎖️ Discipline = Freedom. Stay on track.",
    "🔨 Build what makes money, not what's cool."
]

SCOPE_CREEP_WARNINGS = {
    "agent": {
        "keywords": ["agent", "council", "jarvis", "recon", "sniper", "neural"],
        "message": """
🚫 HOLD UP! I see you're thinking about agents...

**Current Phase:** Phase 1 (Foundation)
**Agent Council:** Phase 3 (Month 3-6)

**Why you can't build it yet:**
❌ No profitable baseline to improve on
❌ Need 200+ trades for training data
❌ Will distract from getting profitable FAST

**What you SHOULD do:**
✅ Finish Phase 1 (get to R5k/week)
✅ THEN we'll build your agent council properly

**Remember:** Renaissance Technologies didn't start with 150 PhDs.
They started profitable, THEN added complexity.

Stay focused, future millionaire! 💪
"""
    },
    "ml": {
        "keywords": ["machine learning", "ml", "neural network", "deep learning", "tensorflow", "pytorch", "model training"],
        "message": """
🚫 WHOA THERE! Machine learning vibes detected...

**Current Phase:** Phase 1 (Foundation)
**ML Implementation:** Phase 5+ (Month 4+)

**Why not now:**
❌ You don't have training data yet
❌ Simple strategies often outperform ML (see docs)
❌ ML without profitability = over-engineering

**What you SHOULD do:**
✅ Get profitable with simple RSI + EMA first
✅ Collect 200+ trades
✅ THEN train ML models on proven strategies

**Real talk:** Even pro quants prefer simple models.
Complexity comes AFTER profit. Period.

Trust the process! 🎯
"""
    },
    "optimization": {
        "keywords": ["optimize", "parameter tuning", "backtest", "optimization", "hyperparameter"],
        "message": """
🚫 STOP RIGHT THERE! Optimization alert...

**Current Phase:** Phase 1 (Foundation)
**Optimization:** AFTER proving profitability

**Why this is premature:**
❌ Optimizing before proving = overfitting
❌ You haven't validated the strategy works yet
❌ Optimization without data = guessing

**What you SHOULD do:**
✅ Run with default parameters first
✅ Collect real trading data
✅ Optimize based on actual performance

**Harsh truth:** 99% of optimized backtests fail live trading.
Prove it works first, optimize later.

Keep it simple, keep it real! 💪
"""
    },
    "infrastructure": {
        "keywords": ["docker", "kubernetes", "microservices", "scalability", "distributed", "cloud"],
        "message": """
🚫 HEY! Infrastructure thinking detected...

**Current Phase:** Phase 1 (Foundation)
**Infrastructure:** Phase 4 (Month 5+)

**Why not now:**
❌ You're not handling enough volume yet
❌ Premature scaling = wasted time
❌ Can't scale what isn't profitable

**What you SHOULD do:**
✅ Run on your laptop first
✅ Prove profitability
✅ Scale when you're making R20k+/week

**Real story:** Most successful traders start on a laptop.
Infrastructure comes AFTER product-market fit (profit).

Focus on money first, scaling second! 💰
"""
    },
    "features": {
        "keywords": ["add feature", "new feature", "implement", "also need", "what if we"],
        "message": """
🚫 FEATURE ALERT! Let's pause...

**The Feature Trap:**
Every feature delays profitability.
Every delay costs money.
Every distraction compounds.

**Current Focus:** Fix 0% confidence → Get profitable

**Ask yourself:**
1. Is this in current milestone? → If NO, don't build
2. Will this make money THIS WEEK? → If NO, don't build
3. Is this critical to profitability? → If NO, don't build

**What you SHOULD do:**
✅ Finish current milestone
✅ Mark it complete
✅ Move to next milestone
✅ Repeat until profitable

**Remember:** Jeff Bezos started with ONLY books.
Not books + music + electronics + everything.

One thing at a time. Profitable first. 🎯
"""
    },
    "research": {
        "keywords": ["research", "investigate", "explore", "look into", "maybe we should"],
        "message": """
🚫 RESEARCH MODE DETECTED! Pause...

**The Research Trap:**
Research without action = procrastination
Learning without building = stalling
Planning without executing = fear

**Current Phase:** EXECUTION, not research

**You already have:**
✅ A proven strategy (RSI + EMA)
✅ Clear milestones
✅ Step-by-step SOPs
✅ Everything you need to be profitable

**What you DON'T need:**
❌ More research
❌ More learning
❌ More "investigating"

**What you SHOULD do:**
✅ Open the current SOP
✅ Follow it step by step
✅ Build → Test → Ship

**Truth bomb:** No one ever researched their way to profit.
They built their way there.

Stop learning. Start building! 💪
"""
    }
}

ROAST_MESSAGES = [
    """
😤 ALRIGHT, REAL TALK TIME...

You're here checking if you can add more features?
Bro, your bot is giving 0% confidence signals!

**Current situation:**
- Bot: Broken (0% signals)
- Your focus: Adding more features
- Math: Does not compute

**Fix your shit first:**
1. Fix the 0% confidence bug
2. Get to profitable
3. THEN add cool stuff

**Remember:** Every feature added before profit = 
another day you're NOT making money.

Now get back to SOP-001 and FIX THAT BUG! 💪
""",
    """
😒 SOOOO... YOU'RE BACK WITH MORE IDEAS?

**Your brain:** "What if we add this cool feature?"
**Your wallet:** "What if we finish ONE thing first?"

**Reality check:**
- Days since starting: Multiple
- Revenue generated: R0
- Features built: Too many
- Features finished: Not enough

**The prescription:**
✅ Close all other tabs
✅ Open SOP-001
✅ Follow it step by step
✅ Don't come back until milestone complete

**Side effects:** Making actual money 💰

*May cause: Discipline, focus, and profit*

See you when 1.1 is DONE! 🚀
""",
    """
🤨 LET ME GUESS... ANOTHER "GREAT IDEA"?

**The Pattern:**
1. Get excited about new feature
2. Start building it
3. Never finish
4. Repeat

**The Result:**
- 10 half-built features
- 0 completed milestones
- Still not profitable

**The Solution:**
1. Pick ONE milestone
2. Finish it COMPLETELY
3. Mark it DONE
4. THEN move to next

**Hard truth:** You don't have an execution problem.
You have a focus problem.

Fix it. 🎯
"""
]

CELEBRATION_MESSAGES = [
    """
🎉🎉🎉 YOOOOO YOU DID IT! 🎉🎉🎉

Milestone {milestone_id} COMPLETE!

**You just:**
✅ Followed the plan
✅ Didn't get distracted
✅ Made actual progress

**You're officially:**
🏆 More disciplined than 99% of traders
💪 Actually finishing what you start
🎯 On track to profitability

**Keep this energy!**

Next milestone loading... 🚀
""",
    """
🔥🔥🔥 THAT'S WHAT I'M TALKING ABOUT! 🔥🔥🔥

Milestone {milestone_id} = CRUSHED ✅

**The stats:**
- Distractions resisted: Many
- Plans followed: 100%
- Progress made: Real

**You're becoming:**
🧠 Disciplined
⚡ Focused
💰 Profitable (soon)

**Fortune favors the focused.**

Level up! Next mission awaits... 🎮
""",
    """
💪 BOOM! ANOTHER ONE DONE! 💪

{milestone_name} ✅

**This is how winners operate:**
1. Set clear goal
2. Execute relentlessly
3. Complete fully
4. Move to next

**You're doing it RIGHT.**

Keep stacking wins. Millionaire status loading... 🚀
"""
]

def check_scope_creep(user_input):
    """Check if user is trying to build something outside scope"""
    user_input_lower = user_input.lower()
    
    for category, data in SCOPE_CREEP_WARNINGS.items():
        for keyword in data["keywords"]:
            if keyword in user_input_lower:
                return True, data["message"]
    
    return False, None

def motivational_message():
    """Return a random motivational quote"""
    return random.choice(MOTIVATIONAL_QUOTES)

def can_i_build(feature_description):
    """Check if a feature can be built in current phase"""
    print("\n" + "="*70)
    print(f"🤔 CAN I BUILD: {feature_description}?")
    print("="*70)
    
    # Check for scope creep
    is_creep, message = check_scope_creep(feature_description)
    
    if is_creep:
        print(message)
        print("\n" + "="*70)
        print(f"📊 TL;DR: NO, NOT YET")
        print("="*70)
        print("\n✅ What to do instead:")
        print("   1. Run: python3 MASTER_PLANNER.py next")
        print("   2. Work on THAT")
        print("   3. Stay on track!")
        print()
        return False
    
    # Check if it's in current milestones
    data = load_planner_data()
    current_phase_id = data["current_phase"]
    phase = get_phase_info(current_phase_id)
    
    # Check if feature matches any current milestone
    feature_lower = feature_description.lower()
    found = False
    
    for milestone_id, milestone in phase['milestones'].items():
        full_id = f"{current_phase_id}.{milestone_id}"
        if full_id not in data.get("milestones_completed", []):
            milestone_text = f"{milestone['name']} {' '.join(milestone['tasks'])}".lower()
            if any(word in milestone_text for word in feature_lower.split()):
                found = True
                print(f"\n✅ YES! This is in your current phase milestones.")
                print(f"\n👉 Check where it fits:")
                print(f"   python3 MASTER_PLANNER.py status")
                print()
                return True
    
    if not found:
        print(f"\n🚫 NOT IN CURRENT PHASE")
        print(f"\nThis might be a future phase feature, or scope creep.")
        print(f"\n👉 Check current priorities:")
        print(f"   python3 MASTER_PLANNER.py next")
        print()
        return False

def ask_permission(action_description):
    """Ask if an action should be taken"""
    print("\n" + "="*70)
    print(f"🤔 SHOULD I: {action_description}?")
    print("="*70)
    
    # Check for scope creep
    is_creep, message = check_scope_creep(action_description)
    
    if is_creep:
        print(message)
        print("\n" + "="*70)
        print(f"🎯 NEXT ACTIONS")
        print("="*70)
        show_next_actions()
        return False
    
    print(f"\n✅ Doesn't seem like scope creep...")
    print(f"\n👉 But check if it's in your current milestone:")
    print(f"   python3 MASTER_PLANNER.py next")
    print()
    return True

def roast_me():
    """Give tough love when needed"""
    message = random.choice(ROAST_MESSAGES)
    print(message)

def celebrate(milestone_id, milestone_name):
    """Celebrate milestone completion"""
    message = random.choice(CELEBRATION_MESSAGES)
    print(message.format(milestone_id=milestone_id, milestone_name=milestone_name))

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
    
    # Celebrate!
    print()
    celebrate(milestone_id, milestone['name'])
    
    print(f"\n{'='*70}")
    print(f"✅ MILESTONE COMPLETED: {milestone['name']}")
    print(f"   Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*70}")
    
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
        print("\n🎯 OZZY MASTER PLANNER - Your Discipline Enforcer")
        print("\n📋 Core Commands:")
        print("  python3 MASTER_PLANNER.py status           # Show current status")
        print("  python3 MASTER_PLANNER.py next             # Show next actions")
        print("  python3 MASTER_PLANNER.py complete <ID>    # Mark milestone complete")
        print("\n🎭 Personality Commands:")
        print("  python3 MASTER_PLANNER.py caniburn <idea>  # Check if you can build it")
        print("  python3 MASTER_PLANNER.py ask <action>     # Ask permission for action")
        print("  python3 MASTER_PLANNER.py roast            # Need tough love?")
        print("  python3 MASTER_PLANNER.py motivate         # Need motivation?")
        print("\n📚 Help:")
        print("  python3 MASTER_PLANNER.py help             # Show detailed help")
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
    elif command == "caniburn" or command == "canibuild":
        if len(sys.argv) < 3:
            print("❌ Error: Provide feature description")
            print("   Example: python3 MASTER_PLANNER.py caniburn 'agent council'")
            return
        feature = " ".join(sys.argv[2:])
        can_i_build(feature)
    elif command == "ask":
        if len(sys.argv) < 3:
            print("❌ Error: Provide action description")
            print("   Example: python3 MASTER_PLANNER.py ask 'optimize parameters'")
            return
        action = " ".join(sys.argv[2:])
        ask_permission(action)
    elif command == "roast":
        roast_me()
    elif command == "motivate":
        print("\n" + "="*70)
        print("💡 FRIENDLY REMINDER")
        print("="*70)
        print(f"\n{motivational_message()}")
        print(f"\n🎯 Your ONLY goal right now: Simple bot making R5k/week")
        print(f"\n📍 Current milestone: Check with 'python3 MASTER_PLANNER.py next'")
        print(f"\n🔥 Focus wins. Distractions lose.")
        print("\n" + "="*70 + "\n")
    elif command == "help":
        print(__doc__)
        print("\n🎭 PERSONALITY FEATURES:")
        print("\nThe planner now has personality! It will:")
        print("  ✅ Motivate you when on track")
        print("  🚫 Block you when deviating")
        print("  😤 Roast you when procrastinating")
        print("  🎉 Celebrate when achieving")
        print("\nExamples:")
        print("  python3 MASTER_PLANNER.py caniburn 'agent council'")
        print("  python3 MASTER_PLANNER.py ask 'optimize parameters'")
        print("  python3 MASTER_PLANNER.py roast")
        print("  python3 MASTER_PLANNER.py motivate")
        print()
    else:
        print(f"❌ Unknown command: {command}")
        print("   Run: python3 MASTER_PLANNER.py help")

if __name__ == "__main__":
    main()
