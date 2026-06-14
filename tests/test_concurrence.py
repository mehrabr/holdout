"""Tests for protocol.concurrence -- fragile-agreement detection wiring.

Tests assert plumbing: prompt loading, field population, response parsing, and
that the correct bool is returned. Semantic quality of the detection is out of scope.

Property tests:
  - CONVERGENT response -> False (plain MAJORITY, no flag)
  - FRAGILE response    -> True  (FRAGILE_AGREEMENT, flag set)
"""

from __future__ import annotations

import pytest

from magi.protocol.concurrence import detect_concurrence
from magi.providers.fake import FakeProvider
from magi.types import Position, Vote

# ---- helpers ----------------------------------------------------------------

QUESTION = "Should we adopt this new dependency?"


def _pos(mandate: str, rationale: str, vote: str = "yes") -> Position:
    return Position(
        agent_name="agent",
        agent_mandate=mandate,
        rationale=rationale,
        vote=Vote(vote),
    )


UNANIMOUS_YES = [
    _pos("reason from data", "Benchmarks show clear gains.", "yes"),
    _pos("reason from duty", "Adopting reduces team cognitive load.", "yes"),
    _pos("reason from pattern", "Analogous projects succeeded with this dependency.", "yes"),
]

UNANIMOUS_NO = [
    _pos("reason from data", "No hard data supports adoption.", "no"),
    _pos("reason from duty", "Risk to users is non-trivial.", "no"),
    _pos("reason from pattern", "Similar adoptions caused long-term debt.", "no"),
]


# ---- parsing: CONVERGENT -> False -------------------------------------------


async def test_convergent_response_returns_false() -> None:
    provider = FakeProvider(default="The agents agree on the same basis.\nASSESSMENT: CONVERGENT")
    result = await detect_concurrence(QUESTION, UNANIMOUS_YES, provider)

    assert result is False


async def test_convergent_case_insensitive() -> None:
    provider = FakeProvider(default="analysis\nassessment: convergent")
    result = await detect_concurrence(QUESTION, UNANIMOUS_YES, provider)

    assert result is False


# ---- parsing: FRAGILE -> True -----------------------------------------------


async def test_fragile_response_returns_true() -> None:
    provider = FakeProvider(default="The rationales contradict each other.\nASSESSMENT: FRAGILE")
    result = await detect_concurrence(QUESTION, UNANIMOUS_YES, provider)

    assert result is True


async def test_fragile_case_insensitive() -> None:
    provider = FakeProvider(default="analysis\nassessment: fragile")
    result = await detect_concurrence(QUESTION, UNANIMOUS_YES, provider)

    assert result is True


async def test_takes_last_assessment_marker() -> None:
    """If multiple ASSESSMENT: lines appear, the last one is binding."""
    provider = FakeProvider(
        default="Initially ASSESSMENT: FRAGILE but on reflection\nASSESSMENT: CONVERGENT"
    )
    result = await detect_concurrence(QUESTION, UNANIMOUS_YES, provider)

    assert result is False


# ---- basic wiring -----------------------------------------------------------


async def test_detect_concurrence_makes_exactly_one_provider_call() -> None:
    provider = FakeProvider(default="analysis\nASSESSMENT: CONVERGENT")
    await detect_concurrence(QUESTION, UNANIMOUS_YES, provider)

    assert len(provider.calls) == 1


async def test_detect_concurrence_works_for_unanimous_no() -> None:
    provider = FakeProvider(default="analysis\nASSESSMENT: FRAGILE")
    result = await detect_concurrence(QUESTION, UNANIMOUS_NO, provider)

    assert result is True


# ---- prompt content ---------------------------------------------------------


async def test_concurrence_prompt_contains_question() -> None:
    provider = FakeProvider(default="analysis\nASSESSMENT: CONVERGENT")
    await detect_concurrence(QUESTION, UNANIMOUS_YES, provider)

    assert QUESTION in provider.calls[0]


async def test_concurrence_prompt_contains_all_rationales() -> None:
    provider = FakeProvider(default="analysis\nASSESSMENT: CONVERGENT")
    await detect_concurrence(QUESTION, UNANIMOUS_YES, provider)

    prompt = provider.calls[0]
    for pos in UNANIMOUS_YES:
        assert pos.rationale in prompt, f"rationale for '{pos.agent_mandate}' missing from prompt"


async def test_concurrence_prompt_contains_all_mandates() -> None:
    provider = FakeProvider(default="analysis\nASSESSMENT: CONVERGENT")
    await detect_concurrence(QUESTION, UNANIMOUS_YES, provider)

    prompt = provider.calls[0]
    for pos in UNANIMOUS_YES:
        assert pos.agent_mandate in prompt, f"mandate '{pos.agent_mandate}' missing from prompt"


# ---- error handling ---------------------------------------------------------


async def test_missing_assessment_marker_raises() -> None:
    provider = FakeProvider(default="Some analysis with no assessment marker.")
    with pytest.raises(ValueError, match="ASSESSMENT"):
        await detect_concurrence(QUESTION, UNANIMOUS_YES, provider)


async def test_invalid_assessment_value_raises() -> None:
    provider = FakeProvider(default="ASSESSMENT: UNCERTAIN")
    with pytest.raises(ValueError, match="ASSESSMENT"):
        await detect_concurrence(QUESTION, UNANIMOUS_YES, provider)
