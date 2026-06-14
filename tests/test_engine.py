"""Tests for protocol.engine -- full-panel orchestration.

Integration tests run against FakeProvider (offline, deterministic).
All network seams are bypassed; the only production code under test is
the engine's orchestration of gather → tabulate → crux/concurrence → Record.

FakeProvider rule ordering note:
  Crux and concurrence prompts include "[Mandate:" (from _format_rationales).
  Commit prompts do NOT (the template says "the following mandate:", not "[Mandate:").
  Placing a "[Mandate:" rule first in the rules list lets us script crux/concurrence
  responses without the rule accidentally matching commit calls.
"""

from __future__ import annotations

import re

from magi.protocol.engine import Panel
from magi.providers.fake import FakeProvider
from magi.types import Agent, Outcome, Record, Tier, Vote

# ─────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

QUESTION = "Should we adopt this new service?"

AGENTS_3 = [
    Agent(name="empirical", mandate="reason from data and evidence"),
    Agent(name="principled", mandate="reason from duty and stakeholder interests"),
    Agent(name="practitioner", mandate="reason from pattern and prior cases"),
]

_CRUX_TEXT = "Would the performance gains offset the migration risk?"
_CONVERGENT_RESPONSE = "Reasons reinforce each other.\nASSESSMENT: CONVERGENT"
_FRAGILE_RESPONSE = "Reasons contradict each other.\nASSESSMENT: FRAGILE"


def _provider_2_1_yes(*, crux_response: str = _CRUX_TEXT) -> FakeProvider:
    """3-agent panel: 2 YES (empirical, principled), 1 NO (practitioner).

    The "[Mandate:" rule is first so it catches crux/concurrence calls.
    Commit prompts never contain "[Mandate:" so they fall through to mandate rules.
    """
    return FakeProvider(
        rules=[
            ("[Mandate:", crux_response),
            ("reason from data and evidence", "Data supports adoption.\nVOTE: YES"),
            ("reason from duty and stakeholder interests", "Duty supports adoption.\nVOTE: YES"),
            ("reason from pattern and prior cases", "Prior cases advise caution.\nVOTE: NO"),
        ],
    )


def _provider_unanimous_yes(*, concurrence_response: str = _CONVERGENT_RESPONSE) -> FakeProvider:
    """3-agent panel: all YES."""
    return FakeProvider(
        rules=[
            ("[Mandate:", concurrence_response),
            ("reason from data and evidence", "Data supports.\nVOTE: YES"),
            ("reason from duty and stakeholder interests", "Duty supports.\nVOTE: YES"),
            ("reason from pattern and prior cases", "Pattern supports.\nVOTE: YES"),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Outcome routing: two-tier handling
# ─────────────────────────────────────────────────────────────────────────────


async def test_reversible_non_unanimous_majority_gives_majority() -> None:
    """REVERSIBLE + 2-1 vote → MAJORITY (simple majority threshold met)."""
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    assert record.outcome is Outcome.MAJORITY
    assert record.crux is None
    assert record.concurrence is False


async def test_hard_to_reverse_non_unanimous_gives_split() -> None:
    """HARD_TO_REVERSE + 2-1 vote → SPLIT (unanimity required but not met)."""
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier=Tier.HARD_TO_REVERSE)

    assert record.outcome is Outcome.SPLIT
    assert record.crux is not None
    assert record.crux != ""


async def test_hard_to_reverse_split_attaches_crux() -> None:
    """On SPLIT the crux from extract_crux is stored on the record verbatim."""
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes(crux_response=_CRUX_TEXT))
    record = await panel.deliberate(QUESTION, tier=Tier.HARD_TO_REVERSE)

    assert record.crux == _CRUX_TEXT


async def test_unanimous_convergent_gives_majority() -> None:
    """Unanimous + CONVERGENT concurrence → plain MAJORITY, no flag."""
    provider = _provider_unanimous_yes(concurrence_response=_CONVERGENT_RESPONSE)
    panel = Panel(AGENTS_3, provider=provider)
    record = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    assert record.outcome is Outcome.MAJORITY
    assert record.concurrence is False
    assert record.crux is None


