#!/usr/bin/env python3
"""
🧠 MASTER PLANNER - ENVIRONMENT AWARENESS MODULE

This module gives the Master Planner "eyes" to see the codebase!

Features:
1. **Environment Scanning**: Knows what files exist, what's built
2. **Dependency Tracking**: Knows what depends on what
3. **Quality Gates**: Catches bugs like "unknown_pattern" before they ship
4. **Nested Domains**: Organizes knowledge by system area

USAGE:
    from planner_environment import EnvironmentScanner
    
    scanner = EnvironmentScanner()
    health = scanner.check_health()
    scanner.generate_report()
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Set, Optional
from datetime import datetime
import subprocess


class Domain:
    """
    Represents a nested domain of the system.
    
    Examples:
    - Learning System (outcome tracker, analyzers, learning engine)
    - Trading System (agent, safety, portfolio)
    - Intelligence (pattern library, confidence calculator)
    """
    
    def __init__(self, name: str, description: str, critical: bool = False):
        self.name = name
        self.description = description
        self.critical = critical  # If True, system can't run without it
        self.sub_domains: List[Domain] = []
        self.required_files: Set[Path] = set()
        self.required_data: Set[Path] = set()
        self.quality_gates: List[Dict] = []
        self.dependencies: Set[str] = set()  # Other domains this depends on
    
    def add_sub_domain(self, domain: 'Domain'):
        """Add a nested sub-domain"""
        self.sub_domains.append(domain)
    
    def add_required_file(self, path: Path):
        """Mark a file as required for this domain"""
        self.required_files.add(path)
    
    def add_quality_gate(self, name: str, check_func, error_message: str):
        """Add a quality check that must pass"""
        self.quality_gates.append({
            'name': name,
            'check': check_func,
            'error_message': error_message
        })
    
    def check_health(self, base_path: Path) -> Dict:
        """Check if this domain is healthy"""
        issues = []
        
        # Check required files exist
        for file_path in self.required_files:
            full_path = base_path / file_path
            if not full_path.exists():
                issues.append(f"Missing required file: {file_path}")
        
        # Run quality gates
        for gate in self.quality_gates:
            try:
                if not gate['check'](base_path):
                    issues.append(f"Quality gate failed: {gate['name']} - {gate['error_message']}")
            except Exception as e:
                issues.append(f"Quality gate error: {gate['name']} - {str(e)}")
        
        # Check sub-domains
        sub_domain_health = {}
        for sub_domain in self.sub_domains:
            sub_health = sub_domain.check_health(base_path)
            sub_domain_health[sub_domain.name] = sub_health
            if sub_health['issues']:
                issues.extend([f"{sub_domain.name}: {issue}" for issue in sub_health['issues']])
        
        return {
            'domain': self.name,
            'healthy': len(issues) == 0,
            'critical': self.critical,
            'issues': issues,
            'sub_domains': sub_domain_health
        }


class EnvironmentScanner:
    """
    Scans the codebase and gives Master Planner awareness of what's built.
    """
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path.cwd()
        self.domains: Dict[str, Domain] = {}
        self._build_domain_map()
    
    def _build_domain_map(self):
        """Build the nested domain structure"""
        
        # Domain 1: Learning System (Milestone 1.2.5)
        learning = Domain(
            "Learning System",
            "Tracks outcomes, analyzes performance, auto-updates confidence",
            critical=False  # Not critical for basic trading, but critical for improvement
        )
        
        # Sub-domain: Outcome Tracking
        outcome_tracking = Domain("Outcome Tracking", "Captures and labels trade outcomes")
        outcome_tracking.add_required_file(Path("scripts/track_trade_outcomes.py"))
        outcome_tracking.add_required_file(Path("data/trade_labels"))
        outcome_tracking.add_quality_gate(
            "ChromaDB Available",
            lambda p: (p / "data/trade_labels").exists(),
            "ChromaDB storage directory missing"
        )
        outcome_tracking.add_quality_gate(
            "No Unknown Pattern Learning",
            self._check_no_unknown_pattern_learning,
            "System is learning from 'unknown_pattern' - this is a bug!"
        )
        learning.add_sub_domain(outcome_tracking)
        
        # Sub-domain: Pattern Analysis
        pattern_analysis = Domain("Pattern Analysis", "Analyzes pattern performance")
        pattern_analysis.add_required_file(Path("scripts/analyze_pattern_performance.py"))
        pattern_analysis.add_quality_gate(
            "Unknown Pattern Excluded",
            lambda p: self._check_file_contains(
                p / "scripts/analyze_pattern_performance.py",
                "if pattern in ['unknown_pattern', 'indicator_based']:"
            ),
            "Pattern analyzer doesn't exclude unknown_pattern and indicator_based"
        )
        learning.add_sub_domain(pattern_analysis)
        
        # Sub-domain: Learning Engine
        learning_engine = Domain("Learning Engine", "Auto-updates confidence multipliers")
        learning_engine.add_required_file(Path("scripts/learning_engine.py"))
        learning_engine.add_required_file(Path("data/learning_multipliers.json"))
        learning_engine.add_quality_gate(
            "Unknown Pattern Skipped",
            lambda p: self._check_file_contains(
                p / "scripts/learning_engine.py",
                "if pattern in ['unknown_pattern', 'indicator_based']:"
            ),
            "Learning engine doesn't skip unknown_pattern and indicator_based"
        )
        learning.add_sub_domain(learning_engine)
        
        self.domains["learning"] = learning
        
        # Domain 2: Trading System
        trading = Domain(
            "Trading System",
            "Makes trading decisions and executes trades",
            critical=True
        )
        
        # Sub-domain: Agent
        agent = Domain("Trading Agent", "AI decision maker")
        agent.add_required_file(Path("agent/trader.py"))
        agent.add_quality_gate(
            "Learning Multipliers Integrated",
            lambda p: self._check_file_contains(
                p / "agent/trader.py",
                "_load_learning_multipliers"
            ),
            "TradingAgent doesn't load learning multipliers"
        )
        agent.dependencies.add("learning")  # Depends on learning system
        trading.add_sub_domain(agent)
        
        # Sub-domain: Safety Rails
        safety = Domain("Safety Rails", "Prevents dangerous trades")
        safety.add_required_file(Path("agent/safety.py"))
        trading.add_sub_domain(safety)
        
        # Sub-domain: Portfolio
        portfolio = Domain("Portfolio Management", "Tracks positions and capital")
        portfolio.add_required_file(Path("agent/portfolio.py"))
        trading.add_sub_domain(portfolio)
        
        self.domains["trading"] = trading
        
        # Domain 3: Intelligence System
        intelligence = Domain(
            "Intelligence System",
            "Pattern recognition and market analysis",
            critical=True
        )
        
        intelligence.add_required_file(Path("intelligence/pattern_intelligence.py"))
        intelligence.add_required_file(Path("intelligence/pattern_library.py"))
        
        self.domains["intelligence"] = intelligence
    
    def _check_file_contains(self, file_path: Path, text: str) -> bool:
        """Check if a file contains specific text"""
        if not file_path.exists():
            return False
        try:
            content = file_path.read_text()
            return text in content
        except:
            return False
    
    def _check_no_unknown_pattern_learning(self, base_path: Path) -> bool:
        """
        CRITICAL: Ensure we're not learning from unknown_pattern or indicator_based
        
        Checks:
        1. learning_engine.py skips both unknown_pattern and indicator_based
        2. analyze_pattern_performance.py excludes both
        3. No unknown_pattern in active multipliers
        """
        # Check 1: Learning engine skips both
        learning_engine = base_path / "scripts/learning_engine.py"
        if not self._check_file_contains(learning_engine, "if pattern in ['unknown_pattern', 'indicator_based']:"):
            return False
        
        # Check 2: Pattern analyzer excludes both
        analyzer = base_path / "scripts/analyze_pattern_performance.py"
        if not self._check_file_contains(analyzer, "if pattern in ['unknown_pattern', 'indicator_based']:"):
            return False
        
        # Check 3: No unknown_pattern in multipliers
        multipliers_file = base_path / "data/learning_multipliers.json"
        if multipliers_file.exists():
            try:
                with open(multipliers_file) as f:
                    multipliers = json.load(f)
                if 'unknown_pattern' in multipliers:
                    return False
            except:
                pass
        
        return True
    
    def check_health(self) -> Dict:
        """Check health of all domains"""
        results = {}
        critical_issues = []
        warnings = []
        
        for domain_name, domain in self.domains.items():
            health = domain.check_health(self.base_path)
            results[domain_name] = health
            
            if not health['healthy']:
                if domain.critical:
                    critical_issues.extend(health['issues'])
                else:
                    warnings.extend(health['issues'])
        
        return {
            'timestamp': datetime.now().isoformat(),
            'overall_healthy': len(critical_issues) == 0,
            'critical_issues': critical_issues,
            'warnings': warnings,
            'domains': results
        }
    
    def generate_report(self) -> str:
        """Generate human-readable health report"""
        health = self.check_health()
        
        report = []
        report.append("="*70)
        report.append("🧠 MASTER PLANNER - ENVIRONMENT HEALTH REPORT")
        report.append(f"Generated: {health['timestamp']}")
        report.append("="*70)
        
        # Overall status
        if health['overall_healthy']:
            report.append("\n✅ OVERALL STATUS: HEALTHY")
        else:
            report.append("\n🔥 OVERALL STATUS: CRITICAL ISSUES DETECTED")
        
        # Critical issues
        if health['critical_issues']:
            report.append(f"\n🔥 CRITICAL ISSUES ({len(health['critical_issues'])}):")
            report.append("-"*70)
            for issue in health['critical_issues']:
                report.append(f"  ❌ {issue}")
        
        # Warnings
        if health['warnings']:
            report.append(f"\n⚠️  WARNINGS ({len(health['warnings'])}):")
            report.append("-"*70)
            for warning in health['warnings']:
                report.append(f"  ⚠️  {warning}")
        
        # Domain details
        report.append(f"\n📊 DOMAIN HEALTH:")
        report.append("-"*70)
        for domain_name, domain_health in health['domains'].items():
            status = "✅" if domain_health['healthy'] else "❌"
            critical = " (CRITICAL)" if domain_health['critical'] else ""
            report.append(f"{status} {domain_health['domain']}{critical}")
            
            # Sub-domains
            if domain_health['sub_domains']:
                for sub_name, sub_health in domain_health['sub_domains'].items():
                    sub_status = "✅" if sub_health['healthy'] else "❌"
                    report.append(f"  {sub_status} {sub_health['domain']}")
                    
                    if not sub_health['healthy']:
                        for issue in sub_health['issues']:
                            report.append(f"      - {issue}")
        
        report.append("\n" + "="*70)
        
        if health['overall_healthy']:
            report.append("🎉 System is healthy and ready to trade!")
        else:
            report.append("⚠️  Fix critical issues before proceeding!")
        
        report.append("="*70)
        
        return "\n".join(report)
    
    def get_unknown_pattern_stats(self) -> Dict:
        """
        Specific check: How many unknown_pattern trades do we have?
        This helps answer: "How do we AVOID unknown patterns?"
        """
        try:
            import chromadb
            from chromadb.config import Settings
            
            client = chromadb.PersistentClient(
                path=str(self.base_path / "data/trade_labels"),
                settings=Settings(anonymized_telemetry=False)
            )
            db = client.get_collection(name="trade_outcomes")
            
            results = db.get(include=['metadatas'])
            total = len(results['metadatas'])
            
            unknown_count = sum(1 for m in results['metadatas'] if m.get('pattern') == 'unknown_pattern')
            known_count = total - unknown_count
            
            # Get list of known patterns
            known_patterns = set()
            for m in results['metadatas']:
                pattern = m.get('pattern')
                if pattern and pattern != 'unknown_pattern':
                    known_patterns.add(pattern)
            
            return {
                'total_trades': total,
                'unknown_count': unknown_count,
                'known_count': known_count,
                'unknown_percentage': (unknown_count / total * 100) if total > 0 else 0,
                'known_patterns': list(known_patterns),
                'recommendation': self._get_unknown_pattern_recommendation(unknown_count, total)
            }
        except Exception as e:
            return {
                'error': str(e),
                'recommendation': "Install ChromaDB or check data directory"
            }
    
    def _get_unknown_pattern_recommendation(self, unknown_count: int, total: int) -> str:
        """Recommend actions based on unknown_pattern ratio"""
        if total == 0:
            return "No trades yet - start paper trading"
        
        ratio = unknown_count / total
        
        if ratio == 0:
            return "✅ Perfect! All patterns identified correctly"
        elif ratio < 0.2:
            return "✅ Good! <20% unknown is acceptable"
        elif ratio < 0.5:
            return "⚠️  Moderate: Consider improving pattern detection in AI prompt"
        else:
            return "🔥 HIGH: >50% unknown - URGENT: Improve pattern extraction or AI prompt"


def main():
    """Run environment health check"""
    scanner = EnvironmentScanner()
    
    # Generate report
    print(scanner.generate_report())
    
    # Unknown pattern stats
    print("\n" + "="*70)
    print("📊 UNKNOWN PATTERN ANALYSIS")
    print("="*70)
    
    stats = scanner.get_unknown_pattern_stats()
    
    if 'error' in stats:
        print(f"❌ Error: {stats['error']}")
    else:
        print(f"Total Trades: {stats['total_trades']}")
        print(f"Unknown: {stats['unknown_count']} ({stats['unknown_percentage']:.1f}%)")
        print(f"Known: {stats['known_count']}")
        print(f"Known Patterns: {', '.join(stats['known_patterns']) if stats['known_patterns'] else 'None'}")
        print(f"\n{stats['recommendation']}")


if __name__ == '__main__':
    main()
