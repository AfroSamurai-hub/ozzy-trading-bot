#!/usr/bin/env python3
"""
OZZY AI AGENT - Ambitious Autonomous Trading Intelligence (local implementation)

Ambitious, goal-driven partner that analyzes signals, proposes improvements,
and stores rich analysis to SQLite for monitoring and comparison.

This implementation avoids external API calls and simulates ambitious behavior
based on the incoming signal data. Safe for Phase 1.5 monitoring.
"""
from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime
from typing import Dict, Any


class OzzyAIAgent:
    """Ambitious AI trading agent with goals and autonomy (local, simulated)."""

    def __init__(self, db_path: str = 'ozzy_simple.db') -> None:
        self.db_path = db_path
        # Personality and goals
        self.risk_appetite = "AGGRESSIVE"
        self.approval_target = 40.0  # % approvals targeted per day
        self.rr_min_target = 2.5

        self.session_stats = {
            'signals_analyzed': 0,
            'opportunities_found': 0,
            'approvals': 0,
            'rejections': 0,
            'improvements_suggested': 0,
            'base_system_challenges': 0,
        }

        self._init_agent_tables()

    # ---------------------- DB SCHEMA ----------------------
    def _init_agent_tables(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS ai_agent_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT,
                base_signal TEXT,
                base_confidence REAL,
                ai_action TEXT,
                ai_confidence REAL,
                ai_reasoning TEXT,
                risk_appetite TEXT,
                opportunity_score REAL,
                conviction_level TEXT,
                suggested_entry REAL,
                suggested_stop REAL,
                suggested_target REAL,
                improved_rr_ratio REAL,
                alignment_with_goals REAL,
                learning_insight TEXT,
                challenge_to_base TEXT,
                agreement BOOLEAN,
                execution_recommendation TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS ai_agent_performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                signals_analyzed INTEGER,
                approval_rate REAL,
                avg_confidence_boost REAL,
                avg_rr_improvement REAL,
                opportunities_found INTEGER,
                challenges_made INTEGER,
                goal_achievement_score REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        conn.commit()
        conn.close()

    # ---------------------- CORE API ----------------------
    def analyze_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a base signal with an ambitious mindset and store results.

        Expected signal keys (best-effort):
        - symbol, action (LONG/SHORT), confidence, quality
        - entry_price, stop_loss, take_profit, risk_reward_ratio
        - technical_data.rsi / ema_short / ema_long / volume_ratio / price_momentum
        """
        self.session_stats['signals_analyzed'] += 1

        symbol = signal.get('symbol', 'UNKNOWN')
        base_action = str(signal.get('action', 'HOLD')).upper()
        base_conf = float(signal.get('confidence') or 0.0)

        tech = signal.get('technical_data', {}) if isinstance(signal.get('technical_data'), dict) else {}
        rsi = _to_float(tech.get('rsi'))
        vol = _to_float(tech.get('volume_ratio'))
        momentum = _to_float(tech.get('price_momentum'))

        # Decide ambitious action
        decision = self._decide_action(base_action, base_conf, rsi, vol, momentum)

        # Improvements proposal when applicable
        improvements = {}
        suggested_rr = None
        if decision['action'] in ('IMPROVE', 'APPROVE', 'CHALLENGE'):
            entry = _to_float(signal.get('entry_price'))
            stop = _to_float(signal.get('stop_loss'))
            target = _to_float(signal.get('take_profit'))
            # Suggest a modestly better entry and more ambitious target
            if entry and stop and target:
                tweak = 0.005  # 0.5%
                if base_action == 'LONG':
                    better_entry = entry * (1 - tweak)
                elif base_action == 'SHORT':
                    better_entry = entry * (1 + tweak)
                else:
                    better_entry = entry
                better_target = target * (1 + 0.08)  # push for 8% more
                suggested_rr = max(_to_float(signal.get('risk_reward_ratio')) or 2.0, 2.6)
                improvements = {
                    'entry_price': round(better_entry, 6),
                    'stop_loss': stop,
                    'take_profit': round(better_target, 6),
                    'improved_rr': suggested_rr,
                    'position_size_multiplier': 1.2,
                    'why_better': 'Optimized entry and extended target to lift R/R above 2.5.'
                }

        analysis = {
            'timestamp': datetime.now().isoformat(timespec='seconds'),
            'symbol': symbol,
            'base_signal': base_action,
            'base_confidence': base_conf,
            'action': decision['action'],
            'ai_confidence': decision['ai_confidence'],
            'conviction_level': decision['conviction'],
            'opportunity_score': decision['opportunity_score'],
            'reasoning': decision['reasons'],
            'aggressive_take': decision['aggressive_take'],
            'improvements': improvements,
            'challenge_to_base': decision.get('challenge'),
            'execution_plan': decision['execution'],
            'risk_analysis': decision['risk'],
            'learning_insight': decision['learning'],
            'alignment_with_goals': decision['goal_alignment'],
            'agreement': self._calc_agreement(base_action, decision['action'])
        }

        # Persist
        self._store_agent_analysis(analysis)

        # Update local stats
        self._update_stats(analysis)

        # Friendly console output
        self._display(analysis)

        return analysis

    # ---------------------- DECISION LOGIC ----------------------
    def _decide_action(self, base_action: str, base_conf: float, rsi: float | None, vol: float | None, momentum: float | None) -> Dict[str, Any]:
        reasons = []
        aggressive_take = "Hunting for edge."
        goal_alignment = 8.0

        # Heuristics for ambition
        if base_conf >= 55:
            action = 'APPROVE'
            ai_conf = min(base_conf + 12, 90)
            conviction = 'HIGH'
            opp = 8.2
            execution = {'recommendation': 'EXECUTE_NOW', 'timing': 'NOW', 'reasoning': 'Strong enough as-is.'}
            reasons.append('Confidence is solid; setup quality sufficient.')
        elif base_conf >= 40:
            action = 'IMPROVE'
            ai_conf = min(base_conf + 15, 85)
            conviction = 'HIGH'
            opp = 8.5
            execution = {'recommendation': 'EXECUTE_MODIFIED', 'timing': 'NOW', 'reasoning': 'Optimized entry/targets lift R/R.'}
            reasons.append('Good bones; optimization can unlock better R/R.')
        else:
            # Below 40: either CHALLENGE (timing), COUNTER (if overbought), or REJECT
            if (base_action == 'LONG' and rsi and rsi >= 70) or (base_action == 'SHORT' and rsi and rsi <= 30):
                action = 'COUNTER'
                ai_conf = 76.0
                conviction = 'HIGH'
                opp = 7.6
                execution = {'recommendation': 'COUNTER_SIGNAL', 'timing': 'WAIT_FOR_PULLBACK', 'reasoning': 'Overextended; reversal likely.'}
                aggressive_take = 'Opposite direction is the play.'
                reasons.append('RSI extreme suggests reversal opportunity.')
            elif vol and vol >= 1.5:
                action = 'CHALLENGE'
                ai_conf = 71.0
                conviction = 'MEDIUM'
                opp = 7.8
                execution = {'recommendation': 'WAIT_FOR_BETTER_ENTRY', 'timing': 'WAIT_15MIN', 'reasoning': 'Let volatility give a better entry.'}
                aggressive_take = 'Timing is off; wait for pullback then strike.'
                reasons.append('Volume expansion suggests better timing soon.')
            elif base_conf >= 35:
                action = 'CHALLENGE'
                ai_conf = 68.0
                conviction = 'MEDIUM'
                opp = 7.2
                execution = {'recommendation': 'WAIT_FOR_BETTER_ENTRY', 'timing': 'WAIT_1HOUR', 'reasoning': 'Need improved alignment before entry.'}
                reasons.append('Signal has potential but needs better entry.')
            else:
                action = 'REJECT'
                ai_conf = 80.0
                conviction = 'MEDIUM'
                opp = 5.0
                execution = {'recommendation': 'SKIP', 'timing': 'N/A', 'reasoning': 'No reliable edge right now.'}
                reasons.append('Setup quality too low to justify risk.')

        risk = {
            'risk_level': 'MODERATE' if action in ('APPROVE', 'IMPROVE', 'CHALLENGE') else 'LOW',
            'risk_worth_it': action in ('APPROVE', 'IMPROVE', 'CHALLENGE', 'COUNTER'),
            'max_position_size': 1.5 if action in ('APPROVE', 'IMPROVE') else 1.0,
            'why_acceptable': 'Expected reward outweighs risk under ambitious criteria.' if action != 'REJECT' else 'Risk not justified.'
        }

        challenge_text = None
        if action in ('CHALLENGE', 'COUNTER'):
            challenge_text = 'Base timing/direction can be improved for superior R/R.'

        learning = 'Volatility + moderate confidence => wait for pullback then execute.' if action == 'CHALLENGE' else 'Aggressive optimization lifts R/R.'

        return {
            'action': action,
            'ai_confidence': ai_conf,
            'conviction': conviction,
            'opportunity_score': opp,
            'execution': execution,
            'reasons': reasons,
            'aggressive_take': aggressive_take,
            'risk': risk,
            'challenge': challenge_text,
            'learning': learning,
            'goal_alignment': goal_alignment,
        }

    @staticmethod
    def _calc_agreement(base_action: str, ai_action: str) -> bool:
        if ai_action in ('APPROVE', 'IMPROVE') and base_action in ('LONG', 'SHORT'):
            return True
        if ai_action == 'COUNTER':
            return False
        if ai_action == 'CHALLENGE':
            return False
        return False

    # ---------------------- PERSISTENCE ----------------------
    def _store_agent_analysis(self, analysis: Dict[str, Any]) -> None:
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        improvements = analysis.get('improvements') or {}
        cur.execute(
            '''
            INSERT INTO ai_agent_analysis (
                timestamp, symbol, base_signal, base_confidence,
                ai_action, ai_confidence, ai_reasoning,
                risk_appetite, opportunity_score, conviction_level,
                suggested_entry, suggested_stop, suggested_target, improved_rr_ratio,
                alignment_with_goals, learning_insight, challenge_to_base,
                agreement, execution_recommendation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                analysis['timestamp'],
                analysis.get('symbol'),
                analysis.get('base_signal'),
                analysis.get('base_confidence'),
                analysis.get('action'),
                analysis.get('ai_confidence'),
                json.dumps(analysis.get('reasoning') or []),
                self.risk_appetite,
                analysis.get('opportunity_score'),
                analysis.get('conviction_level'),
                improvements.get('entry_price'),
                improvements.get('stop_loss'),
                improvements.get('take_profit'),
                improvements.get('improved_rr'),
                analysis.get('alignment_with_goals'),
                analysis.get('learning_insight'),
                analysis.get('challenge_to_base'),
                1 if analysis.get('agreement') else 0,
                (analysis.get('execution_plan') or {}).get('recommendation')
            )
        )
        conn.commit()
        conn.close()

    def _update_stats(self, analysis: Dict[str, Any]) -> None:
        action = (analysis.get('action') or '').upper()
        if action == 'APPROVE':
            self.session_stats['approvals'] += 1
            self.session_stats['opportunities_found'] += 1
        elif action == 'REJECT':
            self.session_stats['rejections'] += 1
        elif action in ('IMPROVE', 'CHALLENGE', 'COUNTER'):
            self.session_stats['improvements_suggested'] += 1
            if action in ('CHALLENGE', 'COUNTER'):
                self.session_stats['base_system_challenges'] += 1

    # ---------------------- DISPLAY ----------------------
    def _display(self, analysis: Dict[str, Any]) -> None:
        print("\n" + "=" * 70)
        print("🤖 OZZY AI AGENT - AMBITIOUS ANALYSIS")
        print("=" * 70)
        print(f"\n📊 BASE SYSTEM: {analysis.get('base_signal')} {analysis.get('symbol')} @ {analysis.get('base_confidence', 0):.1f}%")
        print("\n🎯 AI AGENT DECISION:")
        action_emoji = {
            'APPROVE': '✅',
            'IMPROVE': '⚡',
            'CHALLENGE': '🔥',
            'REJECT': '❌',
            'COUNTER': '🔄'
        }
        emoji = action_emoji.get(analysis.get('action'), '❓')
        print(f"   {emoji} {analysis.get('action')} (Confidence: {float(analysis.get('ai_confidence') or 0):.1f}%)")
        print(f"   🎖️  Conviction: {analysis.get('conviction_level')}")
        print(f"   ⭐ Opportunity Score: {float(analysis.get('opportunity_score') or 0):.1f}/10")
        if analysis.get('agreement'):
            print("   🤝 AI AGREES - Let's hunt this opportunity!")
        elif analysis.get('action') == 'COUNTER':
            print("   🔄 AI SEES OPPOSITE - Counter-signal opportunity!")
        else:
            print("   💭 AI HAS DIFFERENT VIEW")

        if analysis.get('aggressive_take'):
            print("\n💪 AGGRESSIVE TAKE:")
            print(f"   \"{analysis['aggressive_take']}\"")

        if analysis.get('reasoning'):
            print("\n🧠 REASONING:")
            for r in (analysis['reasoning'] or [])[:3]:
                print(f"   • {r}")

        impr = analysis.get('improvements') or {}
        if impr:
            print("\n⚡ IMPROVEMENTS:")
            if 'entry_price' in impr:
                print(f"   Entry: {impr['entry_price']}")
            if 'stop_loss' in impr:
                print(f"   Stop: {impr['stop_loss']}")
            if 'take_profit' in impr:
                print(f"   Target: {impr['take_profit']}")
            if 'improved_rr' in impr:
                print(f"   R/R: 1:{float(impr['improved_rr']):.2f}")

        execp = analysis.get('execution_plan') or {}
        if execp:
            rec = execp.get('recommendation', 'UNKNOWN')
            timing = execp.get('timing', 'UNKNOWN')
            print("\n📍 EXECUTION PLAN:")
            print(f"   Action: {rec}")
            print(f"   Timing: {timing}")

        approval_rate = (self.session_stats['approvals'] / max(1, self.session_stats['signals_analyzed'])) * 100.0
        print("\n" + "-" * 70)
        print(
            f"📊 SESSION STATS: Analyzed: {self.session_stats['signals_analyzed']} | "
            f"Approved: {self.session_stats['approvals']} ({approval_rate:.1f}%) | "
            f"Opportunities: {self.session_stats['opportunities_found']} | "
            f"Challenges: {self.session_stats['base_system_challenges']}"
        )
        print("=" * 70 + "\n")


def _to_float(x) -> float | None:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


if __name__ == '__main__':
    # Tiny smoke test
    agent = OzzyAIAgent()
    agent.analyze_signal({
        'symbol': 'BTCUSDT',
        'action': 'LONG',
        'confidence': 42.0,
        'quality': 'OK',
        'entry_price': 65234.0,
        'stop_loss': 63929.0,
        'take_profit': 67844.0,
        'risk_reward_ratio': 2.0,
        'technical_data': {'rsi': 48.3, 'volume_ratio': 1.8, 'price_momentum': 0.1}
    })
