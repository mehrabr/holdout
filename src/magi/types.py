"""Core type contract for MAGI.

This module is the contract. Every other module depends on it, and it depends on
nothing inside the package. Build it first; change it rarely.

Two load-bearing invariants are encoded structurally here, not just by convention:

1. NO SYNTHESIS. `Record` has no field for a merged or synthesized answer. There is
   nowhere to put one. A synthesis step cannot be added without changing this type,
   which makes the violation loud and reviewable.

2. BLIND COMMITMENT is enforced at the function boundary (see protocol.commit), not
   here -- but `Position` deliberately carries only one agent's output, so a position
   can never structurally contain a peer's rationale.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations
# ─────────────────────────────────────────────────────────────────────────────

class Vote(str, Enum):
    """A binding position. Deliberately binary: the system forces commitment."""
    YES = "yes"
    NO = "no"


class Tier(str, Enum):
    """Decision reversibility. The only classification the system makes."""
    REVERSIBLE = "reversible"
    HARD_TO_REVERSE = "hard_to_reverse"


class Outcome(str, Enum):
    """The terminal state of a deliberation.

    Note what is absent: there is no 'synthesized' or 'merged' outcome. The three
    possible outcomes preserve disagreement rather than resolving it into one answer.
    """
    MAJORITY = "majority"                 # a position prevailed by the tier threshold
    SPLIT = "split"                       # threshold not met; crux produced, no verdict
    FRAGILE_AGREEMENT = "fragile_agreement"  # agreement reached on incompatible reasons


# ─────────────────────────────────────────────────────────────────────────────
# Inputs
# ─────────────────────────────────────────────────────────────────────────────

class Agent(BaseModel):
    """One reasoner with a fixed mandate.

    The mandate is a constraint on what evidence the agent may invoke -- not a
    personality. It is stored verbatim on every Position so the conditions of a
    deliberation are auditable from the record alone.
    """
    model_config = {"frozen": True}

    name: str = Field(min_length=1, description="Stable identifier, e.g. 'empirical'.")
    mandate: str = Field(min_length=1, description="The reasoning constraint, verbatim.")

    @field_validator("name")
    @classmethod
    def _name_no_whitespace(cls, v: str) -> str:
        if v != v.strip() or not v:
            raise ValueError("agent name must be non-empty and not surrounded by whitespace")
        return v


# ─────────────────────────────────────────────────────────────────────────────
# Atomic outputs
# ─────────────────────────────────────────────────────────────────────────────

class Position(BaseModel):
    """One agent's committed output for one deliberation.

    This is the unit of blind commitment. It carries exactly one agent's mandate,
    rationale, and vote -- never a reference to, or content from, any peer. The
    protocol guarantees it was produced without sight of peers; the type guarantees
    it cannot structurally hold a peer's content.
    """
    model_config = {"frozen": True}

    agent_name: str = Field(min_length=1)
    agent_mandate: str = Field(min_length=1, description="Stored verbatim for auditability.")
    rationale: str = Field(min_length=1, description="The agent's full written reasoning, verbatim.")
    vote: Vote


# ─────────────────────────────────────────────────────────────────────────────
# The record (the product)
# ─────────────────────────────────────────────────────────────────────────────

class Record(BaseModel):
    """The durable artifact of one deliberation. This is the product.

    INVARIANT (no synthesis): there is no field here for a final, merged, or
    synthesized answer. The record preserves the competing positions; it does not
    resolve them into one response. Do not add such a field.

    INVARIANT (dissent preserved): `positions` always contains every agent's full
    rationale verbatim, including the losing one(s). The `minority` accessor derives
    the losing rationale from `positions`; it never stores a summarized version.
    """
    model_config = {"frozen": True}

    id: str = Field(min_length=1, description="Stable identifier for retrieval and citation.")
    created_at: str = Field(description="ISO 8601 timestamp.")
    question: str = Field(min_length=1, description="The question as asked, verbatim.")
    tier: Tier
    positions: tuple[Position, ...] = Field(description="Every agent's position, verbatim.")
    outcome: Outcome

    # Present only on SPLIT. Consequence-anchored: names the adverse outcome the
    # minority is reasoning about, not merely where the positions differ.
    crux: str | None = Field(default=None)

    # True when agreement rests on incompatible reasons (Outcome.FRAGILE_AGREEMENT).
    concurrence: bool = Field(default=False)

    @field_validator("positions")
    @classmethod
    def _at_least_three_and_odd(cls, v: tuple[Position, ...]) -> tuple[Position, ...]:
        if len(v) < 3:
            raise ValueError("a panel requires at least 3 positions")
        if len(v) % 2 == 0:
            raise ValueError("panel size must be odd to guarantee a tie-break on binary votes")
        return v

    def model_post_init(self, __context: object) -> None:
        # Structural cross-field guarantees. These encode the spec's invariants so
        # that an invalid Record cannot be constructed.
        if self.outcome is Outcome.SPLIT and not self.crux:
            raise ValueError("a SPLIT outcome must carry a consequence-anchored crux")
        if self.outcome is not Outcome.SPLIT and self.crux is not None:
            raise ValueError("crux is only meaningful on a SPLIT outcome")
        if self.outcome is Outcome.FRAGILE_AGREEMENT and not self.concurrence:
            raise ValueError("FRAGILE_AGREEMENT requires the concurrence flag to be set")
        if self.concurrence and self.outcome is not Outcome.FRAGILE_AGREEMENT:
            raise ValueError("concurrence may only be set on a FRAGILE_AGREEMENT outcome")

    # ── derived accessors (never stored, always computed from positions) ──

    @property
    def votes(self) -> dict[str, Vote]:
        """Map of agent_name -> vote."""
        return {p.agent_name: p.vote for p in self.positions}

    @property
    def tally(self) -> dict[Vote, int]:
        """Count of YES vs NO."""
        return {
            Vote.YES: sum(1 for p in self.positions if p.vote is Vote.YES),
            Vote.NO: sum(1 for p in self.positions if p.vote is Vote.NO),
        }

    @property
    def prevailing(self) -> Vote | None:
        """The winning vote on a MAJORITY outcome; None on SPLIT.

        On FRAGILE_AGREEMENT the agents are unanimous, so this returns that vote.
        """
        if self.outcome is Outcome.SPLIT:
            return None
        t = self.tally
        return Vote.YES if t[Vote.YES] > t[Vote.NO] else Vote.NO

    @property
    def minority(self) -> tuple[Position, ...]:
        """The preserved losing positions, verbatim.

        Empty when the panel was unanimous (no losing side). Never a summary --
        always the full Position objects, retained from `positions`.
        """
        win = self.prevailing
        if win is None:  # SPLIT: there is no single prevailing side; all positions stand
            return self.positions
        return tuple(p for p in self.positions if p.vote is not win)
