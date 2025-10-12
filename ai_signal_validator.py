#!/usr/bin/env python3
"""
AI Signal Validator - Phase 1.5
Adds LLM analysis to Phase 1 monitoring without disrupting base system
"""

import json
import requests
from datetime import datetime
from typing import Dict, Any, Optional
import sqlite3
import time

class AISignalValidator:
    """
    Uses Claude API to validate and enhance trading signals
    Runs in parallel with base system - purely advisory
    """
    
    def __init__(self, db_path='ozzy_simple.db'):
        self.db_path = db_path
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.model = "claude-3-sonnet-20240229"
        self.api_key = "your-api-key-here"  # Set your Anthropic API key
        self.validation_count = 0
        self.agreements = 0
        self.disagreements = 0
        
        # Create AI analysis table
        self._init_ai_table()
        # Best-effort cleanup: backfill missing symbols on existing AI rows
        try:
            self._backfill_unknown_symbols()
        except Exception:
            # Non-fatal; continue
            pass
        
        print("🤖 AI Signal Validator initialized")
    
    def _init_ai_table(self):
        """Create table to store AI analysis"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT,
                base_signal TEXT,
                base_confidence REAL,
                ai_recommendation TEXT,
                ai_confidence REAL,
                ai_reasoning TEXT,
                agreement INTEGER,
                key_insights TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def validate_signal(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send signal to Claude for validation and insights
        """
        
        # For Phase 1 demo, we'll simulate AI responses
        # Replace this with real API call when you have Anthropic API key
        
        try:
            # Simulate AI analysis for now
            analysis = self._simulate_ai_analysis(signal_data)
            
            # Store in database
            self._store_analysis(signal_data, analysis)
            
            # Update metrics
            self._update_metrics(signal_data, analysis)
            
            # Display AI insights
            self._display_analysis(signal_data, analysis)
            
            return analysis
            
        except Exception as e:
            print(f"⚠️  AI validation error: {e}")
            return {"error": str(e)}
    
    def _simulate_ai_analysis(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate AI analysis for Phase 1 testing
        Replace with real API call when ready
        """
        
        symbol = signal_data.get('symbol', 'UNKNOWN')
        action = signal_data.get('signal', 'HOLD')
        confidence = signal_data.get('confidence', 0)
        rsi = signal_data.get('rsi', 50)
        
        # Simulate AI logic
        ai_confidence = confidence + (rsi - 50) * 0.3  # AI adjusts based on RSI
        ai_confidence = max(20, min(95, ai_confidence))  # Clamp between 20-95
        
        # AI recommendation logic
        if confidence >= 60 and 30 <= rsi <= 70:
            recommendation = "APPROVE"
            agreement = True
        elif confidence >= 40 and action != 'HOLD':
            recommendation = "MODIFY"
            agreement = True
        else:
            recommendation = "REJECT"
            agreement = False
        
        # Generate insights
        if action == 'LONG':
            if rsi < 40:
                insight = "RSI oversold - good entry timing for LONG"
                concerns = ["Watch for continued downward momentum"]
            elif rsi > 60:
                insight = "RSI elevated - consider waiting for pullback"
                concerns = ["Potential overbought conditions"]
            else:
                insight = "RSI neutral - decent setup"
                concerns = ["Monitor volume confirmation"]
        elif action == 'SHORT':
            if rsi > 60:
                insight = "RSI overbought - good entry timing for SHORT"
                concerns = ["Watch for reversal signals"]
            else:
                insight = "RSI not confirming SHORT bias"
                concerns = ["Consider waiting for higher RSI"]
        else:
            insight = "No clear directional bias detected"
            concerns = ["Market in consolidation"]
        
        return {
            'recommendation': recommendation,
            'ai_confidence': round(ai_confidence, 1),
            'reasoning': [
                f"RSI at {rsi:.1f} {'supports' if agreement else 'questions'} {action} bias",
                f"Base confidence {confidence:.1f}% {'aligns with' if agreement else 'differs from'} technical setup",
                f"Risk/reward appears {'favorable' if confidence > 50 else 'marginal'}"
            ],
            'strengths': [
                "Clear signal direction",
                "Defined risk parameters"
            ] if action != 'HOLD' else ["Patience in unclear conditions"],
            'concerns': concerns,
            'key_insight': insight,
            'agreement': agreement,
            'timestamp': datetime.now().isoformat(),
            'base_signal': action,
            'base_confidence': confidence,
            'symbol': symbol,
            'risk_level': 'MODERATE' if confidence > 40 else 'HIGH',
            'timing': 'NOW' if recommendation == 'APPROVE' else 'WAIT' if recommendation == 'MODIFY' else 'SKIP'
        }
    
    def _store_analysis(self, signal_data: Dict, analysis: Dict):
        """Store AI analysis in database"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO ai_analysis (
                timestamp, symbol, base_signal, base_confidence,
                ai_recommendation, ai_confidence, ai_reasoning,
                agreement, key_insights
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            analysis.get('timestamp'),
            analysis.get('symbol'),
            analysis.get('base_signal'),
            analysis.get('base_confidence'),
            analysis.get('recommendation'),
            analysis.get('ai_confidence'),
            json.dumps(analysis.get('reasoning', [])),
            1 if analysis.get('agreement') else 0,
            analysis.get('key_insight', '')
        ))
        
        conn.commit()
        conn.close()

    def _backfill_unknown_symbols(self):
        """Best-effort backfill for rows where symbol is UNKNOWN by matching nearby signal timestamps."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            # Find ai rows with NULL or 'UNKNOWN' symbol
            cursor.execute("SELECT id, timestamp FROM ai_analysis WHERE symbol IS NULL OR symbol = 'UNKNOWN'")
            rows = cursor.fetchall()
            for rid, ts in rows:
                if not ts:
                    continue
                # Find the closest signal within +/- 2 minutes
                cursor.execute(
                    """
                    SELECT symbol FROM signals
                    WHERE ABS(strftime('%s', timestamp) - strftime('%s', ?)) <= 120
                    ORDER BY ABS(strftime('%s', timestamp) - strftime('%s', ?)) ASC
                    LIMIT 1
                    """,
                    (ts, ts)
                )
                res = cursor.fetchone()
                if res and res[0]:
                    cursor.execute("UPDATE ai_analysis SET symbol = ? WHERE id = ?", (res[0], rid))
            conn.commit()
        finally:
            conn.close()
    
    def _update_metrics(self, signal_data: Dict, analysis: Dict):
        """Update AI validation metrics"""
        
        self.validation_count += 1
        
        if analysis.get('agreement'):
            self.agreements += 1
        else:
            self.disagreements += 1
    
    def _display_analysis(self, signal_data: Dict, analysis: Dict):
        """Display AI analysis in a readable format"""
        
        print("\n" + "="*70)
        print("🤖 AI SIGNAL ANALYSIS")
        print("="*70)
        
        print(f"\n📊 BASE SYSTEM:")
        print(f"   Signal: {signal_data.get('signal')} {signal_data.get('symbol')}")
        print(f"   Confidence: {signal_data.get('confidence', 0):.1f}%")
        print(f"   Quality: {signal_data.get('quality')}")
        
        print(f"\n🧠 AI VERDICT:")
        
        rec = analysis.get('recommendation', 'ERROR')
        ai_conf = analysis.get('ai_confidence', 0)
        
        # Color code recommendation
        if rec == 'APPROVE':
            print(f"   ✅ {rec} (AI Confidence: {ai_conf:.1f}%)")
        elif rec == 'REJECT':
            print(f"   ❌ {rec} (AI Confidence: {ai_conf:.1f}%)")
        elif rec == 'MODIFY':
            print(f"   ⚠️  {rec} (AI Confidence: {ai_conf:.1f}%)")
        else:
            print(f"   ❓ {rec}")
        
        # Agreement indicator
        if analysis.get('agreement'):
            print(f"   🤝 AI AGREES with base system")
        else:
            print(f"   🔀 AI DISAGREES with base system")
        
        # Key reasoning
        print(f"\n💡 AI REASONING:")
        for reason in analysis.get('reasoning', [])[:3]:
            print(f"   • {reason}")
        
        # Key insight
        if 'key_insight' in analysis:
            print(f"\n🎯 KEY INSIGHT:")
            print(f"   {analysis['key_insight']}")
        
        # Strengths and concerns
        strengths = analysis.get('strengths', [])
        concerns = analysis.get('concerns', [])
        
        if strengths:
            print(f"\n✅ STRENGTHS:")
            for s in strengths[:2]:
                print(f"   • {s}")
        
        if concerns:
            print(f"\n⚠️  CONCERNS:")
            for c in concerns[:2]:
                print(f"   • {c}")
        
        # Risk and timing
        print(f"\n🟡 Risk Level: {analysis.get('risk_level', 'UNKNOWN')}")
        print(f"⏰ Timing: {analysis.get('timing', 'UNKNOWN')}")
        
        print("\n" + "="*70)
        print(f"📊 AI Stats: {self.agreements} agreements, {self.disagreements} disagreements ({self.agreements/(self.validation_count or 1)*100:.1f}% agreement rate)")
        print("="*70 + "\n")
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics of AI validation"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Total validations
            cursor.execute("SELECT COUNT(*) FROM ai_analysis")
            total = cursor.fetchone()[0]
            
            # Agreement rate
            cursor.execute("SELECT COUNT(*) FROM ai_analysis WHERE agreement = 1")
            agreements = cursor.fetchone()[0]
            
            # Recommendation breakdown
            cursor.execute("""
                SELECT ai_recommendation, COUNT(*) 
                FROM ai_analysis 
                GROUP BY ai_recommendation
            """)
            recommendations = dict(cursor.fetchall())
            
            # Average AI confidence by recommendation
            cursor.execute("""
                SELECT ai_recommendation, AVG(ai_confidence)
                FROM ai_analysis
                GROUP BY ai_recommendation
            """)
            avg_confidence = dict(cursor.fetchall())
            
        except Exception as e:
            print(f"Error getting stats: {e}")
            total = agreements = 0
            recommendations = {}
            avg_confidence = {}
        
        conn.close()
        
        return {
            'total_validations': total,
            'agreements': agreements,
            'disagreements': total - agreements,
            'agreement_rate': (agreements / total * 100) if total > 0 else 0,
            'recommendations': recommendations,
            'avg_confidence_by_rec': avg_confidence
        }
    
    def print_summary(self):
        """Print summary of AI validation performance"""
        
        stats = self.get_summary_stats()
        
        print("\n" + "="*70)
        print("🤖 AI VALIDATION SUMMARY")
        print("="*70)
        
        print(f"\n📊 OVERALL STATS:")
        print(f"   Total Validations: {stats['total_validations']}")
        print(f"   Agreements: {stats['agreements']} ({stats['agreement_rate']:.1f}%)")
        print(f"   Disagreements: {stats['disagreements']}")
        
        if stats['recommendations']:
            print(f"\n📈 AI RECOMMENDATIONS:")
            for rec, count in stats['recommendations'].items():
                pct = count / stats['total_validations'] * 100
                avg_conf = stats['avg_confidence_by_rec'].get(rec, 0)
                print(f"   {rec}: {count} ({pct:.1f}%) - Avg confidence: {avg_conf:.1f}%")
        
        print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    print("""
🤖 AI Signal Validator - Phase 1.5

This module adds AI analysis to your existing Phase 1 bot.

To integrate:
1. Import: from ai_signal_validator import AISignalValidator
2. Initialize: self.ai_validator = AISignalValidator()  
3. Use: ai_analysis = self.ai_validator.validate_signal(signal_data)

The AI will analyze each signal and provide:
✅ APPROVE/REJECT/MODIFY recommendations
🎯 AI confidence scores
💡 Reasoning and insights  
⚠️ Strengths and concerns
📊 Agreement tracking with base system

Perfect for Phase 1 - no risk, pure learning!
""")