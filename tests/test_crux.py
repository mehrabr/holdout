"""Tests for protocol.crux -- crux extraction wiring.

Tests assert plumbing only: prompt loading, field population, response parsing,
and structural results. Semantic quality of the crux is out of scope.
"""

from __future__ import annotations

import pytest

from magi.protocol.crux import extract_crux
from magi.providers.fake import FakeProvider
from magi.types import Position, Vote

# ---- helpers ----------------------------------------------------------------

QUESTION = "Should we migrate the database to a new engine?"


def _pos(mandate: str, rationale: str, vote: str) -> Position:
    return Position(
        agent_name="agent",
        agent_mandate=mandate,
        rationale=rationale,
        vote=Vote(vote),
    )


SPLIT_POSITIONS = [
    _pos("reason from data", "Benchmarks show 2x throughput gains.", "yes"),
    _pos("reason from duty", "Migration risk outweighs performance gains.", "no"),
    _pos("reason from pattern", "Prior migrations at this scale caused downtime.", "no"),
]


# ---- basic wiring -----------------------------------------------------------


async def test_extract_crux_returns_nonempty_string() -> None:
    provider = FakeProvider(default="Would migration downtime violate our SLA commitments?")
    crux = await extract_crux(QUESTION, SPLIT_POSITIONS, provider)

    assert isinstance(crux, str)
    assert len(crux) > 0


async def test_extract_crux_returns_provider_response_stripped() -> None:
    expected = "Would the performance gains offset the risk of SLA violations?"
    provider = FakeProvider(default=f"  {expected}  \n")
    crux = await extract_crux(QUESTION, SPLIT_POSITIONS, provider)

    assert crux == expected


async def test_extract_crux_makes_exactly_one_provider_call() -> None:
    provider = FakeProvider(default="A crux question.")
    await extract_crux(QUESTION, SPLIT_POSITIONS, provider)

    assert len(provider.calls) == 1


# ---- prompt content ---------------------------------------------------------


async def test_crux_prompt_contains_question() -> None:
    provider = FakeProvider(default="Crux text.")
    await extract_crux(QUESTION, SPLIT_POSITIONS, provider)

    assert QUESTION in provider.calls[0]


async def test_crux_prompt_contains_all_rationales() -> None:
    provider = FakeProvider(default="Crux text.")
    await extract_crux(QUESTION, SPLIT_POSITIONS, provider)

    prompt = provider.calls[0]
    for pos in SPLIT_POSITIONS:
        assert pos.rationale in prompt, f"rationale for '{pos.agent_mandate}' missing from prompt"


async def test_crux_prompt_contains_all_mandates() -> None:
    provider = FakeProvider(default="Crux text.")
    await extract_crux(QUESTION, SPLIT_POSITIONS, provider)

    prompt = provider.calls[0]
    for pos in SPLIT_POSITIONS:
        assert pos.agent_mandate in prompt, f"mandate '{pos.agent_mandate}' missing from prompt"


async def test_crux_prompt_contains_votes() -> None:
    provider = FakeProvider(default="Crux text.")
    await extract_crux(QUESTION, SPLIT_POSITIONS, provider)

    prompt = provider.calls[0]
    assert "YES" in prompt or "NO" in prompt


# ---- no peer injection (neutrality) -----------------------------------------


async def test_crux_prompt_does_not_contain_agent_names() -> None:
    """The neutral crux pass identifies agents by mandate and vote only, not name."""
    positions = [
        _pos("mandate_for_alpha", "Alpha unique rationale.", "yes"),
        _pos("mandate_for_beta", "Beta unique rationale.", "no"),
        _pos("mandate_for_gamma", "Gamma unique rationale.", "no"),
    ]
    provider = FakeProvider(default="Crux text.")
    await extract_crux(QUESTION, positions, provider)

    prompt = provider.calls[0]
    # agent names (set on the Position but should not appear in prompt)
    assert "agent" not in prompt.lower() or "agent_mandate" not in prompt


# ---- error handling ---------------------------------------------------------


async def test_extract_crux_raises_on_empty_response() -> None:
    provider = FakeProvider(default="   \n  ")
    with pytest.raises(ValueError, match="empty crux"):
        await extract_crux(QUESTION, SPLIT_POSITIONS, provider)
