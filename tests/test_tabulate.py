"""Tests for protocol.tabulate -- vote counting and threshold logic.

Two property tests are included:
  - tabulate() never returns FRAGILE_AGREEMENT (that is concurrence.py's job).
  - With odd N and REVERSIBLE tier, tabulate() always returns MAJORITY (pigeonhole).
"""

from __future__ import annotations

import pytest

from magi.protocol.tabulate import tabulate
from magi.types import Outcome, Position, Tier, Vote

# ---- helpers ----------------------------------------------------------------


def _positions(*votes: str) -> list[Position]:
    """Build a list of minimal Position objects with the given votes."""
    return [
        Position(
            agent_name=f"agent{i}",
            agent_mandate=f"mandate{i}",
            rationale=f"rationale {i}",
            vote=Vote(v),
        )
        for i, v in enumerate(votes)
    ]


# ---- REVERSIBLE tier --------------------------------------------------------


def test_reversible_majority_yes() -> None:
    assert tabulate(_positions("yes", "yes", "no"), Tier.REVERSIBLE) is Outcome.MAJORITY


def test_reversible_majority_no() -> None:
    assert tabulate(_positions("yes", "no", "no"), Tier.REVERSIBLE) is Outcome.MAJORITY


def test_reversible_unanimous_yes() -> None:
    assert tabulate(_positions("yes", "yes", "yes"), Tier.REVERSIBLE) is Outcome.MAJORITY


def test_reversible_unanimous_no() -> None:
    assert tabulate(_positions("no", "no", "no"), Tier.REVERSIBLE) is Outcome.MAJORITY


def test_reversible_five_agents_majority() -> None:
    positions = _positions("yes", "yes", "yes", "no", "no")
    assert tabulate(positions, Tier.REVERSIBLE) is Outcome.MAJORITY


def test_reversible_five_agents_unanimous() -> None:
    positions = _positions("yes", "yes", "yes", "yes", "yes")
    assert tabulate(positions, Tier.REVERSIBLE) is Outcome.MAJORITY


# ---- HARD_TO_REVERSE tier ---------------------------------------------------


def test_hard_to_reverse_unanimous_yes_passes() -> None:
    positions = _positions("yes", "yes", "yes")
    assert tabulate(positions, Tier.HARD_TO_REVERSE) is Outcome.MAJORITY


def test_hard_to_reverse_unanimous_no_passes() -> None:
    positions = _positions("no", "no", "no")
    assert tabulate(positions, Tier.HARD_TO_REVERSE) is Outcome.MAJORITY


def test_hard_to_reverse_two_one_yes_splits() -> None:
    """2-1 is not unanimous -- HARD_TO_REVERSE requires all votes on one side."""
    positions = _positions("yes", "yes", "no")
    assert tabulate(positions, Tier.HARD_TO_REVERSE) is Outcome.SPLIT


def test_hard_to_reverse_one_two_no_splits() -> None:
    positions = _positions("yes", "no", "no")
    assert tabulate(positions, Tier.HARD_TO_REVERSE) is Outcome.SPLIT


def test_hard_to_reverse_five_agents_four_one_splits() -> None:
    positions = _positions("yes", "yes", "yes", "yes", "no")
    assert tabulate(positions, Tier.HARD_TO_REVERSE) is Outcome.SPLIT


def test_hard_to_reverse_five_agents_unanimous_passes() -> None:
    positions = _positions("yes", "yes", "yes", "yes", "yes")
    assert tabulate(positions, Tier.HARD_TO_REVERSE) is Outcome.MAJORITY


# ---- property tests ---------------------------------------------------------


@pytest.mark.parametrize(
    "votes",
    [
        ["yes", "yes", "no"],
        ["yes", "no", "no"],
        ["yes", "yes", "yes"],
        ["no", "no", "no"],
        ["yes", "yes", "yes", "no", "no"],
        ["yes", "yes", "no", "no", "no"],
    ],
)
def test_tabulate_never_returns_fragile_agreement(votes: list[str]) -> None:
    """FRAGILE_AGREEMENT is determined by concurrence.py, not tabulate().

    tabulate() returns only MAJORITY or SPLIT. This is a structural property:
    tabulate has no provider access and cannot perform the LLM call needed to
    detect incompatible rationale alignment.
    """
    assert tabulate(_positions(*votes), Tier.REVERSIBLE) is not Outcome.FRAGILE_AGREEMENT
    assert tabulate(_positions(*votes), Tier.HARD_TO_REVERSE) is not Outcome.FRAGILE_AGREEMENT


@pytest.mark.parametrize("n", [3, 5, 7, 9])
def test_reversible_odd_panel_always_majority(n: int) -> None:
    """With an odd panel and REVERSIBLE tier, there is always a majority (pigeonhole).

    An odd number of binary votes can never produce a tie, so REVERSIBLE always
    resolves. SPLIT is only possible under HARD_TO_REVERSE (requires unanimity).
    """
    # Closest-to-split vote: (n//2 + 1) YES vs (n//2) NO
    votes = ["yes"] * (n // 2 + 1) + ["no"] * (n // 2)
    assert tabulate(_positions(*votes), Tier.REVERSIBLE) is Outcome.MAJORITY


@pytest.mark.parametrize("n", [3, 5, 7, 9])
def test_hard_to_reverse_odd_panel_always_defined(n: int) -> None:
    """With odd N and HARD_TO_REVERSE tier, every vote distribution resolves to
    exactly one of {MAJORITY, SPLIT} — never an undefined state.

    Unanimous → MAJORITY; anything short of unanimous → SPLIT.
    """
    valid = {Outcome.MAJORITY, Outcome.SPLIT}

    # Unanimous case
    unanimous = ["yes"] * n
    assert tabulate(_positions(*unanimous), Tier.HARD_TO_REVERSE) in valid

    # Closest-to-split (one dissent) → SPLIT
    one_dissent = ["yes"] * (n - 1) + ["no"]
    result = tabulate(_positions(*one_dissent), Tier.HARD_TO_REVERSE)
    assert result in valid
    assert result is Outcome.SPLIT

    # Bare majority (not unanimous) → SPLIT
    bare_majority = ["yes"] * (n // 2 + 1) + ["no"] * (n // 2)
    result = tabulate(_positions(*bare_majority), Tier.HARD_TO_REVERSE)
    assert result in valid
    assert result is Outcome.SPLIT
