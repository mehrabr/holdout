"""OpenAI-compatible provider via async httpx.

The only module that touches the network. Satisfies the Provider protocol:
one async complete() method, safe for concurrent calls.

A single AsyncClient is shared across concurrent complete() calls;
httpx.AsyncClient is safe for concurrent async use without additional locking.
"""

from __future__ import annotations

import httpx

_DEFAULT_TIMEOUT = 60.0


class OpenAICompatProvider:
    """Async provider for any OpenAI-compatible /chat/completions endpoint.

    Args:
        base_url: API root, e.g. ``"https://api.openai.com/v1"``.
        api_key:  Bearer token sent in the ``Authorization`` header.
        model:    Model name forwarded in every request body.
        timeout:  Per-request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def complete(self, prompt: str) -> str:
        """POST to /chat/completions; return the assistant message text.

        Raises ``httpx.HTTPStatusError`` on 4xx/5xx responses.
        Raises ``httpx.TimeoutException`` when the request times out.
        """
        response = await self._client.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])

    async def aclose(self) -> None:
        """Release the underlying HTTP client."""
        await self._client.aclose()
