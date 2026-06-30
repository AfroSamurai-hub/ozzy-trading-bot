"""
Rejection Tracker — Analyzes filter performance and auto-tunes thresholds

Tracks why signals get rejected, analyzes what would have happened if they
weren't rejected, and suggests/adjusts filter thresholds to maximize R-multiples.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from dataclasses import dataclass, asdict

# Path to persistent storage
REJECTION_DB_PATH = "/home/rick/ozzy-bot/rejection_tracker.json"
TUNING_LOG_PATH = "/home/rick/ozzy-bot/tuning_log.jsonl"


@dataclass
class FilterStats:
    """Statistics for a single filter type."""
    filter_name: str
    total_rejections: int = 0
    blocked_winners: int = 0  # Would have hit TP
    blocked_losers: int = 0   # Would have hit SL
    blocked_ambiguous: int = 0  # No clear outcome
    total_r_lost: float = 0.0  # Sum of R-multiples from blocked winners
    total_r_saved: float = 0.0  # Sum of R-multiples from blocked losers (positive = saved)
    avg_r_per_rejection: float = 0.0
    last_updated: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> FilterStats:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ThresholdSuggestion:
    """Suggestion for adjusting a filter threshold."""
    filter_name: str
    current_value: Any
    suggested_value: Any
    confidence: float  # 0.0 to 1.0
    reason: str
    expected_improvement_r: float
    sample_size: int


class RejectionTracker:
    """
    Tracks filter rejections and their outcomes to enable auto-tuning.

    Usage:
        tracker = RejectionTracker()
        tracker.record_rejection(filter_name="rsi_exhaustion", ...)
        tracker.analyze_outcomes()  # Backfill from signal_reviews.json
        suggestions = tracker.suggest_adjustments()
        tracker.apply_adjustment("rsi_exhaustion", new_value=80.0)
    """

    def __init__(self, db_path: str = REJECTION_DB_PATH):
        self.db_path = Path(db_path)
        self.data = self._load()
        self._ensure_structure()

    def _load(self) -> dict:
        """Load rejection database from disk."""
        if not self.db_path.exists():
            return {}
        try:
            return json.loads(self.db_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save(self) -> None:
        """Save rejection database to disk."""
        self.db_path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def _ensure_structure(self) -> None:
        """Ensure database has required structure."""
        if "filters" not in self.data:
            self.data["filters"] = {}
        if "adjustments" not in self.data:
            self.data["adjustments"] = []
        if "daily_stats" not in self.data:
            self.data["daily_stats"] = {}

    def record_rejection(
        self,
        filter_name: str,
        symbol: str,
        signal: str,
        entry: float,
        filter_value: Any = None,
        filter_reason: str = "",
        timestamp: str | None = None,
    ) -> str:
        """
        Record a new rejection event.

        Returns the rejection ID for later outcome tracking.
        """
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        rejection_id = f"{ts}:{filter_name}:{symbol}:{signal}:{entry}"

        rejection = {
            "id": rejection_id,
            "ts": ts,
            "filter_name": filter_name,
            "symbol": symbol,
            "signal": signal,
            "entry": entry,
            "filter_value": filter_value,
            "filter_reason": filter_reason,
            "outcome": None,  # To be filled later
            "r_multiple": None,
            "outcome_resolved_at": None,
        }

        # Store in daily bucket for efficient querying
        day_key = ts[:10]  # YYYY-MM-DD
        if day_key not in self.data["daily_stats"]:
            self.data["daily_stats"][day_key] = {"rejections": []}
        self.data["daily_stats"][day_key]["rejections"].append(rejection)

        self._save()
        return rejection_id

    def update_outcome(
        self,
        rejection_id: str,
        outcome: str,  # "win", "loss", "ambiguous"
        r_multiple: float | None = None,
    ) -> bool:
        """Update the outcome of a previously recorded rejection."""
        # Search through daily buckets
        for day_key, day_data in self.data.get("daily_stats", {}).items():
            for rej in day_data.get("rejections", []):
                if rej["id"] == rejection_id:
                    rej["outcome"] = outcome
                    rej["r_multiple"] = r_multiple
                    rej["outcome_resolved_at"] = datetime.now(timezone.utc).isoformat()
                    self._save()
                    return True
        return False

    def sync_from_signal_reviews(self, reviews_path: str = "/home/rick/ozzy-bot/signal_reviews.json") -> dict:
        """
        Sync outcomes from signal_reviews.json (populated by signal_review.py).

        This connects the rejection tracker to the existing signal review system.
        """
        reviews_file = Path(reviews_path)
        if not reviews_file.exists():
            return {"synced": 0, "error": "signal_reviews.json not found"}

        try:
            reviews_data = json.loads(reviews_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return {"synced": 0, "error": f"JSON decode error: {e}"}

        synced = 0
        for review in reviews_data.get("reviews", []):
            if review.get("decision") != "rejected":
                continue

            # Build rejection ID from review data
            ts = review.get("ts", "")
            filter_name = review.get("filter_name", "unknown")
            symbol = review.get("symbol", "")
            signal = review.get("signal", "")
            entry = review.get("entry", 0)

            rejection_id = f"{ts}:{filter_name}:{symbol}:{signal}:{entry}"

            # Update outcome if available
            outcome = review.get("outcome")  # "win", "loss", "tp", "sl"
            if outcome in ("tp", "win"):
                outcome = "win"
            elif outcome in ("sl", "loss"):
                outcome = "loss"
            elif review.get("outcome_status") == "ambiguous":
                outcome = "ambiguous"
            else:
                continue  # No outcome yet

            r_multiple = review.get("r_multiple")

            if self.update_outcome(rejection_id, outcome, r_multiple):
                synced += 1

        return {"synced": synced, "total_reviews": len(reviews_data.get("reviews", []))}

    def get_filter_stats(self, days: int = 7) -> dict[str, FilterStats]:
        """
        Calculate statistics for each filter over the last N days.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stats: dict[str, FilterStats] = {}

        for day_key, day_data in self.data.get("daily_stats", {}).items():
            day_ts = datetime.fromisoformat(f"{day_key}T00:00:00+00:00")
            if day_ts < cutoff:
                continue

            for rej in day_data.get("rejections", []):
                filter_name = rej.get("filter_name", "unknown")
                if filter_name not in stats:
                    stats[filter_name] = FilterStats(filter_name=filter_name)

                s = stats[filter_name]
                s.total_rejections += 1

                outcome = rej.get("outcome")
                r_multiple = rej.get("r_multiple") or 0.0

                if outcome == "win":
                    s.blocked_winners += 1
                    s.total_r_lost += r_multiple
                elif outcome == "loss":
                    s.blocked_losers += 1
                    s.total_r_saved += abs(r_multiple)
                elif outcome == "ambiguous":
                    s.blocked_ambiguous += 1

        # Calculate averages and update timestamps
        for s in stats.values():
            if s.total_rejections > 0:
                net_r = s.total_r_saved - s.total_r_lost
                s.avg_r_per_rejection = round(net_r / s.total_rejections, 4)
            s.last_updated = datetime.now(timezone.utc).isoformat()

        return stats

    def suggest_adjustments(
        self,
        min_sample_size: int = 10,
        r_threshold: float = 0.5,  # Minimum R improvement to suggest change
    ) -> list[ThresholdSuggestion]:
        """
        Analyze filter performance and suggest threshold adjustments.

        Returns list of suggestions sorted by expected improvement.
        """
        stats = self.get_filter_stats(days=7)
        suggestions = []

        for filter_name, s in stats.items():
            if s.total_rejections < min_sample_size:
                continue

            # Skip if we don't have enough outcome data
            resolved = s.blocked_winners + s.blocked_losers
            if resolved < min_sample_size * 0.5:  # At least 50% resolved
                continue

            # Calculate win rate of rejected signals
            if resolved > 0:
                rejected_win_rate = s.blocked_winners / resolved
            else:
                continue

            # If we're blocking more winners than losers, suggest loosening
            if rejected_win_rate > 0.6 and s.total_r_lost > s.total_r_saved:
                # High confidence we're being too strict
                confidence = min(0.9, rejected_win_rate)
                expected_improvement = s.total_r_lost - s.total_r_saved

                suggestion = ThresholdSuggestion(
                    filter_name=filter_name,
                    current_value=None,  # Will be filled from config
                    suggested_value="loosen",
                    confidence=confidence,
                    reason=f"Blocking {rejected_win_rate:.1%} winners vs losers. "
                           f"Net R lost: {s.total_r_lost - s.total_r_saved:.2f}",
                    expected_improvement_r=expected_improvement,
                    sample_size=s.total_rejections,
                )
                suggestions.append(suggestion)

            # If we're blocking mostly losers, suggest tightening (we're too loose)
            elif rejected_win_rate < 0.3 and s.total_r_saved > s.total_r_lost:
                confidence = min(0.9, 1 - rejected_win_rate)
                expected_improvement = s.total_r_saved - s.total_r_lost

                suggestion = ThresholdSuggestion(
                    filter_name=filter_name,
                    current_value=None,
                    suggested_value="tighten",
                    confidence=confidence,
                    reason=f"Blocking {rejected_win_rate:.1%} winners vs losers. "
                           f"Net R saved: {s.total_r_saved - s.total_r_lost:.2f}",
                    expected_improvement_r=expected_improvement,
                    sample_size=s.total_rejections,
                )
                suggestions.append(suggestion)

        # Sort by expected improvement
        suggestions.sort(key=lambda x: x.expected_improvement_r, reverse=True)
        return suggestions

    def generate_weekly_report(self) -> dict:
        """Generate a comprehensive weekly report for Telegram."""
        stats = self.get_filter_stats(days=7)
        suggestions = self.suggest_adjustments(min_sample_size=5)

        total_rejections = sum(s.total_rejections for s in stats.values())
        total_blocked_winners = sum(s.blocked_winners for s in stats.values())
        total_blocked_losers = sum(s.blocked_losers for s in stats.values())
        total_r_lost = sum(s.total_r_lost for s in stats.values())
        total_r_saved = sum(s.total_r_saved for s in stats.values())

        # Filter breakdown
        filter_breakdown = []
        for name, s in sorted(stats.items(), key=lambda x: x[1].total_rejections, reverse=True):
            filter_breakdown.append({
                "name": name,
                "rejections": s.total_rejections,
                "blocked_winners": s.blocked_winners,
                "blocked_losers": s.blocked_losers,
                "net_r": round(s.total_r_saved - s.total_r_lost, 2),
            })

        return {
            "period": "last_7_days",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_rejections": total_rejections,
                "blocked_winners": total_blocked_winners,
                "blocked_losers": total_blocked_losers,
                "net_r_impact": round(total_r_saved - total_r_lost, 2),
                "opportunity_cost_r": round(total_r_lost, 2),
                "risk_saved_r": round(total_r_saved, 2),
            },
            "filter_breakdown": filter_breakdown,
            "suggestions": [
                {
                    "filter": s.filter_name,
                    "suggested_action": s.suggested_value,
                    "confidence": round(s.confidence, 2),
                    "reason": s.reason,
                    "expected_improvement_r": round(s.expected_improvement_r, 2),
                    "sample_size": s.sample_size,
                }
                for s in suggestions[:5]  # Top 5 suggestions
            ],
        }

    def log_adjustment(self, filter_name: str, old_value: Any, new_value: Any, reason: str) -> None:
        """Log a threshold adjustment for audit trail."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "filter_name": filter_name,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason,
        }

        with open(TUNING_LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")

        # Also track in data structure
        self.data["adjustments"].append(entry)
        self._save()

    def apply_suggestions_to_config(self, min_confidence: float = 0.7) -> list[dict]:
        """
        Apply high-confidence threshold suggestions directly to config.DYNAMIC_THRESHOLDS.
        Returns list of applied changes for logging.
        """
        try:
            import config
        except ImportError:
            return []

        suggestions = self.suggest_adjustments(min_sample_size=5, r_threshold=0.5)
        applied = []

        delta_map = {
            "rsi_exhaustion": ("rsi_exhaustion", 2.0),
            "pullback_rsi_exhaustion": ("pullback_rsi_exhaustion", 2.0),
            "momentum_rsi_exhaustion": ("momentum_rsi_exhaustion", 2.0),
            "volume_confirmation": ("volume_confirmation", 0.05),
            "ema_overextension": ("ema_overextension", 0.5),
        }

        for sugg in suggestions:
            if sugg.confidence < min_confidence:
                continue
            fn = sugg.filter_name
            action = sugg.suggested_value
            if fn not in delta_map:
                continue

            key, delta = delta_map[fn]
            if key not in config.DYNAMIC_THRESHOLDS:
                continue

            old = dict(config.DYNAMIC_THRESHOLDS[key])
            if "buy_max" in config.DYNAMIC_THRESHOLDS[key] and "sell_min" in config.DYNAMIC_THRESHOLDS[key]:
                if action == "loosen":
                    config.DYNAMIC_THRESHOLDS[key]["buy_max"] = round(config.DYNAMIC_THRESHOLDS[key]["buy_max"] + delta, 2)
                    config.DYNAMIC_THRESHOLDS[key]["sell_min"] = round(config.DYNAMIC_THRESHOLDS[key]["sell_min"] - delta, 2)
                else:
                    config.DYNAMIC_THRESHOLDS[key]["buy_max"] = round(config.DYNAMIC_THRESHOLDS[key]["buy_max"] - delta, 2)
                    config.DYNAMIC_THRESHOLDS[key]["sell_min"] = round(config.DYNAMIC_THRESHOLDS[key]["sell_min"] + delta, 2)
            elif "min_ratio" in config.DYNAMIC_THRESHOLDS[key]:
                if action == "loosen":
                    config.DYNAMIC_THRESHOLDS[key]["min_ratio"] = round(config.DYNAMIC_THRESHOLDS[key]["min_ratio"] - delta, 2)
                else:
                    config.DYNAMIC_THRESHOLDS[key]["min_ratio"] = round(config.DYNAMIC_THRESHOLDS[key]["min_ratio"] + delta, 2)
            elif "max_distance_pct" in config.DYNAMIC_THRESHOLDS[key]:
                if action == "loosen":
                    config.DYNAMIC_THRESHOLDS[key]["max_distance_pct"] = round(config.DYNAMIC_THRESHOLDS[key]["max_distance_pct"] + delta, 2)
                else:
                    config.DYNAMIC_THRESHOLDS[key]["max_distance_pct"] = round(config.DYNAMIC_THRESHOLDS[key]["max_distance_pct"] - delta, 2)

            self.log_adjustment(fn, old, dict(config.DYNAMIC_THRESHOLDS[key]),
                                f"Auto-{action}: confidence={sugg.confidence:.2f}, {sugg.reason}")
            applied.append({
                "filter": fn,
                "action": action,
                "confidence": round(sugg.confidence, 2),
                "old": old,
                "new": dict(config.DYNAMIC_THRESHOLDS[key]),
            })

        return applied

    def get_current_thresholds(self) -> dict:
        """Get current filter thresholds from config."""
        # Import config dynamically to avoid circular imports
        try:
            from config import (
                RSI_BUY_MAX, RSI_SELL_MIN, VOLUME_MIN_RATIO,
                MIN_RR, MAX_POSITIONS, DAILY_DRAWDOWN_LIMIT,
            )
            return {
                "rsi_exhaustion": {"buy_max": RSI_BUY_MAX, "sell_min": RSI_SELL_MIN},
                "volume_confirmation": {"min_ratio": VOLUME_MIN_RATIO},
                "min_rr": MIN_RR,
                "max_positions": MAX_POSITIONS,
                "daily_drawdown_limit": DAILY_DRAWDOWN_LIMIT,
            }
        except ImportError:
            return {}


# Singleton instance for easy import
_tracker_instance: RejectionTracker | None = None


def get_tracker() -> RejectionTracker:
    """Get or create the singleton rejection tracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = RejectionTracker()
    return _tracker_instance


