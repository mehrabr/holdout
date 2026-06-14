"""Durable SQLite store for deliberation Records.

Implements write, get-by-id, recency retrieval, and similarity retrieval.
The schema is verbatim from the spec (see schema.sql).

Similarity uses SQLite FTS5 BM25 ranking over the question text, converting
the query into an OR-joined term list so partial matches still surface kindred
records. No external dependencies — all capabilities are built into SQLite.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Final

from magi.types import Outcome, Position, Record, Tier, Vote

_SCHEMA: Final[str] = (Path(__file__).parent / "schema.sql").read_text()

_WORD_RE: Final[re.Pattern[str]] = re.compile(r"[a-zA-Z0-9]+")


def _fts_query(question: str) -> str:
    """Convert a natural-language question into an FTS5 OR-joined term query."""
    words = _WORD_RE.findall(question)
    return " OR ".join(words)


class RecordStore:
    """Write and retrieve deliberation Records from a local SQLite database.

    Args:
        db_path: Path to the SQLite file, or ``":memory:"`` for a transient store.
    """

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ── write ─────────────────────────────────────────────────────────────────

    def write(self, record: Record) -> None:
        """Persist a Record. Duplicate id writes are silently ignored."""
        if self._conn.execute("SELECT 1 FROM deliberation WHERE id = ?", (record.id,)).fetchone():
            return

        with self._conn:
            self._conn.execute(
                "INSERT INTO deliberation"
                " (id, created_at, question, tier, outcome, crux, concurrence)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.created_at,
                    record.question,
                    record.tier.value,
                    record.outcome.value,
                    record.crux,
                    1 if record.concurrence else 0,
                ),
            )
            self._conn.executemany(
                "INSERT INTO position"
                " (deliberation_id, ord, agent_name, agent_mandate, rationale, vote)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (record.id, i, p.agent_name, p.agent_mandate, p.rationale, p.vote.value)
                    for i, p in enumerate(record.positions)
                ],
            )
            self._conn.execute(
                "INSERT INTO deliberation_fts (deliberation_id, question) VALUES (?, ?)",
                (record.id, record.question),
            )

    # ── retrieval ─────────────────────────────────────────────────────────────

    def get(self, record_id: str) -> Record | None:
        """Return the Record for ``record_id``, or None if not found."""
        row = self._conn.execute("SELECT * FROM deliberation WHERE id = ?", (record_id,)).fetchone()
        return self._build(row) if row else None

    def recent(self, n: int = 10) -> list[Record]:
        """Return the ``n`` most recently written Records, newest first."""
        rows = self._conn.execute(
            "SELECT * FROM deliberation ORDER BY created_at DESC LIMIT ?", (n,)
        ).fetchall()
        return [self._build(r) for r in rows]

    def similar(self, question: str, n: int = 5) -> list[Record]:
        """Return up to ``n`` Records whose question most resembles ``question``.

        Uses FTS5 BM25 ranking. Returns an empty list when no stored records
        share any term with the query.
        """
        fts_q = _fts_query(question)
        if not fts_q:
            return []
        try:
            id_rows = self._conn.execute(
                "SELECT deliberation_id FROM deliberation_fts"
                " WHERE question MATCH ? ORDER BY rank LIMIT ?",
                (fts_q, n),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        records = []
        for id_row in id_rows:
            rec = self.get(id_row["deliberation_id"])
            if rec is not None:
                records.append(rec)
        return records

    # ── internals ─────────────────────────────────────────────────────────────

    def _build(self, row: sqlite3.Row) -> Record:
        pos_rows = self._conn.execute(
            "SELECT agent_name, agent_mandate, rationale, vote"
            " FROM position WHERE deliberation_id = ? ORDER BY ord",
            (row["id"],),
        ).fetchall()
        positions = tuple(
            Position(
                agent_name=r["agent_name"],
                agent_mandate=r["agent_mandate"],
                rationale=r["rationale"],
                vote=Vote(r["vote"]),
            )
            for r in pos_rows
        )
        return Record(
            id=row["id"],
            created_at=row["created_at"],
            question=row["question"],
            tier=Tier(row["tier"]),
            outcome=Outcome(row["outcome"]),
            crux=row["crux"],
            concurrence=bool(row["concurrence"]),
            positions=positions,
        )
