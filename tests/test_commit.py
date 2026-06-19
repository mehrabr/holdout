"""Tests for protocol.commit -- blind commitment fan-out.

Three invariant tests are non-negotiable (see CLAUDE.md):
  - SIGNATURE:    commit() takes exactly one agent, with no parameter for peer output.
  - SURVEILLANCE: after gather(), no agent's prompt contains a peer's rationale sentinel.
  - CONCURRENCY:  all N calls are in-flight before any returns.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from typing import get_type_hints

import pytest

from holdout.protocol.commit import commit, gather
from holdout.providers.fake import FakeProvider
from holdout.types import Agent, Position, Vote

# ---- fixtures ----------------------------------------------------------------

QUESTION = "Should we adopt this architecture?"

AGENTS_3 = [
    Agent(name="alpha", mandate="reason from data and evidence"),
    Agent(name="beta", mandate="reason from duty and stakeholder interests"),
    Agent(name="gamma", mandate="reason from pattern and prior cases"),
]


def _agent(name: str, mandate: str) -> Agent:
    return Agent(name=name, mandate=mandate)


def _provider(
    *rules: tuple[str, str],
    default: str = "Fallback rationale.\nVOTE: YES",
) -> FakeProvider:
    return FakeProvider(rules=list(rules), default=default)


# ---- signature test (INVARIANT II) ------------------------------------------


def test_commit_signature_takes_exactly_one_agent() -> None:
    """commit() must accept one Agent, never a collection or a peer-output parameter.

    `images` is permitted as shared visual context; it is identical for every agent
    and cannot carry peer output. The forbidden set covers any name that could be
    used to pass one agent's output to another.
    """
    sig = inspect.signature(commit)
    params = list(sig.parameters.keys())

    assert params == ["question", "agent", "provider", "images"], (
        f"commit() parameters are {params!r} -- "
        "expected ['question', 'agent', 'provider', 'images']"
    )

    hints = get_type_hints(commit)
    assert hints["agent"] is Agent, (
        f"commit()'s agent parameter is typed as {hints['agent']!r}, not Agent -- "
        "a collection type here would allow the panel to be passed"
    )

    forbidden = {"agents", "peers", "panel", "rationales", "peer_output"}
    for name in forbidden:
        assert name not in params, (
            f"commit() has a '{name}' parameter -- this opens a path for peer output injection"
        )


# ---- basic commit behaviour --------------------------------------------------


async def test_commit_returns_position_for_yes() -> None:
    agent = _agent("empirical", "reason from data")
    provider = _provider(("reason from data", "Data supports this.\nVOTE: YES"))

    pos = await commit(QUESTION, agent, provider)

    assert isinstance(pos, Position)
    assert pos.agent_name == "empirical"
    assert pos.agent_mandate == "reason from data"
    assert pos.vote is Vote.YES
    assert "Data supports this" in pos.rationale


async def test_commit_returns_position_for_no() -> None:
    agent = _agent("principled", "reason from duty")
    provider = _provider(("reason from duty", "Duty forbids this.\nVOTE: NO"))

    pos = await commit(QUESTION, agent, provider)

    assert pos.vote is Vote.NO
    assert "Duty forbids this" in pos.rationale


async def test_commit_prompt_contains_mandate_and_question() -> None:
    """The prompt sent to the provider must contain both the mandate and the question."""
    agent = _agent("practitioner", "reason from pattern")
    provider = _provider(default="Some analysis.\nVOTE: YES")

    await commit(QUESTION, agent, provider)

    assert len(provider.calls) == 1
    prompt = provider.calls[0]
    assert "reason from pattern" in prompt, "mandate missing from prompt"
    assert QUESTION in prompt, "question missing from prompt"


async def test_commit_prompt_contains_only_own_mandate() -> None:
    """The prompt must not contain any peer mandate -- only the agent's own."""
    agent = _agent("alpha", "unique_alpha_mandate")
    provider = _provider(default="Rationale.\nVOTE: YES")

    await commit(QUESTION, agent, provider)

    prompt = provider.calls[0]
    assert "beta_mandate" not in prompt
    assert "gamma_mandate" not in prompt


# ---- vote parsing ------------------------------------------------------------


