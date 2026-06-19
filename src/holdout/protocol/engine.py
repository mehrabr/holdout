"""Engine: orchestrates the full MAGI protocol from question to Record.

The Panel class is the single public entrypoint. The caller asserts the
decision's reversibility tier; the engine does not infer or validate it.

Two-tier handling:
  REVERSIBLE:      simple majority threshold; non-unanimous → MAJORITY, not SPLIT.
  HARD_TO_REVERSE: unanimous threshold; anything short of unanimous → SPLIT.

Both tiers run concurrence detection on unanimous results.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from holdout.protocol.commit import gather
from holdout.protocol.concurrence import detect_concurrence
from holdout.protocol.crux import extract_crux
from holdout.protocol.tabulate import tabulate
from holdout.providers.base import Provider
from holdout.types import Agent, Outcome, Record, Tier, Vote


@dataclass
class Panel:
    """An N-agent panel that deliberates on a question.

    The provider is an injected seam: any implementation of the Provider protocol
    works, including FakeProvider for offline testing.
    """

    agents: Sequence[Agent]
    provider: Provider

    async def deliberate(
        self,
        question: str,
        tier: Tier | str,
        images: Sequence[str] = (),
    ) -> Record:
        """Run a full deliberation and return the durable Record.

        The caller asserts the reversibility tier; the engine does not infer it.
        All agent commitments are dispatched concurrently (blind commitment guarantee).

        `images` is an optional list of paths or URLs passed as shared visual context
        to every agent. It does not affect the deliberation contract.
        """
        resolved_tier = Tier(tier)
        positions = await gather(question, self.agents, self.provider, images)
        initial_outcome = tabulate(positions, resolved_tier)

        crux: str | None = None
        concurrence = False

        if initial_outcome is Outcome.SPLIT:
            crux = await extract_crux(question, positions, self.provider)
            outcome = Outcome.SPLIT
        else:
            n = len(positions)
            yes_count = sum(1 for p in positions if p.vote is Vote.YES)
            is_unanimous = yes_count == n or yes_count == 0
            if is_unanimous:
                is_fragile = await detect_concurrence(question, positions, self.provider)
                outcome = Outcome.FRAGILE_AGREEMENT if is_fragile else Outcome.MAJORITY
                concurrence = is_fragile
            else:
                outcome = Outcome.MAJORITY

        return Record(
            id=str(uuid.uuid4()),
            created_at=datetime.now(UTC).isoformat(),
            question=question,
            tier=resolved_tier,
            positions=tuple(positions),
            outcome=outcome,
            crux=crux,
            concurrence=concurrence,
        )
