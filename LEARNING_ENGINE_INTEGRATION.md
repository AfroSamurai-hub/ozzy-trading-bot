"""
🔗 LEARNING ENGINE INTEGRATION for TradingAgent

Add this to agent/trader.py to close the feedback loop!

This integrates the Learning Engine's confidence multipliers
into the trading decision flow.

Integration Points:
1. Load multipliers in __init__
2. Apply multipliers in analyze_and_decide()
3. Refresh periodically (every N decisions)

═══════════════════════════════════════════════════════════════════
INTEGRATION STEP 1: Add to __init__ (around line 70)
═══════════════════════════════════════════════════════════════════
"""

# In TradingAgent.__init__, add after self._initialize_intelligence_systems():

    def _load_learning_multipliers(self):
        """Load confidence multipliers from Learning Engine"""
        multipliers_file = Path(__file__).parent.parent / "data/learning_multipliers.json"
        
        if not multipliers_file.exists():
            logger.info("📚 No learning multipliers found (using defaults)")
            return {}
        
        with open(multipliers_file) as f:
            multipliers = json.load(f)
        
        logger.info(f"📚 Loaded {len(multipliers)} pattern multipliers from Learning Engine")
        for pattern, mult in multipliers.items():
            emoji = "❌" if mult == 0 else "⬇️" if mult < 1 else "✅" if mult == 1 else "⬆️"
            logger.info(f"   {emoji} {pattern}: {mult:.2f}×")
        
        return multipliers

# Then in __init__:
        self.learning_multipliers = self._load_learning_multipliers()
        self.decisions_since_refresh = 0


"""
═══════════════════════════════════════════════════════════════════
INTEGRATION STEP 2: Apply multipliers in analyze_and_decide()
═══════════════════════════════════════════════════════════════════
"""

# In analyze_and_decide(), AFTER dynamic confidence calculation (around line 325):

        # Fix #1: Dynamic Confidence Calculation (EXISTING CODE)
        base_confidence = ai_decision.get("confidence", 0.75)
        
        confidence_calc = get_confidence_calculator()
        adjusted_confidence, confidence_explanation = confidence_calc.calculate_dynamic_confidence(
            base_confidence,
            market_state,
            pattern_name
        )
        
        # 🧠 NEW: Apply Learning Engine Multipliers
        learning_multiplier = self.learning_multipliers.get(pattern_name, 1.0)
        
        if learning_multiplier == 0.0:
            # Pattern disabled by learning engine
            logger.warning(f"🚫 Learning Engine DISABLED pattern: {pattern_name}")
            return {
                "action": "SKIP",
                "confidence": 0.0,
                "reasoning": f"Pattern '{pattern_name}' disabled by learning engine (poor historical performance)",
                "learning_multiplier": 0.0,
                "original_decision": ai_decision,
            }
        
        # Apply multiplier
        final_confidence = adjusted_confidence * learning_multiplier
        
        logger.info(f"🧠 Learning Engine: {pattern_name} multiplier = {learning_multiplier:.2f}×")
        logger.info(f"   Base: {base_confidence:.0%} → Dynamic: {adjusted_confidence:.0%} → Final: {final_confidence:.0%}")
        
        # Update decision with learning-enhanced confidence
        ai_decision["base_confidence"] = base_confidence
        ai_decision["dynamic_confidence"] = adjusted_confidence
        ai_decision["learning_multiplier"] = learning_multiplier
        ai_decision["confidence"] = final_confidence  # ← This is what gets used!
        ai_decision["confidence_explanation"] = confidence_explanation + f" | Learning: {learning_multiplier:.2f}×"


"""
═══════════════════════════════════════════════════════════════════
INTEGRATION STEP 3: Periodic refresh (around line 400)
═══════════════════════════════════════════════════════════════════
"""

# In analyze_and_decide(), BEFORE logging decision:

        # Refresh multipliers periodically (every 10 decisions)
        self.decisions_since_refresh += 1
        if self.decisions_since_refresh >= 10:
            logger.info("🔄 Refreshing learning multipliers...")
            self.learning_multipliers = self._load_learning_multipliers()
            self.decisions_since_refresh = 0