async def test_vote_parsing_case_insensitive() -> None:
    agent = _agent("x", "some mandate")
    provider = _provider(default="My analysis.\nvote: yes")

    pos = await commit(QUESTION, agent, provider)
    assert pos.vote is Vote.YES


async def test_vote_parsing_takes_last_marker() -> None:
    """If multiple VOTE: lines appear, the last one is the binding position."""
    agent = _agent("x", "some mandate")
    provider = _provider(default="Initial thought VOTE: YES but reconsidered.\nVOTE: NO")

    pos = await commit(QUESTION, agent, provider)
    assert pos.vote is Vote.NO


async def test_missing_vote_marker_raises() -> None:
    agent = _agent("x", "some mandate")
    provider = _provider(default="Analysis with no vote marker at all.")

    with pytest.raises(ValueError, match="VOTE"):
        await commit(QUESTION, agent, provider)


async def test_empty_rationale_raises() -> None:
    agent = _agent("x", "some mandate")
    provider = _provider(default="VOTE: YES")

    with pytest.raises(ValueError, match="rationale"):
        await commit(QUESTION, agent, provider)


# ---- gather: panel-level fan-out --------------------------------------------


async def test_gather_returns_one_position_per_agent() -> None:
    provider = _provider(default="Analysis.\nVOTE: YES")
    positions = await gather(QUESTION, AGENTS_3, provider)

    assert len(positions) == len(AGENTS_3)
    assert all(isinstance(p, Position) for p in positions)


async def test_gather_preserves_agent_order() -> None:
    """Positions must be returned in the same order as the input agents."""
    provider = FakeProvider(
        rules=[
            ("reason from data", "Data says yes.\nVOTE: YES"),
            ("reason from duty", "Duty says no.\nVOTE: NO"),
            ("reason from pattern", "Pattern says yes.\nVOTE: YES"),
        ]
    )
    positions = await gather(QUESTION, AGENTS_3, provider)

    assert [p.agent_name for p in positions] == ["alpha", "beta", "gamma"]
    assert positions[0].vote is Vote.YES
    assert positions[1].vote is Vote.NO
    assert positions[2].vote is Vote.YES


# ---- concurrency test (INVARIANT II enforcement) ----------------------------


async def test_gather_dispatches_concurrently() -> None:
    """All N commit() calls must be in-flight before any returns.

    Method: each provider call sleeps for DELAY seconds. If sequential the
    total would be N*DELAY; if concurrent it should be ~DELAY.
    """
    DELAY = 0.05
    start_times: list[float] = []

    class _SlowProvider:
        async def complete(self, prompt: str) -> str:
            start_times.append(asyncio.get_running_loop().time())
            await asyncio.sleep(DELAY)
            return "Analysis here.\nVOTE: YES"

    agents = [_agent(f"a{i}", f"mandate_{i}") for i in range(3)]
    wall_start = time.monotonic()
    positions = await gather(QUESTION, agents, _SlowProvider())  # type: ignore[arg-type]
    elapsed = time.monotonic() - wall_start

    assert len(positions) == 3
    # Sequential would take >= 3*DELAY; concurrent takes ~DELAY
    assert elapsed < DELAY * 2.5, (
        f"gather() took {elapsed:.3f}s with DELAY={DELAY} -- expected ~{DELAY:.3f}s if concurrent"
    )
    # All calls started before any completed (spread < one delay period)
    spread = max(start_times) - min(start_times)
    assert spread < DELAY, (
        f"call start times spread over {spread:.3f}s -- "
        f"expected <{DELAY:.3f}s if all dispatched at once"
    )


# ---- surveillance test (INVARIANT II -- property, not example) --------------


