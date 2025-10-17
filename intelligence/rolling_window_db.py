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

from agent.utils import safe_float

logger = logging.getLogger(__name__)

# --- Auto-Flush Configuration ---
MAX_PATTERNS = 10000  # Maximum database capacity
FLUSH_THRESHOLD = 0.80  # Flush when 80% full
FLUSH_PERCENTAGE = 0.20  # Remove 20% when flushing


@dataclass
class PatternEmbedding:
    """Lightweight container for vector DB entries."""

    id: str
    embedding: List[float]
    metadata: Dict


class RollingWindowPatternDB:
    """Capacity-bounded pattern storage with auto-flushing."""

    def __init__(
        self,
        persist_directory: str = "data/vector_db",
    ) -> None:
        self.persist_directory = persist_directory

        self._client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self._client.get_or_create_collection(
            name="trading_patterns",
            metadata={"description": "Rolling trading patterns for similarity search"},
        )

        logger.info(
            "🔄 Rolling window DB ready | path=%s | capacity=%s | existing=%s",
            persist_directory,
            MAX_PATTERNS,
            self.collection.count(),
        )

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------
    def add_pattern(self, pattern: PatternEmbedding) -> None:
        """Add a pattern and trigger auto-flush if capacity threshold is met."""

        self.collection.add(
            ids=[pattern.id],
            embeddings=[pattern.embedding],
            metadatas=[pattern.metadata],
        )

        current_count = self.collection.count()
        capacity_percent = current_count / MAX_PATTERNS

        logger.info(
            "Pattern added: %s/%s (%.1f%%)",
            current_count,
            MAX_PATTERNS,
            capacity_percent * 100,
        )

        if capacity_percent >= FLUSH_THRESHOLD:
            self._auto_flush()

    def load_from_csv(
        self,
        csv_path: str,
        clear_existing: bool = False,
        apply_pruning: bool = False,
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
                safe_float(row.get("rsi", 50.0), 50.0) / 100.0,
                safe_float(row.get("ema_ratio", 1.0), 1.0),
                safe_float(row.get("volume_change", 0.0), 0.0),
                safe_float(row.get("price_change", 0.0), 0.0),
            ]

            metadata = {
                "timestamp": pd.to_datetime(row["timestamp"]).timestamp(),
                "label": row.get("label", "UNKNOWN"),
                "symbol": row.get("symbol", "BTCUSDT"),
                "rsi": safe_float(row.get("rsi", 50.0), 50.0),
                "ema_ratio": safe_float(row.get("ema_ratio", 1.0), 1.0),
                "price_change": safe_float(row.get("price_change", 0.0), 0.0),
                "volume_change": safe_float(row.get("volume_change", 0.0), 0.0),
                # Intrawindow risk tracking metadata (safe-coerced)
                "future_high": safe_float(row.get("future_high")),
                "future_low": safe_float(row.get("future_low")),
                "price_change_forward_close": safe_float(row.get("price_change_forward_close")),
                "price_change_forward": safe_float(row.get("price_change_forward")),
                "price_change_forward_low": safe_float(row.get("price_change_forward_low")),
                "max_profit_pct": safe_float(row.get("max_profit_pct")),
                "max_drawdown_pct": safe_float(row.get("max_drawdown_pct")),
                "hit_takeprofit": bool(row.get("hit_takeprofit", False)),
                "hit_stoploss": bool(row.get("hit_stoploss", False)),
            }
            metadata = {k: v for k, v in metadata.items() if v is not None}

            # Use internal add to prevent auto-flushing during bulk load
            self.collection.add(
                ids=[f"bootstrap_{idx}"],
                embeddings=[embedding],
                metadatas=[metadata],
            )
            loaded += 1

        logger.info("Bulk loaded %d patterns from %s", loaded, csv_path)
        return loaded

    def query(self, embedding: List[float], k: int = 5) -> Dict:
        """Low-level query API mirroring Chroma's response."""

        if self.count() == 0:
            return {"ids": [[]], "metadatas": [[]], "distances": [[]]}
        return self.collection.query(query_embeddings=[embedding], n_results=k)

    def find_similar(self, current_state: Dict[str, float], k: int = 5) -> List[Dict]:
        """High-level helper returning metadata + similarity."""

        embedding = [
            safe_float(current_state.get("rsi", 50.0), 50.0) / 100.0,
            safe_float(current_state.get("ema_ratio", 1.0), 1.0),
            safe_float(current_state.get("volume_change", 0.0), 0.0),
            safe_float(current_state.get("price_change", 0.0), 0.0),
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
        
    def get_pattern_by_id(self, pattern_id: str) -> Optional[Dict]:
        """Get a pattern by its ID."""
        try:
            results = self.collection.get(ids=[pattern_id])
            if results and results.get("metadatas") and len(results["metadatas"]) > 0:
                return {
                    "id": pattern_id,
                    "metadata": results["metadatas"][0],
                    "embedding": results["embeddings"][0] if results.get("embeddings") else None,
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get pattern by ID {pattern_id}: {e}")
            return None
    
    def update_pattern_label(self, pattern_id: str, label: str) -> bool:
        """Update the label for a pattern."""
        pattern = self.get_pattern_by_id(pattern_id)
        if not pattern:
            logger.warning(f"Pattern {pattern_id} not found, cannot update label")
            return False
        
        # Update the metadata with the new label
        metadata = pattern["metadata"]
        metadata["label"] = label
        metadata["labeled_at"] = time.time()
        
        try:
            # Update the pattern in the database
            self.collection.update(
                ids=[pattern_id],
                metadatas=[metadata]
            )
            logger.info(f"Updated pattern {pattern_id} with label {label}")
            return True
        except Exception as e:
            logger.error(f"Failed to update pattern {pattern_id}: {e}")
            return False

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
            "sample_size": sample_size,
            "win_rate": (wins / sample_size * 100) if sample_size else None,
            "loss_rate": (losses / sample_size * 100) if sample_size else None,
            "neutral_rate": (neutrals / sample_size * 100) if sample_size else None,
            "avg_max_profit_pct": (sum(max_profits) / len(max_profits) * 100) if max_profits else None,
            "avg_max_drawdown_pct": (sum(max_drawdowns) / len(max_drawdowns) * 100) if max_drawdowns else None,
            "total_patterns": total_patterns,
        }

    def get_capacity_info(self) -> Dict[str, float]:
        """Return database capacity information."""
        current = self.collection.count()
        max_val = safe_float(MAX_PATTERNS, 10000.0)
        percentage = current / max_val
        flush_at = max_val * FLUSH_THRESHOLD
        until_flush = flush_at - current if current < flush_at else 0
        will_remove = safe_float(int(max_val * FLUSH_PERCENTAGE))

        return {
            "current": safe_float(current),
            "max": max_val,
            "percentage": percentage,
            "until_flush": until_flush,
            "will_remove": will_remove,
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
    def _auto_flush(self) -> None:
        """Automatically remove the oldest patterns when capacity is reached."""
        current_count = self.collection.count()
        capacity_percent = current_count / MAX_PATTERNS
        logger.warning(
            "⚠️ DB at %.1f%% capacity! Triggering auto-flush...",
            capacity_percent * 100,
        )

        num_to_remove = int(MAX_PATTERNS * FLUSH_PERCENTAGE)
        logger.info("🗑️ Auto-flush: Removing %s oldest patterns...", num_to_remove)

        try:
            # Get all patterns with their timestamps
            data = self.collection.get(include=["metadatas"])
            
            # Create a list of (id, timestamp) tuples
            patterns_with_ts = []
            for i, meta in enumerate(data['metadatas']):
                if 'timestamp' in meta:
                    patterns_with_ts.append((data['ids'][i], meta['timestamp']))

            # Sort by timestamp (oldest first)
            patterns_with_ts.sort(key=lambda x: x[1])

            # Get IDs of the oldest patterns to delete
            ids_to_delete = [item[0] for item in patterns_with_ts[:num_to_remove]]

            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
                new_count = self.collection.count()
                logger.info(
                    "✅ Flush complete! Removed %d patterns. Now: %d/%d (%.1f%%)",
                    len(ids_to_delete),
                    new_count,
                    MAX_PATTERNS,
                    (new_count / MAX_PATTERNS) * 100,
                )
            else:
                logger.info("No patterns to flush.")

        except Exception as e:
            logger.error("❌ Auto-flush failed: %s", e, exc_info=True)


def _safe_float(value) -> Optional[float]:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
