"""Pytest configuration: skip live-marked tests unless -m live is requested."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # Skip tests marked @pytest.mark.live unless the user explicitly selects them.
    if "live" in (config.getoption("-m", default="") or ""):
        return
    skip = pytest.mark.skip(reason="live tests require -m live and a configured API key")
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip)
