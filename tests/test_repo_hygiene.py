"""Structural tests asserting the repo does not track OS cruft."""

import subprocess
from pathlib import Path

import pytest


def _in_git_worktree() -> bool:
    result = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


pytestmark = pytest.mark.skipif(
    not _in_git_worktree(),
    reason="not inside a git work tree",
)


def test_ds_store_not_tracked() -> None:
    result = subprocess.run(
        ["git", "ls-files", ".DS_Store", "**/.DS_Store"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "", f".DS_Store files are tracked by git:\n{result.stdout}"


def test_gitignore_lists_ds_store() -> None:
    repo_root = Path(__file__).parent.parent
    gitignore = (repo_root / ".gitignore").read_text()
    assert ".DS_Store" in gitignore, ".DS_Store is not listed in .gitignore"
