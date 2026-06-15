"""Structural tests for the packaged prompt files.

Each prompt test asserts:
  (a) the file is reachable via importlib.resources
  (b) it contains exactly the {placeholder} fields the module passes to .format()
  (c) it contains the marker token its parser greps for
"""

import string
from importlib.resources import files
from pathlib import Path


def _load(name: str) -> str:
    return (files("holdout") / "prompts" / name).read_text(encoding="utf-8")


def _placeholders(text: str) -> set[str]:
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(text)
        if field_name is not None
    }


# ── commit.txt ──────────────────────────────────────────────────────────────


def test_commit_prompt_reachable() -> None:
    assert _load("commit.txt").strip()


def test_commit_prompt_placeholders() -> None:
    assert _placeholders(_load("commit.txt")) == {"mandate", "question"}


def test_commit_prompt_marker() -> None:
    assert "VOTE:" in _load("commit.txt")


# ── concurrence.txt ──────────────────────────────────────────────────────────


def test_concurrence_prompt_reachable() -> None:
    assert _load("concurrence.txt").strip()


def test_concurrence_prompt_placeholders() -> None:
    assert _placeholders(_load("concurrence.txt")) == {"question", "rationales"}


def test_concurrence_prompt_marker() -> None:
    assert "ASSESSMENT:" in _load("concurrence.txt")


# ── crux.txt ─────────────────────────────────────────────────────────────────


def test_crux_prompt_reachable() -> None:
    assert _load("crux.txt").strip()


def test_crux_prompt_placeholders() -> None:
    assert _placeholders(_load("crux.txt")) == {"question", "rationales"}


def test_crux_prompt_marker() -> None:
    assert "consequence-anchored" in _load("crux.txt")


# ── repo layout ──────────────────────────────────────────────────────────────


def test_no_root_prompts_dir() -> None:
    repo_root = Path(__file__).parent.parent
    assert not (repo_root / "prompts").exists(), (
        "Root prompts/ should not exist; prompts live at src/holdout/prompts/"
    )
