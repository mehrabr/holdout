"""Crux extraction: consequence-anchored question on a split outcome.

`extract_crux(question, positions, provider)` is a single neutral LLM call —
not one of the N agents. It reads all rationales and returns the one falsifiable
question whose resolution would most likely change the outcome. The crux names
the adverse consequence the minority is reasoning about, not merely the locus of
disagreement.

Called only on SPLIT outcomes (tabulate returned SPLIT). Never called on MAJORITY
or FRAGILE_AGREEMENT.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from holdout.providers.base import Provider
from holdout.types import Position

_PROMPT = (Path(__file__).parents[3] / "prompts" / "crux.txt").read_text()


def _format_rationales(positions: Sequence[Position]) -> str:
    parts = []
    for p in positions:
        parts.append(f"[Mandate: {p.agent_mandate}] [Vote: {p.vote.upper()}]\n{p.rationale}")
    return "\n\n".join(parts)


async def extract_crux(
    question: str,
    positions: Sequence[Position],
    provider: Provider,
) -> str:
    """Return a consequence-anchored crux for a split deliberation.

    Makes exactly one provider call. The prompt never contains agent names —
    only mandates and rationales — to preserve neutrality.
    """
    rationales = _format_rationales(positions)
    prompt = _PROMPT.format(question=question, rationales=rationales)
    response = await provider.complete(prompt)
    crux = response.strip()
    if not crux:
        raise ValueError("provider returned an empty crux")
    return crux
