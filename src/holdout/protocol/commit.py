"""Blind commitment: parallel fan-out, one agent per call.

`commit(question, agent, provider)` is the atomic unit. It takes exactly ONE
agent — never the panel, never a list of peer rationales. There is no parameter
through which peer output could enter.

`gather(question, agents, provider)` dispatches commit() for every agent via
asyncio.TaskGroup, so all N calls are in-flight before any returns. No call can
depend on another's result because no result exists when the calls start.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from importlib.resources import files

from holdout.providers.base import Provider
from holdout.types import Agent, Position, Vote

_PROMPT = (files("holdout") / "prompts" / "commit.txt").read_text(encoding="utf-8")


async def commit(question: str, agent: Agent, provider: Provider) -> Position:
    """Produce one agent's blind commitment.

    Takes exactly one agent — never the panel, never peer rationales.
    """
    prompt = _PROMPT.format(mandate=agent.mandate, question=question)
    response = await provider.complete(prompt)
    rationale, vote = _parse(response)
    return Position(
        agent_name=agent.name,
        agent_mandate=agent.mandate,
        rationale=rationale,
        vote=vote,
    )


async def gather(question: str, agents: Sequence[Agent], provider: Provider) -> list[Position]:
    """Dispatch all agent commits concurrently; await them together.

    Uses asyncio.TaskGroup so all N coroutines are scheduled before any
    completes. Order of returned positions matches order of input agents.
    """
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(commit(question, a, provider)) for a in agents]
    return [t.result() for t in tasks]


_VOTE_RE = re.compile(r"\bVOTE:\s*(YES|NO)\b", re.IGNORECASE)


def _parse(response: str) -> tuple[str, Vote]:
    """Extract (rationale, vote) from a provider response.

    The last VOTE: YES/NO line is the binding position. Everything before it
    is the rationale. Raises ValueError if either is absent.
    """
    matches = list(_VOTE_RE.finditer(response))
    if not matches:
        raise ValueError(f"no VOTE: YES/NO marker in provider response: {response!r}")
    last = matches[-1]
    rationale = response[: last.start()].strip()
    if not rationale:
        raise ValueError("provider response has no rationale before the VOTE marker")
    return rationale, Vote(last.group(1).lower())
