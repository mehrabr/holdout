"""MAGI — preserve the dissenting reasoning behind contested decisions.

Public API is intentionally tiny. The contract lives in `types`; the provider seam
in `providers.base`.
"""

from magi.protocol.engine import Panel
from magi.types import Agent, Outcome, Position, Record, Tier, Vote

__all__ = ["Agent", "Outcome", "Panel", "Position", "Record", "Tier", "Vote"]
