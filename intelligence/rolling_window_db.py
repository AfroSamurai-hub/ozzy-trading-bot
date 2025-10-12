"""Rolling window vector database for recent trading patterns.

Updated for ChromaDB >= 0.4 using the PersistentClient API and enriched with
risk-aware metadata handling.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import chromadb
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class PatternEmbedding:
    """Lightweight container for vector DB entries."""

    id: str
    embedding: List[float]
    metadata: Dict


class RollingWindowPatternDB:
    """Time-bounded pattern storage backed by ChromaDB."""

    def __init__(
        self,
        persist_directory: str = "data/vector_db",
        window_hours: int = 48,
    ) -> None:
        self.persist_directory = persist_directory
        self.window_hours = window_hours
        self.max_age_seconds = window_hours * 3600

        self._client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self._client.get_or_create_collection(
            name="trading_patterns",
            metadata={"description": "Rolling trading patterns for similarity search"},
        )

        logger.info(
            "🔄 Rolling window DB ready | path=%s | window=%sh | existing=%s",
            persist_directory,
            window_hours,
            self.collection.count(),
        )

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------
    def add_pattern(self, pattern: PatternEmbedding, prune: bool = True) -> None:
        """Add a pattern and optionally enforce time-based pruning."""

        self.collection.add(
            ids=[pattern.id],
            embeddings=[pattern.embedding],
            metadatas=[pattern.metadata],
        )

        if prune:
            self._prune_old_patterns()

    def load_from_csv(
        self,
        csv_path: str,
        clear_existing: bool = False,
        apply_pruning: bool = True,
    ) -> int:
        """Bulk load patterns from a CSV file (used for bootstrap data)."""

        df = pd.read_csv(csv_path)
        if df.empty:
            return 0

        if clear_existing:
            self.clear()

        loaded = 0
        for idx, row in df.iterrows():
            embedding = [
                float(row.get("rsi", 50.0)) / 100.0,
                float(row.get("ema_ratio", 1.0)),
                float(row.get("volume_change", 0.0)),
                float(row.get("price_change", 0.0)),
            ]

            metadata = {
                "timestamp": pd.to_datetime(row["timestamp"]).timestamp(),
                "label": row.get("label", "UNKNOWN"),
                "symbol": row.get("symbol", "BTCUSDT"),
                "rsi": float(row.get("rsi", 50.0)),
                "ema_ratio": float(row.get("ema_ratio", 1.0)),
                "price_change": float(row.get("price_change", 0.0)),
                "volume_change": float(row.get("volume_change", 0.0)),
                # Intrawindow risk tracking metadata (safe-coerced)
                "future_high": _safe_float(row.get("future_high")),
                "future_low": _safe_float(row.get("future_low")),
                "price_change_forward_close": _safe_float(row.get("price_change_forward_close")),
                "price_change_forward": _safe_float(row.get("price_change_forward")),
                "price_change_forward_low": _safe_float(row.get("price_change_forward_low")),
                "max_profit_pct": _safe_float(row.get("max_profit_pct")),
                "max_drawdown_pct": _safe_float(row.get("max_drawdown_pct")),
                "hit_takeprofit": bool(row.get("hit_takeprofit", False)),
                "hit_stoploss": bool(row.get("hit_stoploss", False)),
            }
            metadata = {k: v for k, v in metadata.items() if v is not None}

            self.add_pattern(
                PatternEmbedding(
                    id=f"bootstrap_{idx}",
                    embedding=embedding,
                    metadata=metadata,
                ),
                prune=False,
            )
            loaded += 1

        if apply_pruning:
            self._prune_old_patterns()

        return loaded

    def query(self, embedding: List[float], k: int = 5) -> Dict:
        """Low-level query API mirroring Chroma's response."""

        if self.count() == 0:
            return {"ids": [[]], "metadatas": [[]], "distances": [[]]}
        return self.collection.query(query_embeddings=[embedding], n_results=k)

    def find_similar(self, current_state: Dict[str, float], k: int = 5) -> List[Dict]:
        """High-level helper returning metadata + similarity."""

        embedding = [
            float(current_state.get("rsi", 50.0)) / 100.0,
            float(current_state.get("ema_ratio", 1.0)),
            float(current_state.get("volume_change", 0.0)),
            float(current_state.get("price_change", 0.0)),
        ]

        results = self.collection.query(query_embeddings=[embedding], n_results=k)
        metadatas = results.get("metadatas", [[]])[0] or []
        distances = results.get("distances", [[]])[0] or []

        formatted: List[Dict] = []
        for meta, distance in zip(metadatas, distances):
            similarity = 1 - distance if distance is not None else None
            formatted.append({"metadata": meta, "similarity": similarity})

        return formatted

    def count(self) -> int:
        return self.collection.count()

    def get_stats(self) -> Dict[str, Optional[float]]:
        total_patterns = self.collection.count()
        sample_limit = min(1000, total_patterns)
        data = self.collection.get(limit=sample_limit)
        metadatas = data.get("metadatas", []) or []
        wins = sum(1 for m in metadatas if m.get("label") == "WIN")
        losses = sum(1 for m in metadatas if m.get("label") == "LOSS")
        neutrals = sum(1 for m in metadatas if m.get("label") == "NEUTRAL")
        sample_size = len(metadatas)

        # Calculate average intrawindow metrics (values stored as fractions)
        max_profits = [m.get("max_profit_pct") for m in metadatas if m.get("max_profit_pct") is not None]
        max_drawdowns = [m.get("max_drawdown_pct") for m in metadatas if m.get("max_drawdown_pct") is not None]

        return {
            "window_hours": self.window_hours,
            "max_age_seconds": self.max_age_seconds,
            "sample_size": sample_size,
            "win_rate": (wins / sample_size * 100) if sample_size else None,
            "loss_rate": (losses / sample_size * 100) if sample_size else None,
            "neutral_rate": (neutrals / sample_size * 100) if sample_size else None,
            "avg_max_profit_pct": (sum(max_profits) / len(max_profits) * 100) if max_profits else None,
            "avg_max_drawdown_pct": (sum(max_drawdowns) / len(max_drawdowns) * 100) if max_drawdowns else None,
            "total_patterns": total_patterns,
        }

    def clear(self) -> None:
        """Remove all patterns from the collection."""

        try:
            self._client.delete_collection(name="trading_patterns")
        except Exception:
            logger.warning("Collection deletion failed; creating fresh one")
        finally:
            self.collection = self._client.get_or_create_collection(
                name="trading_patterns",
                metadata={"description": "Rolling trading patterns for similarity search"},
            )
            logger.info("🧹 Cleared rolling window collection")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _prune_old_patterns(self) -> int:
        cutoff = time.time() - self.max_age_seconds
        data = self.collection.get()
        metadatas = data.get("metadatas", []) or []
        ids = data.get("ids", []) or []

        to_delete: List[str] = []
        for idx, metadata in enumerate(metadatas):
            ts = metadata.get("timestamp") if isinstance(metadata, dict) else None
            if ts is not None and ts < cutoff:
                to_delete.append(ids[idx])

        if to_delete:
            self.collection.delete(ids=to_delete)
            logger.debug("🗑️ Pruned %s stale patterns", len(to_delete))

        return len(to_delete)


def _safe_float(value) -> Optional[float]:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    logging.basicConfig(level=logging.INFO)
    db = RollingWindowPatternDB()
    stats = db.get_stats()
    logger.info("📊 Rolling DB stats: %s", stats)
    sample = db.find_similar({}, k=3)
    logger.info("🔍 Sample query count: %s", len(sample))