async def test_unanimous_fragile_gives_fragile_agreement() -> None:
    """Unanimous + FRAGILE concurrence → FRAGILE_AGREEMENT, concurrence flag set."""
    provider = _provider_unanimous_yes(concurrence_response=_FRAGILE_RESPONSE)
    panel = Panel(AGENTS_3, provider=provider)
    record = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    assert record.outcome is Outcome.FRAGILE_AGREEMENT
    assert record.concurrence is True
    assert record.crux is None


async def test_hard_to_reverse_unanimous_calls_concurrence() -> None:
    """HARD_TO_REVERSE + unanimous → still runs concurrence detection."""
    provider = _provider_unanimous_yes(concurrence_response=_FRAGILE_RESPONSE)
    panel = Panel(AGENTS_3, provider=provider)
    record = await panel.deliberate(QUESTION, tier=Tier.HARD_TO_REVERSE)

    assert record.outcome is Outcome.FRAGILE_AGREEMENT


# ─────────────────────────────────────────────────────────────────────────────
# Caller-asserted tier
# ─────────────────────────────────────────────────────────────────────────────


async def test_tier_accepted_as_string() -> None:
    """deliberate() accepts the tier as a plain string (caller convenience)."""
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier="reversible")

    assert record.tier is Tier.REVERSIBLE


async def test_tier_hard_to_reverse_accepted_as_string() -> None:
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier="hard_to_reverse")

    assert record.tier is Tier.HARD_TO_REVERSE
    assert record.outcome is Outcome.SPLIT


async def test_tier_stored_on_record() -> None:
    """The tier the caller asserted is stored verbatim on the record."""
    panel = Panel(AGENTS_3, provider=_provider_unanimous_yes())
    record = await panel.deliberate(QUESTION, tier=Tier.HARD_TO_REVERSE)

    assert record.tier is Tier.HARD_TO_REVERSE


# ─────────────────────────────────────────────────────────────────────────────
# Record fields and verbatim preservation
# ─────────────────────────────────────────────────────────────────────────────


async def test_record_has_nonempty_id() -> None:
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    assert record.id != ""


async def test_record_id_is_unique_across_runs() -> None:
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    r1 = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)
    r2 = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    assert r1.id != r2.id


async def test_record_created_at_is_iso8601() -> None:
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    # ISO 8601: YYYY-MM-DDTHH:MM:SS
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", record.created_at)


async def test_record_question_verbatim() -> None:
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    assert record.question == QUESTION


async def test_record_positions_count() -> None:
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    assert len(record.positions) == len(AGENTS_3)


async def test_record_positions_preserve_rationale_verbatim() -> None:
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    rationale_texts = {p.rationale for p in record.positions}
    assert "Data supports adoption." in rationale_texts
    assert "Duty supports adoption." in rationale_texts
    assert "Prior cases advise caution." in rationale_texts


async def test_record_positions_preserve_mandate_verbatim() -> None:
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    mandates = {p.agent_mandate for p in record.positions}
    assert mandates == {a.mandate for a in AGENTS_3}


# ─────────────────────────────────────────────────────────────────────────────
# Minority preservation (Invariant I: dissent preserved verbatim)
# ─────────────────────────────────────────────────────────────────────────────


async def test_minority_preserved_on_majority() -> None:
    """The losing position is preserved verbatim in record.minority."""
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    assert record.prevailing is Vote.YES
    minority = record.minority
    assert len(minority) == 1
    assert minority[0].vote is Vote.NO
    assert minority[0].rationale == "Prior cases advise caution."


async def test_minority_is_full_position_objects_not_summaries() -> None:
    """record.minority returns the original Position objects, byte-for-byte."""
    panel = Panel(AGENTS_3, provider=_provider_2_1_yes())
    record = await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    minority = record.minority
    assert all(p in record.positions for p in minority)