def record_rejection(*args, **kwargs) -> str:
    """Convenience function to record a rejection."""
    return get_tracker().record_rejection(*args, **kwargs)


def sync_outcomes() -> dict:
    """Convenience function to sync outcomes from signal_reviews.json."""
    return get_tracker().sync_from_signal_reviews()


def get_weekly_report() -> dict:
    """Convenience function to generate weekly report."""
    return get_tracker().generate_weekly_report()


def suggest_filter_adjustments() -> list:
    """Convenience function to get adjustment suggestions."""
    return get_tracker().suggest_adjustments()


if __name__ == "__main__":
    # CLI for testing
    import sys

    tracker = RejectionTracker()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "sync":
            result = tracker.sync_from_signal_reviews()
            print(json.dumps(result, indent=2))
        elif cmd == "report":
            report = tracker.generate_weekly_report()
            print(json.dumps(report, indent=2))
        elif cmd == "suggest":
            suggestions = tracker.suggest_adjustments()
            for s in suggestions:
                print(f"{s.filter_name}: {s.suggested_value} (confidence: {s.confidence:.2f})")
                print(f"  Reason: {s.reason}")
                print(f"  Expected improvement: {s.expected_improvement_r:.2f}R")
                print()
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python rejection_tracker.py [sync|report|suggest]")
    else:
        # Default: show stats
        stats = tracker.get_filter_stats(days=7)
        print("Filter Stats (last 7 days):")
        for name, s in stats.items():
            print(f"\n{name}:")
            print(f"  Rejections: {s.total_rejections}")
            print(f"  Blocked winners: {s.blocked_winners}")
            print(f"  Blocked losers: {s.blocked_losers}")
            print(f"  Net R per rejection: {s.avg_r_per_rejection:.4f}")
