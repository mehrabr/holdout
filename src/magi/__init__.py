"""MAGI — preserve the dissenting reasoning behind contested decisions.

Public API is intentionally tiny. The contract lives in `types`; the provider seam
in `providers.base`. Engine, store, and report are added in later build steps.
"""

from magi.types import Agent, Outcome, Position, Record, Tier, Vote

__all__ = ["Agent", "Outcome", "Position", "Record", "Tier", "Vote"]