"""
═══════════════════════════════════════════════════════════════════
COMPLETE FLOW DIAGRAM
═══════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────┐
│                      TRADING DECISION FLOW                       │
└─────────────────────────────────────────────────────────────────┘

1. TradingAgent.analyze_and_decide()
   │
   ├─> Get market data (RSI, EMA, patterns)
   │
   ├─> Call OpenAI (base confidence = 0.75)
   │
   ├─> Dynamic Confidence Calculator
   │   └─> Adjust based on: pattern strength, volume, regime
   │       Result: adjusted_confidence = 0.70
   │
   ├─> 🧠 Learning Engine Multiplier (NEW!)
   │   └─> Load from data/learning_multipliers.json
   │       Pattern "unknown_pattern" → 1.1× (BOOST)
   │       Result: final_confidence = 0.70 × 1.1 = 0.77
   │
   ├─> Pattern Diversity Check (skip if overused)
   │
   ├─> Entry Spacing Check (wait if too soon)
   │
   ├─> Safety Rails (validate confidence, win rate, etc.)
   │
   └─> Execute trade with final_confidence = 0.77

2. Trade Outcome Tracker (scripts/track_trade_outcomes.py)
   │
   └─> Monitor position, label outcome (WIN/LOSS)
       Save to ChromaDB

3. Pattern Performance Analyzer (scripts/analyze_pattern_performance.py)
   │
   └─> Calculate: "unknown_pattern" = 100% WR (3/3 trades)

4. Learning Engine (scripts/learning_engine.py)
   │
   ├─> Rules: >60% WR → BOOST (1.2×)
   │
   └─> Save: data/learning_multipliers.json
       {"unknown_pattern": 1.1}  ← Gradual increase (max 0.1/day)

5. Next Decision (FEEDBACK LOOP CLOSED!)
   │
   └─> TradingAgent loads multipliers
       "unknown_pattern" now gets 1.1× confidence boost!


═══════════════════════════════════════════════════════════════════
AUTOMATION SETUP (Recommended)
═══════════════════════════════════════════════════════════════════

Add a cron job or systemd timer to run learning updates daily:

# Daily at 8 AM: Update learning multipliers
0 8 * * * cd /home/rick/ozzy-simple && /home/rick/ozzy-simple/venv/bin/python scripts/learning_engine.py --update

Or integrate into your trading loop (every 50 trades):

    trade_count = 0
    
    while trading:
        decision = await agent.analyze_and_decide()
        trade_count += 1
        
        # Every 50 trades: Run learning update
        if trade_count % 50 == 0:
            subprocess.run([
                sys.executable,
                "scripts/learning_engine.py",
                "--update"
            ])


═══════════════════════════════════════════════════════════════════
SAFETY & MONITORING
═══════════════════════════════════════════════════════════════════

1. Check multipliers before trading:
   python3 scripts/learning_engine.py --show

2. Review DISABLE actions manually:
   - Learning engine flags them but doesn't auto-apply
   - Human must approve pattern disabling

3. Monitor learning history:
   cat data/learning_history.json

4. Revert if needed:
   - Delete data/learning_multipliers.json
   - System falls back to defaults (1.0× for all)

5. Daily reports show learning impact:
   python3 scripts/generate_daily_report.py


═══════════════════════════════════════════════════════════════════
EXPECTED IMPACT
═══════════════════════════════════════════════════════════════════

From 5 trades:
- "unknown_pattern": 100% WR → 1.1× multiplier
  → 10% confidence boost on future trades
  → Higher position sizing, more aggressive entries

After 50 trades (expected):
- Good patterns (70%+ WR): 1.2× multiplier
  → 20% confidence boost
  → Significantly more capital allocated

- Bad patterns (<40% WR): 0.0× multiplier (DISABLED)
  → Completely blocked
  → Save capital, avoid losses

- OK patterns (50-60% WR): 1.0× multiplier
  → No change
  → Let more data accumulate


═══════════════════════════════════════════════════════════════════
NEXT STEPS
═══════════════════════════════════════════════════════════════════

1. ✅ Review this integration guide
2. 🔧 Add code to agent/trader.py (3 integration points above)
3. 🧪 Test with bulletproof_test.py (verify multipliers applied)
4. 🚀 Deploy to paper trading (watch learning happen!)
5. 📊 Monitor daily reports (see improvements over time)

"""

# Example usage in bulletproof_test.py:

def test_learning_integration():
    """Test that learning multipliers are loaded and applied"""
    from agent.trader import TradingAgent
    
    agent = TradingAgent(mcp_server, capital=5000)
    
    # Check multipliers loaded
    print(f"Loaded {len(agent.learning_multipliers)} multipliers")
    for pattern, mult in agent.learning_multipliers.items():
        print(f"  {pattern}: {mult:.2f}×")
    
    # Make a decision
    decision = await agent.analyze_and_decide()
    
    # Check multiplier was applied
    assert "learning_multiplier" in decision
    print(f"Learning multiplier applied: {decision['learning_multiplier']:.2f}×")
    print(f"Final confidence: {decision['confidence']:.0%}")
