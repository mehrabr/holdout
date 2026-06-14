"""Deterministic provider for tests.

`FakeProvider` is part of the contract, not an afterthought: it is how the entire
engine is exercised without a network. Tests script its responses by matching on
substrings of the prompt, so a test can stage any panel outcome -- unanimous, split,
fragile agreement -- with full determinism and zero latency.

It also records every prompt it received, which is how the blind-commitment invariant
is tested: after a deliberation, a test inspects `calls` and asserts that no agent's
prompt contained any peer's rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FakeProvider:
    """A scripted, inspectable Provider implementation.

    Args:
        rules: ordered (needle, response) pairs. The first rule whose `needle` is a
            substring of the prompt wins. Use this to give each agent mandate a
            distinct scripted answer.
        default: returned when no rule matches.
    """

    rules: list[tuple[str, str]] = field(default_factory=list)
    default: str = ""
    calls: list[str] = field(default_factory=list)

    async def complete(self, prompt: str) -> str:
        # Record every prompt verbatim for later inspection (blind-commitment tests).
        self.calls.append(prompt)
        for needle, response in self.rules:
            if needle in prompt:
                return response
        return self.default

    # ── convenience for assertions ──

    def prompts_containing(self, needle: str) -> list[str]:
        """Every recorded prompt that contains `needle`."""
        return [p for p in self.calls if needle in p]

    def any_prompt_contains(self, needle: str) -> bool:
        return any(needle in p for p in self.calls)
