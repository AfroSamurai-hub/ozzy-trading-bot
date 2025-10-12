"""Rolling window vector database for recent trading patterns.

Keeps a small time-bounded set of patterns (default 48h) inside ChromaDB so
queries stay fast and only reflect the latest market context.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

import chromadb
from chromadb.config import Settings


@dataclass
class PatternEmbedding:
    id: str
    embedding: List[float]
    metadata: Dict


class RollingWindowPatternDB:
    """Time-bounded pattern storage using ChromaDB."""

    def __init__(
        self,
        persist_directory: str = "data/vector_db",
        window_hours: int = 48,
    ) -> None:
        self.window_hours = window_hours
        self.max_age_seconds = window_hours * 3600
        self._client = chromadb.Client(
            Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=persist_directory,
            )
        )
        self.collection = self._client.get_or_create_collection("rolling_patterns")

    def _prune_old_patterns(self) -> int:
        cutoff = time.time() - self.max_age_seconds
        old = self.collection.get(where={"timestamp": {"$lt": cutoff}})
        ids = old.get("ids", []) if old else []
        if ids:
            self.collection.delete(ids=ids)
        return len(ids)

    def add_pattern(self, pattern: PatternEmbedding) -> None:
        self.collection.add(
            ids=[pattern.id],
            embeddings=[pattern.embedding],
            metadatas=[pattern.metadata],
        )
        self._prune_old_patterns()

    def load_from_csv(self, csv_path: str) -> int:
        df = pd.read_csv(csv_path)
        if df.empty:
            return 0

        patterns = []
        for idx, row in df.iterrows():
            embedding = [
                float(row.get("rsi", 50)) / 100.0,
                float(row.get("ema_ratio", 1.0)),
                float(row.get("volume_change", 0.0)),
                float(row.get("price_change", 0.0)),
            ]
            metadata = {
                "timestamp": pd.to_datetime(row["timestamp"]).timestamp(),
                "label": row.get("label", "UNKNOWN"),
                "rsi": float(row.get("rsi", 50)),
                "ema_ratio": float(row.get("ema_ratio", 1.0)),
            }
            patterns.append(
                PatternEmbedding(
                    id=f"bootstrap_{idx}",
                    embedding=embedding,
                    metadata=metadata,
                )
            )

        for pattern in patterns:
            self.add_pattern(pattern)

        return len(patterns)

    def query(self, embedding: List[float], k: int = 5) -> Dict:
        if self.count() == 0:
            return {"ids": [[]], "metadatas": [[]], "distances": [[]]}
        return self.collection.query(query_embeddings=[embedding], n_results=k)

    def count(self) -> int:
        return self.collection.count()

    def get_stats(self) -> Dict[str, Optional[float]]:
        data = self.collection.get(limit=1000)
        metadatas = data.get("metadatas", []) or []
        wins = sum(1 for m in metadatas if m.get("label") == "WIN")
        total = len(metadatas)
        return {
            "window_hours": self.window_hours,
            "max_age_seconds": self.max_age_seconds,
            "sample_size": total,
            "win_rate": (wins / total * 100) if total else None,
            "total_patterns": self.count(),
        }
