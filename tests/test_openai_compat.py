"""Tests for providers/openai_compat.py.

Offline tests use respx to intercept httpx. They verify:
  - Correct request shape (URL, model, messages structure, auth header).
  - Response parsing returns the assistant message content as a string.
  - HTTP 4xx/5xx errors raise httpx.HTTPStatusError.
  - Timeout errors propagate as httpx.TimeoutException.
  - Concurrent calls each get the correct, distinct response.

Live test (opt-in, -m live): sends a real completion to a configured endpoint.
Requires env vars MAGI_API_KEY, MAGI_BASE_URL, MAGI_MODEL.
"""

from __future__ import annotations

import asyncio
import json
import os

import httpx
import pytest
import respx

from holdout.providers.openai_compat import OpenAICompatProvider

_BASE_URL = "https://api.test.local/v1"
_API_KEY = "sk-test-key-abc"
_MODEL = "test-model-7b"
_CHAT_URL = f"{_BASE_URL}/chat/completions"


def _provider() -> OpenAICompatProvider:
    return OpenAICompatProvider(base_url=_BASE_URL, api_key=_API_KEY, model=_MODEL)


def _chat_json(content: str) -> dict[str, object]:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


# ─────────────────────────────────────────────────────────────────────────────
# Request shape
# ─────────────────────────────────────────────────────────────────────────────


@respx.mock
async def test_posts_to_chat_completions_endpoint() -> None:
    route = respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, json=_chat_json("hello")))
    p = _provider()
    await p.complete("Hello")
    await p.aclose()
    assert route.called


@respx.mock
async def test_request_body_model_and_messages() -> None:
    route = respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, json=_chat_json("hi")))
    p = _provider()
    await p.complete("Say hi")
    await p.aclose()
    payload = json.loads(route.calls.last.request.content)
    assert payload["model"] == _MODEL
    assert payload["messages"] == [{"role": "user", "content": "Say hi"}]


@respx.mock
async def test_auth_bearer_header_present() -> None:
    route = respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, json=_chat_json("ok")))
    p = _provider()
    await p.complete("Hi")
    await p.aclose()
    auth = route.calls.last.request.headers.get("authorization", "")
    assert auth == f"Bearer {_API_KEY}"


# ─────────────────────────────────────────────────────────────────────────────
# Response parsing
# ─────────────────────────────────────────────────────────────────────────────


@respx.mock
async def test_returns_assistant_message_content() -> None:
    expected = "The assistant replied with this."
    respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, json=_chat_json(expected)))
    p = _provider()
    result = await p.complete("Prompt")
    await p.aclose()
    assert result == expected


@respx.mock
async def test_return_type_is_str() -> None:
    respx.post(_CHAT_URL).mock(return_value=httpx.Response(200, json=_chat_json("42")))
    p = _provider()
    result = await p.complete("Prompt")
    await p.aclose()
    assert isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# Error propagation
# ─────────────────────────────────────────────────────────────────────────────


@respx.mock
async def test_http_401_raises_status_error() -> None:
    respx.post(_CHAT_URL).mock(return_value=httpx.Response(401, json={"error": "unauthorized"}))
    p = _provider()
    with pytest.raises(httpx.HTTPStatusError):
        await p.complete("Prompt")
    await p.aclose()


@respx.mock
async def test_http_500_raises_status_error() -> None:
    respx.post(_CHAT_URL).mock(
        return_value=httpx.Response(500, json={"error": "internal server error"})
    )
    p = _provider()
    with pytest.raises(httpx.HTTPStatusError):
        await p.complete("Prompt")
    await p.aclose()


@respx.mock
async def test_http_429_raises_status_error() -> None:
    respx.post(_CHAT_URL).mock(return_value=httpx.Response(429, json={"error": "rate limited"}))
    p = _provider()
    with pytest.raises(httpx.HTTPStatusError):
        await p.complete("Prompt")
    await p.aclose()


@respx.mock
async def test_timeout_propagates_as_timeout_exception() -> None:
    respx.post(_CHAT_URL).mock(side_effect=httpx.TimeoutException("request timed out"))
    p = _provider()
    with pytest.raises(httpx.TimeoutException):
        await p.complete("Prompt")
    await p.aclose()


# ─────────────────────────────────────────────────────────────────────────────
# Concurrent safety
# ─────────────────────────────────────────────────────────────────────────────


@respx.mock
async def test_concurrent_calls_each_get_correct_response() -> None:
    """N concurrent in-flight calls each receive distinct, correct responses."""
    respx.post(_CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=_chat_json("response-A")),
            httpx.Response(200, json=_chat_json("response-B")),
            httpx.Response(200, json=_chat_json("response-C")),
        ]
    )
    p = _provider()
    results = await asyncio.gather(
        p.complete("prompt-A"),
        p.complete("prompt-B"),
        p.complete("prompt-C"),
    )
    await p.aclose()
    assert set(results) == {"response-A", "response-B", "response-C"}


@respx.mock
async def test_concurrent_calls_do_not_share_state() -> None:
    """Responses from concurrent calls are not interleaved."""
    sentinel_a = "SENTINEL_ALPHA_9914"
    sentinel_b = "SENTINEL_BETA_2277"
    respx.post(_CHAT_URL).mock(
        side_effect=[
            httpx.Response(200, json=_chat_json(f"first {sentinel_a}")),
            httpx.Response(200, json=_chat_json(f"second {sentinel_b}")),
        ]
    )
    p = _provider()
    r1, r2 = await asyncio.gather(p.complete("x"), p.complete("y"))
    await p.aclose()
    # Each response carries only its own sentinel, not the other's.
    assert sentinel_a not in r2
    assert sentinel_b not in r1


# ─────────────────────────────────────────────────────────────────────────────
# Live (opt-in)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.live
async def test_live_smoke_returns_nonempty_completion() -> None:
    """Real endpoint returns a parseable non-empty string.

    Run with: pytest -m live
    Requires: MAGI_API_KEY, MAGI_BASE_URL, MAGI_MODEL environment variables.
    """
    api_key = os.environ["MAGI_API_KEY"]
    base_url = os.environ.get("MAGI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("MAGI_MODEL", "gpt-4o-mini")

    p = OpenAICompatProvider(base_url=base_url, api_key=api_key, model=model)
    result = await p.complete("Respond with exactly one word: hello")
    await p.aclose()

    assert isinstance(result, str)
    assert len(result.strip()) > 0
