"""Blind commitment: parallel fan-out, one agent per call.

`commit(question, agent, provider)` is the atomic unit. It takes exactly ONE
agent — never the panel, never a list of peer rationales. There is no parameter
through which peer output could enter.

`gather(question, agents, provider)` dispatches commit() for every agent via
asyncio.TaskGroup, so all N calls are in-flight before any returns. No call can
depend on another's result because no result exists when the calls start.

`images` is an optional list of paths or URLs attached as shared visual context.
It is identical for every agent, so it cannot carry any peer's output; the
blind-commitment invariant is unaffected.
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import re
from collections.abc import Sequence
from importlib.resources import files
from pathlib import Path

from holdout.providers.base import MessageContent, Provider
from holdout.types import Agent, Position, Vote

_PROMPT = (files("holdout") / "prompts" / "commit.txt").read_text(encoding="utf-8")


# ── image helpers ─────────────────────────────────────────────────────────────


def _image_part(src: str) -> dict[str, object]:
    """Build one OpenAI-style image_url content part from a path or URL."""
    if src.startswith(("http://", "https://")):
        return {"type": "image_url", "image_url": {"url": src}}
    p = Path(src)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def _build_content(text: str, images: Sequence[str]) -> MessageContent:
    """Return a plain string when there are no images (text-only path unchanged).

    When images are present, return a list of content parts: one text part
    followed by one image_url part per image. The text-only path produces output
    byte-identical to the pre-vision code path.
    """
    if not images:
        return text
    return [{"type": "text", "text": text}, *(_image_part(src) for src in images)]


# ── protocol steps ────────────────────────────────────────────────────────────


async def commit(
    question: str,
    agent: Agent,
    provider: Provider,
    images: Sequence[str] = (),
) -> Position:
    """Produce one agent's blind commitment.

    Takes exactly one agent — never the panel, never peer rationales.
    `images` is shared visual context; it is identical for every agent and is
    therefore not a channel through which peer output could travel.
    """
    prompt = _PROMPT.format(mandate=agent.mandate, question=question)
    content = _build_content(prompt, images)
    response = await provider.complete(content)
    rationale, vote = _parse(response)
    return Position(
        agent_name=agent.name,
        agent_mandate=agent.mandate,
        rationale=rationale,
        vote=vote,
    )


async def gather(
    question: str,
    agents: Sequence[Agent],
    provider: Provider,
    images: Sequence[str] = (),
) -> list[Position]:
    """Dispatch all agent commits concurrently; await them together.

    Uses asyncio.TaskGroup so all N coroutines are scheduled before any
    completes. Order of returned positions matches order of input agents.
    """
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(commit(question, a, provider, images)) for a in agents]
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
