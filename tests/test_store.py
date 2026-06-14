"""Tests for store/sqlite.py.

Covers: faithful round-trip, verbatim mandate/rationale, idempotency,
recency ordering, and similarity retrieval.
"""

from __future__ import annotations

import pytest

from magi.store.sqlite import RecordStore
from magi.types import Outcome, Position, Record, Tier, Vote

# ── helpers ───────────────────────────────────────────────────────────────────


def _pos(name: str, mandate: str, rationale: str, vote: Vote) -> Position:
    return Position(agent_name=name, agent_mandate=mandate, rationale=rationale, vote=vote)


_DEFAULT_POSITIONS: tuple[Position, ...] = (
    _pos("empirical", "reason from data", "data supports this <<E>>", Vote.YES),
    _pos("principled", "reason from duty", "duty requires it <<P>>", Vote.YES),
    _pos("practitioner", "reason from pattern", "pattern says caution <<X>>", Vote.NO),
)


def _make_record(
    *,
    id: str,
    question: str = "Should we do the thing?",
    tier: Tier = Tier.REVERSIBLE,
    outcome: Outcome = Outcome.MAJORITY,
    created_at: str = "2024-01-01T00:00:00Z",
    positions: tuple[Position, ...] = _DEFAULT_POSITIONS,
    crux: str | None = None,
    concurrence: bool = False,
) -> Record:
    return Record(
        id=id,
        question=question,
        tier=tier,
        outcome=outcome,
        created_at=created_at,
        positions=positions,
        crux=crux,
        concurrence=concurrence,
    )


@pytest.fixture
def store() -> RecordStore:
    return RecordStore(":memory:")


# ── round-trip ────────────────────────────────────────────────────────────────


def test_write_then_get_returns_faithful_record(store: RecordStore) -> None:
    original = _make_record(id="r1")
    store.write(original)
    assert store.get("r1") == original


def test_get_missing_returns_none(store: RecordStore) -> None:
    assert store.get("nonexistent") is None


def test_split_record_round_trips(store: RecordStore) -> None:
    positions = (
        _pos("a", "mandate_a", "rationale_a", Vote.YES),
        _pos("b", "mandate_b", "rationale_b", Vote.NO),
        _pos("c", "mandate_c", "rationale_c", Vote.NO),
    )
    original = _make_record(
        id="r-split",
        outcome=Outcome.SPLIT,
        positions=positions,
        crux="If this fails, will we lose users permanently?",
    )
    store.write(original)
    assert store.get("r-split") == original


def test_fragile_agreement_round_trips(store: RecordStore) -> None:
    positions = (
        _pos("a", "ma", "ra <<A>>", Vote.YES),
        _pos("b", "mb", "rb <<B>>", Vote.YES),
        _pos("c", "mc", "rc <<C>>", Vote.YES),
    )
    original = _make_record(
        id="r-fragile",
        outcome=Outcome.FRAGILE_AGREEMENT,
        positions=positions,
        concurrence=True,
    )
    store.write(original)
    assert store.get("r-fragile") == original


def test_position_order_preserved(store: RecordStore) -> None:
    """Positions must come back in the same order they were written."""
    positions = (
        _pos("z", "mz", "rz", Vote.NO),
        _pos("a", "ma", "ra", Vote.YES),
        _pos("m", "mm", "rm", Vote.YES),
    )
    record = _make_record(id="r-order", positions=positions)
    store.write(record)
    got = store.get("r-order")
    assert got is not None
    assert tuple(p.agent_name for p in got.positions) == ("z", "a", "m")


# ── verbatim mandate and rationale (auditability guarantee) ───────────────────


def test_mandates_stored_verbatim(store: RecordStore) -> None:
    record = _make_record(id="r-mandate")
    store.write(record)
    got = store.get("r-mandate")
    assert got is not None
    for orig, ret in zip(record.positions, got.positions, strict=True):
        assert ret.agent_mandate == orig.agent_mandate


def test_rationales_stored_verbatim(store: RecordStore) -> None:
    record = _make_record(id="r-rationale")
    store.write(record)
    got = store.get("r-rationale")
    assert got is not None
    for orig, ret in zip(record.positions, got.positions, strict=True):
        assert ret.rationale == orig.rationale


# ── idempotency ───────────────────────────────────────────────────────────────


def test_duplicate_write_is_ignored(store: RecordStore) -> None:
    original = _make_record(id="r-dup")
    store.write(original)
    store.write(original)  # must not raise or corrupt
    assert store.get("r-dup") == original


def test_duplicate_write_does_not_double_positions(store: RecordStore) -> None:
    original = _make_record(id="r-dup2")
    store.write(original)
    store.write(original)
    got = store.get("r-dup2")
    assert got is not None
    assert len(got.positions) == len(original.positions)


# ── recency ───────────────────────────────────────────────────────────────────


def test_recent_returns_newest_first(store: RecordStore) -> None:
    r1 = _make_record(id="old", created_at="2024-01-01T00:00:00Z")
    r2 = _make_record(id="new", created_at="2024-06-01T00:00:00Z")
    store.write(r1)
    store.write(r2)
    assert [r.id for r in store.recent(10)] == ["new", "old"]


def test_recent_respects_limit(store: RecordStore) -> None:
    for i in range(5):
        store.write(_make_record(id=f"r{i}", created_at=f"2024-0{i + 1}-01T00:00:00Z"))
    assert len(store.recent(3)) == 3


def test_recent_empty_store(store: RecordStore) -> None:
    assert store.recent() == []


def test_recent_all_when_fewer_than_limit(store: RecordStore) -> None:
    store.write(_make_record(id="only"))
    assert len(store.recent(100)) == 1


# ── similarity ────────────────────────────────────────────────────────────────


def test_similar_returns_kindred_record(store: RecordStore) -> None:
    """A record about authentication should surface for a query about authentication."""
    auth_rec = _make_record(
        id="auth", question="Should we rewrite the authentication service in Rust?"
    )
    db_rec = _make_record(id="db", question="Should we migrate the billing database schema?")
    store.write(auth_rec)
    store.write(db_rec)
    results = store.similar("Should we replace the authentication service?", n=5)
    assert any(r.id == "auth" for r in results)


def test_similar_no_match_returns_empty(store: RecordStore) -> None:
    store.write(_make_record(id="r1", question="Should we deploy on Friday?"))
    assert store.similar("xyzzy frobnosticator quux", n=5) == []


def test_similar_respects_limit(store: RecordStore) -> None:
    for i in range(5):
        store.write(_make_record(id=f"r{i}", question=f"Should we rewrite service {i}?"))
    results = store.similar("Should we rewrite a service?", n=2)
    assert len(results) <= 2


def test_similar_empty_store(store: RecordStore) -> None:
    assert store.similar("Should we do anything?", n=5) == []


def test_similar_empty_question_returns_empty(store: RecordStore) -> None:
    store.write(_make_record(id="r1"))
    assert store.similar("", n=5) == []
