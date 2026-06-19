"""The provider seam.

A `Provider` is the only thing in holdout that touches the network. Everything else --
the protocol, the store, the report -- depends on this interface, not on any concrete
provider. That single seam is what makes the entire deliberation engine testable
offline, deterministically, with no API key.

There is exactly one method. Keeping the interface this narrow is deliberate: it is
the whole contract the engine needs, and a narrow contract is a stable one.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# A message can be plain text or a list of content parts (text + images) in the
# OpenAI vision format. The text-only path sends a str; the multimodal path sends
# a list with at least one {"type": "text"} part and one or more {"type":
# "image_url"} parts. Providers must accept both forms.
MessageContent = str | list[dict[str, object]]


@runtime_checkable
class Provider(Protocol):
    """A text- or vision-completion endpoint.

    Implementations must be safe to call concurrently: the blind-commitment step
    fans out N agent calls in parallel and awaits them together.
    """

    async def complete(self, content: MessageContent) -> str:
        """Return the model's completion for `content`.

        `content` is either a plain text string (text-only path) or a list of
        OpenAI-style content parts (multimodal path). Implementations should
        raise on transport or API failure rather than returning a sentinel, so
        the engine can surface the error rather than record a malformed position.
        """
        ...
