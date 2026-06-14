"""The provider seam.

A `Provider` is the only thing in MAGI that touches the network. Everything else --
the protocol, the store, the report -- depends on this interface, not on any concrete
provider. That single seam is what makes the entire deliberation engine testable
offline, deterministically, with no API key.

There is exactly one method. Keeping the interface this narrow is deliberate: it is
the whole contract the engine needs, and a narrow contract is a stable one.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Provider(Protocol):
    """A text-completion endpoint.

    Implementations must be safe to call concurrently: the blind-commitment step
    fans out N agent calls in parallel and awaits them together.
    """

    async def complete(self, prompt: str) -> str:
        """Return the model's completion for `prompt`.

        Implementations should raise on transport or API failure rather than
        returning a sentinel, so the engine can surface the error rather than
        record a malformed position.
        """
        ...
