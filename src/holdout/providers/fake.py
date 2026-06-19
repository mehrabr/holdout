"""Deterministic provider for tests.

`FakeProvider` is part of the contract, not an afterthought: it is how the entire
engine is exercised without a network. Tests script its responses by matching on
substrings of the prompt, so a test can stage any panel outcome -- unanimous, split,
fragile agreement -- with full determinism and zero latency.

It also records every prompt it received, which is how the blind-commitment invariant
is tested: after a deliberation, a test inspects `calls` and asserts that no agent's
prompt contained any peer's rationale.

For multimodal (vision) calls, `content_calls` stores the raw content (str or list of
parts). `calls` always stores the extracted text portion, so existing string-based
tests -- including the surveillance tests -- continue to work without modification.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from holdout.providers.base import MessageContent


def _extract_text(content: MessageContent) -> str:
    """Return the text portion of a content value for rule matching and recording."""
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "text":
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
    return " ".join(parts)


@dataclass
class FakeProvider:
    """A scripted, inspectable Provider implementation.

    Args:
        rules: ordered (needle, response) pairs. The first rule whose `needle` is a
            substring of the prompt text wins. Use this to give each agent mandate a
            distinct scripted answer.
        default: returned when no rule matches.
    """

    rules: list[tuple[str, str]] = field(default_factory=list)
    default: str = ""
    calls: list[str] = field(default_factory=list)
    content_calls: list[MessageContent] = field(default_factory=list)

    async def complete(self, content: MessageContent) -> str:
        # Extract text for rule matching; record both text (for surveillance tests)
        # and the raw content (for vision-path inspection).
        text = _extract_text(content)
        self.calls.append(text)
        self.content_calls.append(content)
        for needle, response in self.rules:
            if needle in text:
                return response
        return self.default

    # ── convenience for assertions ──

    def prompts_containing(self, needle: str) -> list[str]:
        """Every recorded prompt that contains `needle`."""
        return [p for p in self.calls if needle in p]

    def any_prompt_contains(self, needle: str) -> bool:
        return any(needle in p for p in self.calls)

    def any_call_is_multimodal(self) -> bool:
        """True if any call was sent as a list of content parts (vision path)."""
        return any(isinstance(c, list) for c in self.content_calls)