# ─────────────────────────────────────────────────────────────────────────────
# Provider call counts (verify exactly the right steps are called)
# ─────────────────────────────────────────────────────────────────────────────


async def test_reversible_non_unanimous_makes_n_calls() -> None:
    """REVERSIBLE + non-unanimous majority: only N commit calls, no crux/concurrence."""
    provider = _provider_2_1_yes()
    panel = Panel(AGENTS_3, provider=provider)
    await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    assert len(provider.calls) == len(AGENTS_3)


async def test_split_makes_n_plus_one_calls() -> None:
    """SPLIT: N commit calls + 1 crux call."""
    provider = _provider_2_1_yes()
    panel = Panel(AGENTS_3, provider=provider)
    await panel.deliberate(QUESTION, tier=Tier.HARD_TO_REVERSE)

    assert len(provider.calls) == len(AGENTS_3) + 1


async def test_unanimous_majority_makes_n_plus_one_calls() -> None:
    """Unanimous: N commit calls + 1 concurrence call."""
    provider = _provider_unanimous_yes()
    panel = Panel(AGENTS_3, provider=provider)
    await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    assert len(provider.calls) == len(AGENTS_3) + 1


# ─────────────────────────────────────────────────────────────────────────────
# Invariant I — no synthesis (structural)
# ─────────────────────────────────────────────────────────────────────────────


def test_record_has_no_synthesis_field() -> None:
    """Record exposes no field that could hold a merged or synthesized answer.

    This is a structural guard: if synthesis were added, the field would have to
    appear here, making the violation visible in a diff.
    """
    forbidden = {"synthesis", "answer", "final", "summary", "consensus", "verdict_text", "merged"}
    record_fields = set(Record.model_fields.keys())
    overlap = forbidden & record_fields
    assert not overlap, (
        f"Record has field(s) that could carry a synthesized answer: {overlap}. "
        "Adding such a field violates Invariant I (no synthesis)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Invariant II — blind commitment (via Panel.deliberate)
# ─────────────────────────────────────────────────────────────────────────────


async def test_blind_commitment_no_peer_sentinel_in_commit_prompts() -> None:
    """After deliberate(), no commit prompt may contain a peer's rationale sentinel.

    Sentinels exist only in the scripted responses. If one appears in a commit
    prompt, a peer's rationale was injected — Invariant II violated.
    """
    SENT_E = "XSENT_ENGINE_7734_EMP"
    SENT_P = "XSENT_ENGINE_8821_PRI"
    SENT_R = "XSENT_ENGINE_9912_PRA"

    provider = FakeProvider(
        rules=[
            ("[Mandate:", "Neutral crux.\nASSESSMENT: CONVERGENT"),
            ("reason from data and evidence", f"Empirical says yes. {SENT_E}\nVOTE: YES"),
            ("reason from duty and stakeholder interests", f"Principled yes. {SENT_P}\nVOTE: YES"),
            ("reason from pattern and prior cases", f"Practitioner says yes. {SENT_R}\nVOTE: YES"),
        ],
    )
    panel = Panel(AGENTS_3, provider=provider)
    await panel.deliberate(QUESTION, tier=Tier.REVERSIBLE)

    # Identify commit calls: they do NOT contain "[Mandate:" (crux/concurrence do)
    commit_prompts = [p for p in provider.calls if "[Mandate:" not in p]
    assert len(commit_prompts) == len(AGENTS_3), "expected exactly N commit prompts"

    all_sentinels = {SENT_E, SENT_P, SENT_R}
    for i, prompt in enumerate(commit_prompts):
        for sentinel in all_sentinels:
            assert sentinel not in prompt, (
                f"commit_prompt[{i}] contains sentinel {sentinel!r} — "
                "this token only exists in a peer's response; peer output was injected "
                "(Invariant II violated)"
            )
