"""Tests for the MAGI type contract (types.py).

These tests form the regression net for the contract. Two are pre-merge gate
tests that must never be removed or skipped:
  - test_no_synthesis_field_absence: Invariant I structural check.
  - test_minority_is_verbatim:       Invariant I dissent-preservation check.
"""

from __future__ import annotations

import pytest

from holdout.types import Agent, Outcome, Position, Record, Tier, Vote

# ─── helpers ──────────────────────────────────────────────────────────────────


def _pos(name: str, mandate: str, rationale: str, vote: str) -> Position:
    return Position(
        agent_name=name,
        agent_mandate=mandate,
        rationale=rationale,
        vote=Vote(vote),
    )


def _record(
    positions: list[Position],
    outcome: Outcome,
    crux: str | None = None,
    concurrence: bool = False,
) -> Record:
    return Record(
        id="test-record-001",
        created_at="2026-06-13T00:00:00Z",
        question="Should we adopt this approach?",
        tier=Tier.REVERSIBLE,
        positions=tuple(positions),
        outcome=outcome,
        crux=crux,
        concurrence=concurrence,
    )


MAJORITY_POSITIONS = [
    _pos("alpha", "reason from data", "Data supports yes.", "yes"),
    _pos("beta", "reason from duty", "Duty requires yes.", "yes"),
    _pos("gamma", "reason from pattern", "Pattern suggests no.", "no"),
]

UNANIMOUS_POSITIONS = [
    _pos("alpha", "reason from data", "Data supports yes.", "yes"),
    _pos("beta", "reason from duty", "Duty requires yes.", "yes"),
    _pos("gamma", "reason from pattern", "Pattern supports yes.", "yes"),
]

# ─── Agent construction ───────────────────────────────────────────────────────


def test_empty_mandate_rejected() -> None:
    with pytest.raises(ValueError):
        Agent(name="x", mandate="")


def test_whitespace_name_rejected() -> None:
    with pytest.raises(ValueError):
        Agent(name="  ", mandate="valid mandate")


def test_valid_agent_constructs() -> None:
    a = Agent(name="empirical", mandate="reason from data and evidence")
    assert a.name == "empirical"
    assert a.mandate == "reason from data and evidence"


# ─── Panel size invariants ─────────────────────────────────────────────────────


def test_two_positions_rejected() -> None:
    with pytest.raises(ValueError):
        _record(MAJORITY_POSITIONS[:2], Outcome.MAJORITY)


def test_four_positions_rejected() -> None:
    four = [
        _pos("a", "m1", "r1", "yes"),
        _pos("b", "m2", "r2", "yes"),
        _pos("c", "m3", "r3", "no"),
        _pos("d", "m4", "r4", "no"),
    ]
    with pytest.raises(ValueError):
        _record(four, Outcome.SPLIT, crux="Some crux.")


# ─── Cross-field invariants ───────────────────────────────────────────────────


def test_split_without_crux_rejected() -> None:
    with pytest.raises(Exception, match="crux"):
        _record(MAJORITY_POSITIONS, Outcome.SPLIT)


def test_crux_on_non_split_rejected() -> None:
    with pytest.raises(Exception, match="crux"):
        _record(MAJORITY_POSITIONS, Outcome.MAJORITY, crux="A crux.")


def test_split_with_crux_constructs() -> None:
    r = _record(MAJORITY_POSITIONS, Outcome.SPLIT, crux="The specific disagreement.")
    assert r.crux == "The specific disagreement."
    assert r.outcome is Outcome.SPLIT


def test_fragile_agreement_without_concurrence_rejected() -> None:
    with pytest.raises(Exception, match="concurrence"):
        _record(UNANIMOUS_POSITIONS, Outcome.FRAGILE_AGREEMENT, concurrence=False)


def test_concurrence_on_non_fragile_rejected() -> None:
    with pytest.raises(Exception, match="concurrence"):
        _record(UNANIMOUS_POSITIONS, Outcome.MAJORITY, concurrence=True)


def test_fragile_agreement_with_concurrence_constructs() -> None:
    r = _record(UNANIMOUS_POSITIONS, Outcome.FRAGILE_AGREEMENT, concurrence=True)
    assert r.concurrence is True
    assert r.outcome is Outcome.FRAGILE_AGREEMENT


# ─── Derived accessors ────────────────────────────────────────────────────────


def test_tally_counts_correctly() -> None:
    r = _record(MAJORITY_POSITIONS, Outcome.MAJORITY)
    assert r.tally == {Vote.YES: 2, Vote.NO: 1}


def test_prevailing_is_yes() -> None:
    r = _record(MAJORITY_POSITIONS, Outcome.MAJORITY)
    assert r.prevailing is Vote.YES


def test_minority_is_the_single_no_position() -> None:
    r = _record(MAJORITY_POSITIONS, Outcome.MAJORITY)
    assert len(r.minority) == 1
    assert r.minority[0] == MAJORITY_POSITIONS[2]


def test_split_prevailing_is_none() -> None:
    r = _record(MAJORITY_POSITIONS, Outcome.SPLIT, crux="The crux.")
    assert r.prevailing is None


def test_split_minority_preserves_all_positions() -> None:
    r = _record(MAJORITY_POSITIONS, Outcome.SPLIT, crux="The crux.")
    assert len(r.minority) == len(MAJORITY_POSITIONS)
    assert {p.agent_name for p in r.minority} == {"alpha", "beta", "gamma"}


# ─── Invariant I: No synthesis (field-absence, structural) ────────────────────
# PRE-MERGE GATE: do not remove or skip.


def test_no_synthesis_field_absence() -> None:
    """Record has no field capable of holding a merged or synthesized answer.

    Structural enforcement of Invariant I. Adding synthesis requires changing
    this type, making the violation visible and reviewable before it ships.
    """
    forbidden = {"synthesis", "answer", "final", "summary", "consensus", "verdict", "verdict_text"}
    record_fields = set(Record.model_fields.keys())
    violations = forbidden & record_fields
    assert not violations, (
        f"Record has field(s) {violations!r} that could hold a synthesized answer -- "
        "Invariant I (no synthesis) violated"
    )


# ─── Invariant I: Dissent preserved verbatim ──────────────────────────────────
# PRE-MERGE GATE: do not remove or skip.


def test_minority_is_verbatim() -> None:
    """record.minority returns the exact Position data -- never a paraphrase.

    Embeds a unique token in the minority rationale and asserts it survives
    byte-for-byte in the output. The minority is derived from `positions`, not
    stored separately, so it cannot silently drift from the committed output.
    """
    unique_token = "VERBATIM_SENTINEL_4471_GAMMA"
    minority_pos = _pos(
        "gamma",
        "reason from pattern",
        f"Pattern suggests no. {unique_token}",
        "no",
    )
    positions = [
        _pos("alpha", "reason from data", "Data supports yes.", "yes"),
        _pos("beta", "reason from duty", "Duty requires yes.", "yes"),
        minority_pos,
    ]
    r = _record(positions, Outcome.MAJORITY)

    assert len(r.minority) == 1
    m = r.minority[0]
    assert m.agent_name == "gamma"
    assert m.agent_mandate == "reason from pattern"
    assert unique_token in m.rationale, "minority rationale was not preserved verbatim"
    assert m.vote is Vote.NO
