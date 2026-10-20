"""Layer 5 (V1 part) — SQLite task log + weight suggestions.

Every routed task is logged as {scene x model x success x tokens x
latency}. This is the raw material the "growing brain" learns from.

V1 honesty rule: the log only *suggests* routing-weight changes
(`suggest()`); it never silently rewrites routes.yaml. Automatic
application is V2, after enough real data exists to be trustworthy.
"""

from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path


def default_db_path() -> Path:
    env = os.environ.get("DISPATCH_BRAIN_DB")
    if env:
        return Path(env)
    return Path.cwd() / "data" / "task_log.db"


class LogStore:
    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                scene TEXT NOT NULL,
                difficulty TEXT,
                model_alias TEXT,
                success INTEGER,
                tokens INTEGER DEFAULT 0,
                latency_ms INTEGER DEFAULT 0,
                note TEXT
            )
            """
        )
        self._conn.commit()

    def record(
        self,
        scene: str,
        model_alias: str | None,
        success: bool,
        tokens: int = 0,
        latency_ms: int = 0,
        difficulty: str = "",
        note: str = "",
    ) -> None:
        self._conn.execute(
            "INSERT INTO task_log (ts, scene, difficulty, model_alias, success, tokens, latency_ms, note)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), scene, difficulty, model_alias, 1 if success else 0,
             int(tokens), int(latency_ms), note),
        )
        self._conn.commit()

    def stats(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT scene, model_alias, COUNT(*) AS n,
                   AVG(success) AS success_rate,
                   AVG(tokens) AS avg_tokens,
                   AVG(latency_ms) AS avg_latency_ms
            FROM task_log
            WHERE model_alias IS NOT NULL
            GROUP BY scene, model_alias
            ORDER BY scene, success_rate DESC
            """
        ).fetchall()
        return [
            {
                "scene": r[0],
                "model_alias": r[1],
                "n": r[2],
                "success_rate": round(r[3] or 0.0, 3),
                "avg_tokens": round(r[4] or 0.0, 1),
                "avg_latency_ms": round(r[5] or 0.0, 1),
            }
            for r in rows
        ]

    def suggest(self, min_samples: int = 5) -> dict:
        """Per scene, rank models by cost-effectiveness.

        score = success_rate / avg_tokens (normalised per 1k tokens).
        Scenes with too little data are reported as insufficient_data
        instead of producing a confident-sounding guess.
        """
        out: dict[str, dict] = {}
        for row in self.stats():
            scene = row["scene"]
            entry = out.setdefault(scene, {"best": None, "candidates": []})
            if row["n"] < min_samples:
                entry["candidates"].append({**row, "verdict": "insufficient_data"})
                continue
            score = row["success_rate"] / max(row["avg_tokens"], 1.0) * 1000.0
            cand = {**row, "score": round(score, 4)}
            entry["candidates"].append(cand)
            if entry["best"] is None or score > entry["best"]["score"]:
                entry["best"] = cand
        return out

    def close(self) -> None:
        self._conn.close()
