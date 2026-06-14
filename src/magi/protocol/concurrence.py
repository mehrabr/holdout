"""Concurrence detection: fragile-agreement identification on unanimous outcomes.

`detect_concurrence(question, positions, provider)` is a single neutral LLM call.
It reads all rationales from a unanimous deliberation and determines whether the
shared position rests on compatible reasons (CONVERGENT → plain MAJORITY) or
incompatible ones (FRAGILE → FRAGILE_AGREEMENT).

Called only when tabulate returned MAJORITY and the vote was unanimous. Never called
on SPLIT outcomes.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from magi.providers.base import Provider
from magi.types import Position

_PROMPT = (Path(__file__).parents[3] / "prompts" / "concurrence.txt").read_text()

_ASSESSMENT_RE = re.compile(r"\bASSESSMENT:\s*(CONVERGENT|FRAGILE)\b", re.IGNORECASE)


def _format_rationales(positions: Sequence[Position]) -> str:
    parts = []
    for p in positions:
        parts.append(f"[Mandate: {p.agent_mandate}]\n{p.rationale}")
    return "\n\n".join(parts)


async def detect_concurrence(
    question: str,
    positions: Sequence[Position],
    provider: Provider,
) -> bool:
    """Return True if the unanimous agreement is fragile (incompatible reasons).

    Makes exactly one provider call. Returns False for CONVERGENT (plain majority),
    True for FRAGILE (fragile agreement requiring the concurrence flag).
    """
    rationales = _format_rationales(positions)
    prompt = _PROMPT.format(question=question, rationales=rationales)
    response = await provider.complete(prompt)
    return _parse(response)


def _parse(response: str) -> bool:
    matches = list(_ASSESSMENT_RE.finditer(response))
    if not matches:
        raise ValueError(
            f"no ASSESSMENT: CONVERGENT/FRAGILE marker in provider response: {response!r}"
        )
    last = matches[-1]
    return last.group(1).upper() == "FRAGILE"