async def test_blind_commitment_surveillance() -> None:
    """No agent's prompt may contain any peer's rationale sentinel.

    This tests the PROPERTY: it is structurally impossible for peer output to
    reach an agent's prompt. We embed unique sentinel tokens in the scripted
    rationale responses, then assert those tokens never appear in any prompt.

    If gather() were sequential and injected prior responses into subsequent
    agents' prompts, the sentinels would appear -- this test would catch that.
    """
    SENT_A = "XSENTINEL_7734_ALPHA"
    SENT_B = "XSENTINEL_8821_BETA"
    SENT_C = "XSENTINEL_9912_GAMMA"

    agents = [
        _agent("alpha", "alpha_mandate"),
        _agent("beta", "beta_mandate"),
        _agent("gamma", "gamma_mandate"),
    ]
    # Sentinels exist only in responses. Their presence in any prompt means
    # a peer's rationale was injected -- a direct Invariant II violation.
    provider = FakeProvider(
        rules=[
            ("alpha_mandate", f"Alpha analysis. {SENT_A}\nVOTE: YES"),
            ("beta_mandate", f"Beta analysis. {SENT_B}\nVOTE: NO"),
            ("gamma_mandate", f"Gamma analysis. {SENT_C}\nVOTE: YES"),
        ]
    )

    await gather(QUESTION, agents, provider)

    assert len(provider.calls) == 3, "expected exactly 3 provider calls"

    all_sentinels = {SENT_A, SENT_B, SENT_C}
    for i, prompt in enumerate(provider.calls):
        for sentinel in all_sentinels:
            assert sentinel not in prompt, (
                f"prompt[{i}] contains sentinel {sentinel!r} -- "
                "this token only exists in a peer's rationale response; "
                "its presence means peer output was injected (Invariant II violated)"
            )


# ---- vision (multimodal) path -----------------------------------------------


async def test_commit_with_url_image_sends_multimodal_content() -> None:
    """When an image URL is passed, the provider receives a list of content parts."""
    from holdout.providers.fake import FakeProvider

    agent = _agent("empirical", "reason from data")
    provider = FakeProvider(default="Looks good.\nVOTE: YES")
    url = "https://example.com/diagram.png"

    pos = await commit(QUESTION, agent, provider, images=[url])

    assert pos.vote is Vote.YES
    assert len(provider.content_calls) == 1
    content = provider.content_calls[0]
    assert isinstance(content, list), "vision call must produce a list of content parts"
    types = [part.get("type") for part in content if isinstance(part, dict)]
    assert "text" in types, "content list must include a text part"
    assert "image_url" in types, "content list must include an image_url part"
    # The image URL must appear verbatim in the image_url part
    assert any(
        isinstance(p, dict)
        and p.get("type") == "image_url"
        and isinstance(p.get("image_url"), dict)
        and p["image_url"].get("url") == url  # type: ignore[index]
        for p in content
    ), "image URL must appear verbatim in the content"


async def test_commit_without_images_sends_plain_string() -> None:
    """Text-only path: provider receives a plain str, not a list."""
    from holdout.providers.fake import FakeProvider

    agent = _agent("empirical", "reason from data")
    provider = FakeProvider(default="Analysis.\nVOTE: YES")

    await commit(QUESTION, agent, provider)

    assert len(provider.content_calls) == 1
    assert isinstance(provider.content_calls[0], str), (
        "text-only call must produce a plain string, not a list"
    )


async def test_gather_with_images_all_agents_receive_image() -> None:
    """Every agent in the panel must receive the shared image."""
    from holdout.providers.fake import FakeProvider

    url = "https://example.com/chart.png"
    provider = FakeProvider(default="Reasonable.\nVOTE: YES")

    await gather(QUESTION, AGENTS_3, provider, images=[url])

    assert len(provider.content_calls) == 3
    for i, content in enumerate(provider.content_calls):
        assert isinstance(content, list), f"agent {i} did not receive multimodal content"
        assert any(
            isinstance(p, dict)
            and p.get("type") == "image_url"
            and isinstance(p.get("image_url"), dict)
            and p["image_url"].get("url") == url  # type: ignore[index]
            for p in content
        ), f"agent {i} did not receive the shared image"


async def test_gather_without_images_all_calls_are_text_only() -> None:
    """Snapshot: with no images every agent receives a plain string (backward compat)."""
    from holdout.providers.fake import FakeProvider

    provider = FakeProvider(default="Fine.\nVOTE: YES")

    await gather(QUESTION, AGENTS_3, provider)

    assert all(isinstance(c, str) for c in provider.content_calls), (
        "text-only gather must send plain strings to every agent"
    )
