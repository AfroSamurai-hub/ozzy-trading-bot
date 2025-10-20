"""
Trading Handbook Loader
Loads and validates trades against institutional trading knowledge base
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class TradingHandbook:
    """
    Loads and provides access to institutional trading knowledge
    Based on Renaissance Technologies / Two Sigma methodology
    """
    
    def __init__(self, handbook_dir='/home/rick/ozzy-simple/handbook'):
        self.handbook_dir = Path(handbook_dir)
        self.knowledge = {}
        self._load_all_documents()
    
    def _load_all_documents(self):
        """Load all markdown files from handbook directory"""
        if not self.handbook_dir.exists():
            print(f"⚠️  Handbook directory not found: {self.handbook_dir}")
            return
        
        for md_file in self.handbook_dir.glob('*.md'):
            try:
                with open(md_file, 'r') as f:
                    self.knowledge[md_file.stem] = f.read()
                print(f"✅ Loaded: {md_file.name}")
            except Exception as e:
                print(f"❌ Error loading {md_file.name}: {e}")
        
        print(f"\n📚 Loaded {len(self.knowledge)} handbook documents")
    
    def get_strategy_rules(self, strategy_name: str) -> str:
        """Get specific strategy documentation"""
        key = strategy_name.upper() + '_STRATEGY'
        return self.knowledge.get(key, f"Strategy '{strategy_name}' not found in handbook")
    
    def get_pattern_rules(self, pattern_name: str) -> str:
        """Get specific pattern rules from pattern library"""
        pattern_lib = self.knowledge.get('PATTERN_LIBRARY', '')
        
        if not pattern_lib:
            return "Pattern library not loaded"
        
        # Extract section for specific pattern
        lines = pattern_lib.split('\n')
        in_pattern = False
        pattern_rules = []
        
        for line in lines:
            if pattern_name.lower() in line.lower() and line.startswith('###'):
                in_pattern = True
            elif in_pattern and line.startswith('###'):
                break
            elif in_pattern:
                pattern_rules.append(line)
        
        return '\n'.join(pattern_rules) if pattern_rules else f"Pattern '{pattern_name}' not found"
    
    def get_risk_rules(self) -> str:
        """Get all risk management rules"""
        return self.knowledge.get('RISK_RULES', 'Risk rules not loaded')
    
    def get_regime_guidance(self, current_regime: str) -> str:
        """Get strategy guidance for current market regime"""
        regime_doc = self.knowledge.get('MARKET_REGIMES', '')
        
        if not regime_doc:
            return "Market regimes not loaded"
        
        # Extract section for specific regime
        lines = regime_doc.split('\n')
        in_regime = False
        regime_guidance = []
        
        for line in lines:
            if current_regime.upper() in line.upper() and line.startswith('###'):
                in_regime = True
            elif in_regime and line.startswith('###'):
                break
            elif in_regime:
                regime_guidance.append(line)
        
        return '\n'.join(regime_guidance) if regime_guidance else f"Regime '{current_regime}' not found"
    
    def check_trade_against_rules(self, trade_signal: Dict) -> Tuple[bool, List[str]]:
        """
        Validate trade signal against handbook rules
        
        Args:
            trade_signal: Dict containing trade details:
                - symbol: str
                - action: str ('LONG', 'SHORT', 'SKIP')
                - strategy: str (e.g., 'momentum')
                - pattern: Optional[str] (e.g., 'bullish_engulfing')
                - confidence: float (0-1)
                - risk_amount: float (dollar risk)
                - account_balance: float
                - volume_confirmed: bool
                - trend_confirmed: bool
                - market_regime: str ('TRENDING', 'RANGING', 'HIGH_VOLATILITY')
                - entry_price: float
                - stop_loss: float
                - take_profit: float
        
        Returns:
            (approved: bool, violations: List[str])
        """
        violations = []
        
        # Skip check for SKIP actions
        if trade_signal.get('action') == 'SKIP':
            return True, []
        
        # 1. Position Sizing Check (2% rule)
        risk_amount = trade_signal.get('risk_amount', 0)
        account_balance = trade_signal.get('account_balance', 0)
        
        if account_balance > 0:
            risk_percentage = (risk_amount / account_balance) * 100
            
            if risk_percentage > 2.0:
                violations.append(f"Position size {risk_percentage:.1f}% exceeds 2% rule")
        
        # 2. Stop Loss Check
        if 'entry_price' in trade_signal and 'stop_loss' in trade_signal:
            entry = trade_signal['entry_price']
            stop = trade_signal['stop_loss']
            
            if entry > 0:
                stop_distance = abs(entry - stop) / entry * 100
                
                # Stop should be around 2% for momentum trades
                if stop_distance < 1.0:
                    violations.append(f"Stop too tight: {stop_distance:.1f}% (recommended 2%)")
                elif stop_distance > 5.0:
                    violations.append(f"Stop too wide: {stop_distance:.1f}% (max 5%)")
        
        # 3. Risk/Reward Check (min 2:1)
        if all(k in trade_signal for k in ['entry_price', 'stop_loss', 'take_profit']):
            entry = trade_signal['entry_price']
            stop = trade_signal['stop_loss']
            tp = trade_signal['take_profit']
            
            risk = abs(entry - stop)
            reward = abs(tp - entry)
            
            if risk > 0:
                rr_ratio = reward / risk
                
                if rr_ratio < 2.0:
                    violations.append(f"R/R ratio {rr_ratio:.1f}:1 below 2:1 minimum")
        
        # 4. Pattern Confirmation Check
        if 'pattern' in trade_signal and trade_signal.get('pattern'):
            pattern = trade_signal['pattern']
            
            # Volume confirmation required
            if not trade_signal.get('volume_confirmed', False):
                violations.append(f"Pattern '{pattern}' lacks volume confirmation (handbook requirement)")
            
            # Trend confirmation required
            if not trade_signal.get('trend_confirmed', False):
                violations.append(f"Pattern '{pattern}' lacks trend confirmation (handbook requirement)")
            
            # Check if pattern is in approved list
            pattern_rules = self.get_pattern_rules(pattern)
            
            if 'RETIRED' in pattern_rules or 'not found' in pattern_rules.lower():
                violations.append(f"Pattern '{pattern}' not approved in handbook")
        
        # 5. Market Regime Check
        regime = trade_signal.get('market_regime', 'UNKNOWN')
        strategy = trade_signal.get('strategy', 'unknown')
        
        if regime == 'HIGH_VOLATILITY':
            violations.append(f"High volatility regime - handbook recommends minimal trading")
        
        elif regime == 'RANGING' and strategy.lower() == 'momentum':
            violations.append(f"Momentum strategy not recommended for RANGING regime (handbook violation)")
        
        elif regime == 'TRENDING' and strategy.lower() == 'mean_reversion':
            violations.append(f"Mean reversion not recommended for TRENDING regime (handbook violation)")
        
        # 6. VIX Emergency Check
        vix = trade_signal.get('vix', 0)
        if vix > 40:
            violations.append(f"VIX {vix:.1f} > 40 - handbook EMERGENCY STOP condition")
        
        # Determine approval
        approved = len(violations) == 0
        
        return approved, violations
    
    def validate_confirmations(self, trade_signal: Dict) -> Dict[str, bool]:
        """
        Check which confirmations are met
        
        Returns:
            Dict of confirmation checks: {'volume': True, 'trend': False, ...}
        """
        confirmations = {
            'volume': trade_signal.get('volume_confirmed', False),
            'trend': trade_signal.get('trend_confirmed', False),
            'support_resistance': trade_signal.get('at_key_level', False),
            'rsi_momentum': trade_signal.get('rsi_confirmed', False),
            'regime_appropriate': True,  # Default, checked separately
            'stop_loss_set': 'stop_loss' in trade_signal,
            'take_profit_set': 'take_profit' in trade_signal,
            'position_sized': 'risk_amount' in trade_signal
        }
        
        # Regime appropriateness check
        regime = trade_signal.get('market_regime', 'UNKNOWN')
        strategy = trade_signal.get('strategy', '')
        
        if regime == 'HIGH_VOLATILITY':
            confirmations['regime_appropriate'] = False
        elif regime == 'RANGING' and strategy.lower() == 'momentum':
            confirmations['regime_appropriate'] = False
        elif regime == 'TRENDING' and strategy.lower() == 'mean_reversion':
            confirmations['regime_appropriate'] = False
        
        return confirmations
    
    def get_confirmation_count(self, trade_signal: Dict) -> Tuple[int, int]:
        """
        Count confirmations met
        
        Returns:
            (confirmations_met, total_confirmations)
        """
        confirmations = self.validate_confirmations(trade_signal)
        met = sum(1 for v in confirmations.values() if v)
        total = len(confirmations)
        
        return met, total
    
    def get_trade_recommendation(self, trade_signal: Dict) -> Dict:
        """
        Get comprehensive trade recommendation based on handbook
        
        Returns:
            {
                'approved': bool,
                'violations': List[str],
                'confirmations': Dict,
                'confirmations_met': int,
                'confirmations_total': int,
                'confidence_adjustment': float,
                'recommendation': str
            }
        """
        approved, violations = self.check_trade_against_rules(trade_signal)
        confirmations = self.validate_confirmations(trade_signal)
        met, total = self.get_confirmation_count(trade_signal)
        
        # Adjust confidence based on confirmations
        base_confidence = trade_signal.get('confidence', 0.5)
        confirmation_ratio = met / total if total > 0 else 0
        
        # Confidence adjustment
        if confirmation_ratio >= 0.8:  # 80%+ confirmations
            confidence_adjustment = 1.2
        elif confirmation_ratio >= 0.6:  # 60-80% confirmations
            confidence_adjustment = 1.0
        elif confirmation_ratio >= 0.4:  # 40-60% confirmations
            confidence_adjustment = 0.8
        else:  # <40% confirmations
            confidence_adjustment = 0.5
        
        adjusted_confidence = min(1.0, base_confidence * confidence_adjustment)
        
        # Generate recommendation
        if not approved:
            recommendation = f"REJECT - {len(violations)} handbook violations"
        elif met < 5:
            recommendation = f"CAUTION - Only {met}/{total} confirmations met"
        elif met >= 7:
            recommendation = f"APPROVED - Strong setup ({met}/{total} confirmations)"
        else:
            recommendation = f"APPROVED - Adequate setup ({met}/{total} confirmations)"
        
        return {
            'approved': approved,
            'violations': violations,
            'confirmations': confirmations,
            'confirmations_met': met,
            'confirmations_total': total,
            'base_confidence': base_confidence,
            'confidence_adjustment': confidence_adjustment,
            'adjusted_confidence': adjusted_confidence,
            'recommendation': recommendation
        }
    
    def print_trade_analysis(self, trade_signal: Dict):
        """Print detailed trade analysis against handbook"""
        print("\n" + "="*70)
        print("📚 TRADING HANDBOOK ANALYSIS")
        print("="*70)
        
        result = self.get_trade_recommendation(trade_signal)
        
        print(f"\n🎯 SYMBOL: {trade_signal.get('symbol', 'N/A')}")
        print(f"📊 STRATEGY: {trade_signal.get('strategy', 'N/A')}")
        print(f"📈 PATTERN: {trade_signal.get('pattern', 'None')}")
        print(f"🌍 REGIME: {trade_signal.get('market_regime', 'UNKNOWN')}")
        
        print(f"\n✅ CONFIRMATIONS: {result['confirmations_met']}/{result['confirmations_total']}")
        for check, passed in result['confirmations'].items():
            status = "✅" if passed else "❌"
            print(f"   {status} {check.replace('_', ' ').title()}")
        
        print(f"\n📊 CONFIDENCE:")
        print(f"   Base: {result['base_confidence']:.1%}")
        print(f"   Adjustment: {result['confidence_adjustment']:.2f}x")
        print(f"   Final: {result['adjusted_confidence']:.1%}")
        
        if result['violations']:
            print(f"\n⚠️  VIOLATIONS ({len(result['violations'])}):")
            for v in result['violations']:
                print(f"   ❌ {v}")
        
        print(f"\n🎯 RECOMMENDATION: {result['recommendation']}")
        
        if result['approved']:
            print("\n✅ TRADE APPROVED BY HANDBOOK")
        else:
            print("\n❌ TRADE REJECTED BY HANDBOOK")
        
        print("="*70 + "\n")
        
        return result


# Example usage
if __name__ == "__main__":
    # Initialize handbook
    handbook = TradingHandbook()
    
    # Example trade signal (simulated)
    trade_signal = {
        'symbol': 'BTCUSDT',
        'action': 'LONG',
        'strategy': 'momentum',
        'pattern': 'bullish_engulfing',
        'confidence': 0.75,
        'risk_amount': 200,
        'account_balance': 10000,
        'entry_price': 42000,
        'stop_loss': 41160,  # 2% stop
        'take_profit': 43680,  # 4% TP (2:1 R/R)
        'volume_confirmed': True,
        'trend_confirmed': True,
        'at_key_level': True,
        'rsi_confirmed': True,
        'market_regime': 'TRENDING',
        'vix': 18
    }
    
    # Analyze trade
    print("\\n🧪 TESTING HANDBOOK VALIDATION\\n")
    result = handbook.print_trade_analysis(trade_signal)
    
    # Test with violations
    print("\\n" + "="*70)
    print("🧪 TESTING WITH VIOLATIONS")
    print("="*70 + "\\n")
    
    bad_signal = trade_signal.copy()
    bad_signal['risk_amount'] = 500  # 5% risk (violates 2% rule)
    bad_signal['volume_confirmed'] = False
    bad_signal['market_regime'] = 'HIGH_VOLATILITY'
    bad_signal['vix'] = 45
    
    result = handbook.print_trade_analysis(bad_signal)
    
    print("\\n✅ Handbook validation system working!")
