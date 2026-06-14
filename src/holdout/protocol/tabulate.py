"""Vote tabulation: determine outcome from positions and reversibility tier.

Thresholds:
  REVERSIBLE:      simple majority — N//2 + 1 votes on one side.
  HARD_TO_REVERSE: unanimous      — all N votes on one side.

With an odd panel, REVERSIBLE always resolves to MAJORITY (no tie is possible).
SPLIT occurs only under HARD_TO_REVERSE when the vote is not unanimous.

FRAGILE_AGREEMENT is not determined here; that is concurrence.py (step 3).
"""

from __future__ import annotations

from collections.abc import Sequence

from holdout.types import Outcome, Position, Tier, Vote


def tabulate(positions: Sequence[Position], tier: Tier) -> Outcome:
    """Count positions against the reversibility threshold and return the outcome."""
    n = len(positions)
    yes = sum(1 for p in positions if p.vote is Vote.YES)
    no = n - yes
    threshold = _threshold(n, tier)
    if yes >= threshold or no >= threshold:
        return Outcome.MAJORITY
    return Outcome.SPLIT


def _threshold(n: int, tier: Tier) -> int:
    """Minimum votes on one side required to reach the acting threshold."""
    if tier is Tier.REVERSIBLE:
        return n // 2 + 1
    return n  # HARD_TO_REVERSE: unanimous
