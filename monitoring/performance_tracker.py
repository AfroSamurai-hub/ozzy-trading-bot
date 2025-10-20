"""
Performance Tracker - Monitor system performance metrics

Tracks:
- Decision latency (time to make AI trading decisions)
- Query speed (ChromaDB pattern queries)
- Memory usage (resident memory)
- Win rate trends
- AI confidence distribution
- Confirmation check pass rates

Usage:
    tracker = PerformanceTracker()
    
    # Track decision latency
    with tracker.track_decision():
        result = make_trading_decision()
    
    # Track query speed
    with tracker.track_query():
        patterns = query_chromadb()
    
    # Get statistics
    stats = tracker.get_statistics()
    print(f"Avg decision latency: {stats['decision_latency']['avg_ms']:.2f}ms")
"""

import time
import json
import psutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from contextlib import contextmanager
from collections import defaultdict
import statistics


class PerformanceTracker:
    """Track and analyze system performance metrics"""
    
    def __init__(self, save_to_file: bool = True, metrics_file: str = "monitoring/metrics.json"):
        """
        Initialize performance tracker
        
        Args:
            save_to_file: Whether to persist metrics to disk
            metrics_file: Path to metrics file
        """
        self.save_to_file = save_to_file
        self.metrics_file = Path(metrics_file)
        
        # Metric storage
        self.decision_latencies: List[float] = []  # milliseconds
        self.query_times: List[float] = []  # milliseconds
        self.memory_samples: List[float] = []  # MB
        self.win_rates: List[float] = []  # percentage
        self.confidence_values: List[float] = []  # 0.0-1.0
        self.confirmation_checks: Dict[str, List[bool]] = defaultdict(list)
        
        # Session tracking
        self.session_start = datetime.now()
        self.total_decisions = 0
        self.total_queries = 0
        
        # Thresholds for alerts
        self.thresholds = {
            'decision_latency_ms': 1000,  # 1 second
            'query_time_ms': 100,  # 100 milliseconds
            'memory_mb': 500,  # 500 MB
        }
        
        # Load previous metrics if file exists
        if self.save_to_file and self.metrics_file.exists():
            self._load_metrics()
    
    @contextmanager
    def track_decision(self):
        """Context manager to track decision latency"""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.decision_latencies.append(elapsed_ms)
            self.total_decisions += 1
            
            # Alert if threshold exceeded
            if elapsed_ms > self.thresholds['decision_latency_ms']:
                print(f"⚠️ SLOW DECISION: {elapsed_ms:.2f}ms (threshold: {self.thresholds['decision_latency_ms']}ms)")
            
            # Save metrics periodically
            if self.total_decisions % 10 == 0 and self.save_to_file:
                self._save_metrics()
    
    @contextmanager
    def track_query(self):
        """Context manager to track query speed"""
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self.query_times.append(elapsed_ms)
            self.total_queries += 1
            
            # Alert if threshold exceeded
            if elapsed_ms > self.thresholds['query_time_ms']:
                print(f"⚠️ SLOW QUERY: {elapsed_ms:.2f}ms (threshold: {self.thresholds['query_time_ms']}ms)")
    
    def record_memory_usage(self):
        """Record current memory usage"""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        self.memory_samples.append(memory_mb)
        
        # Alert if threshold exceeded
        if memory_mb > self.thresholds['memory_mb']:
            print(f"⚠️ HIGH MEMORY: {memory_mb:.2f}MB (threshold: {self.thresholds['memory_mb']}MB)")
        
        return memory_mb
    
    def record_win_rate(self, win_rate: float):
        """Record win rate for trend analysis"""
        self.win_rates.append(win_rate)
    
    def record_confidence(self, confidence: float):
        """Record AI confidence value"""
        self.confidence_values.append(confidence)
    
    def record_confirmation_check(self, check_name: str, passed: bool):
        """Record confirmation check result"""
        self.confirmation_checks[check_name].append(passed)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics"""
        stats = {
            'session_start': self.session_start.isoformat(),
            'session_duration_minutes': (datetime.now() - self.session_start).total_seconds() / 60,
            'total_decisions': self.total_decisions,
            'total_queries': self.total_queries,
        }
        
        # Decision latency stats
        if self.decision_latencies:
            stats['decision_latency'] = {
                'avg_ms': statistics.mean(self.decision_latencies),
                'median_ms': statistics.median(self.decision_latencies),
                'p50_ms': self._percentile(self.decision_latencies, 50),
                'p95_ms': self._percentile(self.decision_latencies, 95),
                'p99_ms': self._percentile(self.decision_latencies, 99),
                'min_ms': min(self.decision_latencies),
                'max_ms': max(self.decision_latencies),
                'samples': len(self.decision_latencies),
                'threshold_ms': self.thresholds['decision_latency_ms'],
                'threshold_violations': sum(1 for x in self.decision_latencies if x > self.thresholds['decision_latency_ms']),
            }
        
        # Query speed stats
        if self.query_times:
            stats['query_speed'] = {
                'avg_ms': statistics.mean(self.query_times),
                'median_ms': statistics.median(self.query_times),
                'p95_ms': self._percentile(self.query_times, 95),
                'min_ms': min(self.query_times),
                'max_ms': max(self.query_times),
                'samples': len(self.query_times),
                'threshold_ms': self.thresholds['query_time_ms'],
                'threshold_violations': sum(1 for x in self.query_times if x > self.thresholds['query_time_ms']),
            }
        
        # Memory usage stats
        if self.memory_samples:
            stats['memory_usage'] = {
                'avg_mb': statistics.mean(self.memory_samples),
                'current_mb': self.memory_samples[-1] if self.memory_samples else 0,
                'peak_mb': max(self.memory_samples),
                'samples': len(self.memory_samples),
                'threshold_mb': self.thresholds['memory_mb'],
                'threshold_violations': sum(1 for x in self.memory_samples if x > self.thresholds['memory_mb']),
            }
        
        # Win rate trend
        if self.win_rates:
            stats['win_rate_trend'] = {
                'current': self.win_rates[-1] if self.win_rates else 0,
                'avg': statistics.mean(self.win_rates),
                'min': min(self.win_rates),
                'max': max(self.win_rates),
                'samples': len(self.win_rates),
                'improving': len(self.win_rates) >= 2 and self.win_rates[-1] > self.win_rates[0],
            }
        
        # Confidence distribution
        if self.confidence_values:
            stats['confidence_distribution'] = {
                'avg': statistics.mean(self.confidence_values),
                'median': statistics.median(self.confidence_values),
                'min': min(self.confidence_values),
                'max': max(self.confidence_values),
                'samples': len(self.confidence_values),
                'distribution': self._confidence_distribution(),
            }
        
        # Confirmation check pass rates
        if self.confirmation_checks:
            stats['confirmation_checks'] = {}
            for check_name, results in self.confirmation_checks.items():
                pass_count = sum(results)
                total_count = len(results)
                stats['confirmation_checks'][check_name] = {
                    'pass_rate': (pass_count / total_count * 100) if total_count > 0 else 0,
                    'passed': pass_count,
                    'total': total_count,
                }
        
        return stats
    
    def get_summary(self) -> str:
        """Get human-readable performance summary"""
        stats = self.get_statistics()
        
        lines = [
            "=" * 80,
            "📊 PERFORMANCE SUMMARY",
            "=" * 80,
            f"Session Duration: {stats['session_duration_minutes']:.1f} minutes",
            f"Total Decisions: {stats['total_decisions']}",
            f"Total Queries: {stats['total_queries']}",
            "",
        ]
        
        # Decision latency
        if 'decision_latency' in stats:
            dl = stats['decision_latency']
            status = "✅" if dl['avg_ms'] < self.thresholds['decision_latency_ms'] else "⚠️"
            lines.extend([
                "🕐 DECISION LATENCY",
                f"  {status} Average: {dl['avg_ms']:.2f}ms (target: <{self.thresholds['decision_latency_ms']}ms)",
                f"  📊 P50: {dl['p50_ms']:.2f}ms | P95: {dl['p95_ms']:.2f}ms | P99: {dl['p99_ms']:.2f}ms",
                f"  📈 Range: {dl['min_ms']:.2f}ms - {dl['max_ms']:.2f}ms",
                f"  ⚠️  Threshold violations: {dl['threshold_violations']}/{dl['samples']}",
                "",
            ])
        
        # Query speed
        if 'query_speed' in stats:
            qs = stats['query_speed']
            status = "✅" if qs['avg_ms'] < self.thresholds['query_time_ms'] else "⚠️"
            lines.extend([
                "🔍 QUERY SPEED",
                f"  {status} Average: {qs['avg_ms']:.2f}ms (target: <{self.thresholds['query_time_ms']}ms)",
                f"  📊 P95: {qs['p95_ms']:.2f}ms",
                f"  📈 Range: {qs['min_ms']:.2f}ms - {qs['max_ms']:.2f}ms",
                f"  ⚠️  Threshold violations: {qs['threshold_violations']}/{qs['samples']}",
                "",
            ])
        
        # Memory usage
        if 'memory_usage' in stats:
            mem = stats['memory_usage']
            status = "✅" if mem['current_mb'] < self.thresholds['memory_mb'] else "⚠️"
            lines.extend([
                "💾 MEMORY USAGE",
                f"  {status} Current: {mem['current_mb']:.2f}MB (target: <{self.thresholds['memory_mb']}MB)",
                f"  📊 Average: {mem['avg_mb']:.2f}MB | Peak: {mem['peak_mb']:.2f}MB",
                f"  ⚠️  Threshold violations: {mem['threshold_violations']}/{mem['samples']}",
                "",
            ])
        
        # Win rate trend
        if 'win_rate_trend' in stats:
            wrt = stats['win_rate_trend']
            trend = "📈 Improving" if wrt['improving'] else "📉 Declining"
            lines.extend([
                "🎯 WIN RATE TREND",
                f"  {trend}",
                f"  📊 Current: {wrt['current']:.2f}% | Average: {wrt['avg']:.2f}%",
                f"  📈 Range: {wrt['min']:.2f}% - {wrt['max']:.2f}%",
                "",
            ])
        
        # Confidence distribution
        if 'confidence_distribution' in stats:
            cd = stats['confidence_distribution']
            lines.extend([
                "🎲 CONFIDENCE DISTRIBUTION",
                f"  📊 Average: {cd['avg']:.3f} | Median: {cd['median']:.3f}",
                f"  📈 Range: {cd['min']:.3f} - {cd['max']:.3f}",
                f"  📊 Distribution:",
            ])
            for bucket, pct in cd['distribution'].items():
                bars = "█" * int(pct / 2)
                lines.append(f"      {bucket}: {pct:5.1f}% {bars}")
            lines.append("")
        
        # Confirmation checks
        if 'confirmation_checks' in stats:
            lines.extend([
                "✅ CONFIRMATION CHECK PASS RATES",
            ])
            for check_name, check_stats in stats['confirmation_checks'].items():
                status = "✅" if check_stats['pass_rate'] >= 80 else "⚠️"
                lines.append(f"  {status} {check_name}: {check_stats['pass_rate']:.1f}% ({check_stats['passed']}/{check_stats['total']})")
            lines.append("")
        
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of data"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def _confidence_distribution(self) -> Dict[str, float]:
        """Calculate confidence distribution in buckets"""
        if not self.confidence_values:
            return {}
        
        buckets = {
            '0.0-0.5': 0,
            '0.5-0.6': 0,
            '0.6-0.7': 0,
            '0.7-0.8': 0,
            '0.8-0.9': 0,
            '0.9-1.0': 0,
        }
        
        for conf in self.confidence_values:
            if conf < 0.5:
                buckets['0.0-0.5'] += 1
            elif conf < 0.6:
                buckets['0.5-0.6'] += 1
            elif conf < 0.7:
                buckets['0.6-0.7'] += 1
            elif conf < 0.8:
                buckets['0.7-0.8'] += 1
            elif conf < 0.9:
                buckets['0.8-0.9'] += 1
            else:
                buckets['0.9-1.0'] += 1
        
        # Convert to percentages
        total = len(self.confidence_values)
        return {k: (v / total * 100) for k, v in buckets.items()}
    
    def _save_metrics(self):
        """Save metrics to disk"""
        try:
            # Ensure directory exists
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            
            metrics = {
                'session_start': self.session_start.isoformat(),
                'last_updated': datetime.now().isoformat(),
                'decision_latencies': self.decision_latencies[-1000:],  # Keep last 1000
                'query_times': self.query_times[-1000:],
                'memory_samples': self.memory_samples[-1000:],
                'win_rates': self.win_rates,
                'confidence_values': self.confidence_values[-1000:],
                'confirmation_checks': {k: v[-1000:] for k, v in self.confirmation_checks.items()},
                'statistics': self.get_statistics(),
            }
            
            with open(self.metrics_file, 'w') as f:
                json.dump(metrics, f, indent=2)
                
        except Exception as e:
            print(f"Warning: Failed to save metrics: {e}")
    
    def _load_metrics(self):
        """Load metrics from disk"""
        try:
            with open(self.metrics_file, 'r') as f:
                metrics = json.load(f)
            
            self.decision_latencies = metrics.get('decision_latencies', [])
            self.query_times = metrics.get('query_times', [])
            self.memory_samples = metrics.get('memory_samples', [])
            self.win_rates = metrics.get('win_rates', [])
            self.confidence_values = metrics.get('confidence_values', [])
            
            confirmation_checks = metrics.get('confirmation_checks', {})
            for check_name, results in confirmation_checks.items():
                self.confirmation_checks[check_name] = results
            
            print(f"✅ Loaded metrics from {self.metrics_file}")
            
        except Exception as e:
            print(f"Warning: Failed to load metrics: {e}")
    
    def reset(self):
        """Reset all metrics"""
        self.decision_latencies.clear()
        self.query_times.clear()
        self.memory_samples.clear()
        self.win_rates.clear()
        self.confidence_values.clear()
        self.confirmation_checks.clear()
        self.session_start = datetime.now()
        self.total_decisions = 0
        self.total_queries = 0


# Decorator functions for easy integration
def track_latency(tracker: PerformanceTracker):
    """Decorator to track function latency"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with tracker.track_decision():
                return func(*args, **kwargs)
        return wrapper
    return decorator


def track_query_time(tracker: PerformanceTracker):
    """Decorator to track query execution time"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with tracker.track_query():
                return func(*args, **kwargs)
        return wrapper
    return decorator
